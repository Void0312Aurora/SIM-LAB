class_name SimulationCore
extends RefCounted

const DEFAULT_RANDOM_SEED := 1337
const CIVILIAN_SPEED_MPS := 2.1
const INFECTED_SPEED_MPS := 2.6
const MILITARY_SPEED_MPS := 2.4
const INFECTION_RADIUS_M := 4.0
const NEUTRALIZE_RADIUS_M := 7.0
const MILITARY_RESPONSE_RADIUS_M := 520.0
const SNAPSHOT_INTERVAL_STEPS := 30
const REPATHT_INTERVAL_STEPS := 8

var _path_cache: Dictionary = {}
var _next_agent_serial := 0


func simulate(
	pack: Dictionary,
	steps: int = 300,
	delta_seconds: float = 1.0,
	seed: int = DEFAULT_RANDOM_SEED,
	options: Dictionary = {}
) -> Dictionary:
	_path_cache.clear()
	_next_agent_serial = 0

	var graph := _build_graph(pack.get("nav_pedestrian", {}))
	if graph.get("node_positions", {}).is_empty():
		return {
			"ok": false,
			"error": "nav_pedestrian graph is empty"
		}

	var record_replay: bool = bool(options.get("record_replay", false))
	var replay_stride: int = max(1, int(options.get("replay_stride", 1)))
	var zones := _build_zone_context(pack.get("zones", []), graph)
	var rng := RandomNumberGenerator.new()
	rng.seed = seed
	var agents := _spawn_agents(pack.get("scenario", {}), graph, zones, rng)
	var metrics := _make_metrics(pack.get("scenario", {}), agents, steps, delta_seconds, seed)
	var snapshots: Array = [_capture_snapshot(0, agents, metrics)]
	var replay := {}
	if record_replay:
		replay = _make_replay_shell(pack, steps, delta_seconds, seed, replay_stride)
		(replay["frames"] as Array).append(_capture_replay_frame(0, 0.0, agents, metrics))
	var completed_steps := 0

	for step in range(steps):
		_update_targets(agents, graph, zones, step)
		_advance_agents(agents, graph, delta_seconds)
		var step_resolution := _resolve_step(agents, graph, zones, metrics, step + 1)
		var converted_agents: Array = step_resolution.get("converted_agents", [])
		for converted_agent in converted_agents:
			agents.append(converted_agent)
		completed_steps = step + 1
		if completed_steps % SNAPSHOT_INTERVAL_STEPS == 0 or completed_steps == steps:
			snapshots.append(_capture_snapshot(completed_steps, agents, metrics))

		var stopped_early := _should_stop(agents)
		if record_replay:
			var replay_events: Array = replay.get("events", [])
			replay_events.append_array(step_resolution.get("events", []))
			if completed_steps % replay_stride == 0 or completed_steps == steps or stopped_early:
				(replay["frames"] as Array).append(
					_capture_replay_frame(
						completed_steps,
						completed_steps * delta_seconds,
						agents,
						metrics
					)
				)

		if stopped_early:
			metrics["stopped_early"] = true
			break

	metrics["completed_step_count"] = completed_steps
	_finalize_metrics(metrics, agents)

	var result := {
		"ok": true,
		"metrics": metrics,
		"snapshots": snapshots
	}
	if record_replay:
		_finalize_replay(
			replay,
			agents,
			metrics,
			pack.get("scenario", {}),
			pack.get("manifest", {}),
			completed_steps,
			delta_seconds
		)
		result["replay"] = replay
	return result


func _build_graph(graph_payload: Dictionary) -> Dictionary:
	var node_positions := {}
	var adjacency := {}
	for node in graph_payload.get("nodes", []):
		if not node is Dictionary:
			continue
		var node_id := str(node.get("id", ""))
		if node_id.is_empty():
			continue
		node_positions[node_id] = _dict_to_vec3(node.get("position", {}))
		adjacency[node_id] = []

	for edge in graph_payload.get("edges", []):
		if not edge is Dictionary:
			continue
		var from_id := str(edge.get("from", ""))
		var to_id := str(edge.get("to", ""))
		if from_id.is_empty() or to_id.is_empty():
			continue
		if not node_positions.has(from_id) or not node_positions.has(to_id):
			continue
		var edge_cost: float = max(0.001, float(edge.get("cost", edge.get("length_m", 1.0))))
		(adjacency[from_id] as Array).append({"to": to_id, "cost": edge_cost})
		if bool(edge.get("bidirectional", true)):
			(adjacency[to_id] as Array).append({"to": from_id, "cost": edge_cost})

	return {
		"node_positions": node_positions,
		"adjacency": adjacency
	}


func _build_zone_context(zones_payload: Array, graph: Dictionary) -> Dictionary:
	var by_id := {}
	var by_class := {}
	var goal_zones: Array = []
	for zone in zones_payload:
		if not zone is Dictionary:
			continue
		var zone_id := str(zone.get("id", ""))
		if zone_id.is_empty():
			continue
		var zone_copy: Dictionary = (zone as Dictionary).duplicate(true)
		var center := _dict_to_vec3(zone_copy.get("center", {}))
		zone_copy["center_vec3"] = center
		zone_copy["graph_node_id"] = _nearest_node_to_position(graph, center)
		by_id[zone_id] = zone_copy
		var zone_class := str(zone_copy.get("class", "generic_zone"))
		if not by_class.has(zone_class):
			by_class[zone_class] = []
		(by_class[zone_class] as Array).append(zone_copy)
		if zone_class == "safe_zone" or zone_class == "evac_point":
			goal_zones.append(zone_copy)

	return {
		"by_id": by_id,
		"by_class": by_class,
		"goal_zones": goal_zones
	}


func _spawn_agents(
	scenario: Dictionary,
	graph: Dictionary,
	zones: Dictionary,
	rng: RandomNumberGenerator
) -> Array:
	var agents: Array = []
	var zone_index: Dictionary = zones.get("by_id", {})
	for spawn_rule in scenario.get("spawn_rules", []):
		if not spawn_rule is Dictionary:
			continue
		var faction := str(spawn_rule.get("faction", ""))
		var zone_id := str(spawn_rule.get("zone_id", ""))
		var zone: Dictionary = zone_index.get(zone_id, {})
		if zone.is_empty():
			continue
		var count := int(spawn_rule.get("count", 0))
		var distribution := str(spawn_rule.get("distribution", "clustered"))
		for _agent_index in range(count):
			var node_id := _pick_spawn_node(zone, graph, distribution, rng)
			var node_positions: Dictionary = graph.get("node_positions", {})
			var position: Vector3 = node_positions.get(node_id, zone.get("center_vec3", Vector3.ZERO))
			agents.append(
				{
					"id": "%s_%03d" % [_faction_token(faction), _take_agent_serial()],
					"faction": faction,
					"active": true,
					"state": _initial_state_for_faction(faction),
					"spawn_zone_id": zone_id,
					"home_zone_id": zone_id,
					"target_zone_id": "",
					"target_node_id": node_id,
					"speed_mps": _speed_for_faction(faction),
					"current_node_id": node_id,
					"position": position,
					"path": [node_id],
					"path_progress_m": 0.0,
					"last_repath_step": -9999
				}
			)
	return agents


func _make_metrics(
	scenario: Dictionary,
	agents: Array,
	steps: int,
	delta_seconds: float,
	seed: int
) -> Dictionary:
	var faction_counts := _count_active_agents_by_faction(agents)
	return {
		"scenario_id": str(scenario.get("scenario_id", "<unknown>")),
		"configured_step_count": steps,
		"delta_seconds": delta_seconds,
		"random_seed": seed,
		"initial_civilian_count": int(faction_counts.get("civilians", 0)),
		"initial_infected_count": int(faction_counts.get("infected", 0)),
		"initial_military_count": int(faction_counts.get("military", 0)),
		"completed_step_count": 0,
		"stopped_early": false,
		"evacuated_count": 0,
		"converted_count": 0,
		"neutralized_count": 0
	}


func _update_targets(agents: Array, graph: Dictionary, zones: Dictionary, step: int) -> void:
	var active_civilians := _active_agents_for_faction(agents, "civilians")
	var active_infected := _active_agents_for_faction(agents, "infected")

	for agent in agents:
		if not bool(agent.get("active", false)):
			continue
		var faction := str(agent.get("faction", ""))
		match faction:
			"civilians":
				_update_civilian_target(agent, graph, zones, step)
			"infected":
				_update_infected_target(agent, graph, active_civilians, step)
			"military":
				_update_military_target(agent, graph, zones, active_infected, step)


func _update_civilian_target(agent: Dictionary, graph: Dictionary, zones: Dictionary, step: int) -> void:
	var goal_zones: Array = zones.get("goal_zones", [])
	if goal_zones.is_empty():
		return
	var nearest_goal := _nearest_zone_to_position(goal_zones, agent.get("position", Vector3.ZERO))
	if nearest_goal.is_empty():
		return
	agent["state"] = "evacuating"
	agent["target_zone_id"] = str(nearest_goal.get("id", ""))
	_set_path_if_needed(agent, graph, str(nearest_goal.get("graph_node_id", "")), step)


func _update_infected_target(agent: Dictionary, graph: Dictionary, active_civilians: Array, step: int) -> void:
	if active_civilians.is_empty():
		return
	var nearest_civilian := _nearest_agent_to_position(active_civilians, agent.get("position", Vector3.ZERO))
	if nearest_civilian.is_empty():
		return
	agent["state"] = "hunting"
	_set_path_if_needed(
		agent,
		graph,
		_nearest_node_to_position(graph, nearest_civilian.get("position", Vector3.ZERO)),
		step
	)


func _update_military_target(
	agent: Dictionary,
	graph: Dictionary,
	zones: Dictionary,
	active_infected: Array,
	step: int
) -> void:
	if active_infected.is_empty():
		_return_military_to_home(agent, graph, zones, step)
		return

	var home_zone_id := str(agent.get("home_zone_id", ""))
	var home_zone: Dictionary = zones.get("by_id", {}).get(home_zone_id, {})
	var reference_position: Vector3 = home_zone.get("center_vec3", agent.get("position", Vector3.ZERO))
	var nearest_infected := _nearest_agent_to_position(active_infected, reference_position)
	if nearest_infected.is_empty():
		_return_military_to_home(agent, graph, zones, step)
		return
	if reference_position.distance_to(nearest_infected.get("position", Vector3.ZERO)) > MILITARY_RESPONSE_RADIUS_M:
		_return_military_to_home(agent, graph, zones, step)
		return

	agent["state"] = "responding"
	_set_path_if_needed(
		agent,
		graph,
		_nearest_node_to_position(graph, nearest_infected.get("position", Vector3.ZERO)),
		step
	)


func _return_military_to_home(agent: Dictionary, graph: Dictionary, zones: Dictionary, step: int) -> void:
	var home_zone_id := str(agent.get("home_zone_id", ""))
	var home_zone: Dictionary = zones.get("by_id", {}).get(home_zone_id, {})
	if home_zone.is_empty():
		return
	agent["state"] = "holding"
	_set_path_if_needed(agent, graph, str(home_zone.get("graph_node_id", "")), step)


func _set_path_if_needed(agent: Dictionary, graph: Dictionary, target_node_id: String, step: int) -> void:
	if target_node_id.is_empty():
		return
	if not _agent_is_at_node(agent):
		return
	var current_target_id := str(agent.get("target_node_id", ""))
	if current_target_id == target_node_id and step - int(agent.get("last_repath_step", -9999)) < REPATHT_INTERVAL_STEPS:
		return

	var from_node_id := str(agent.get("current_node_id", ""))
	if from_node_id.is_empty():
		from_node_id = _nearest_node_to_position(graph, agent.get("position", Vector3.ZERO))
		agent["current_node_id"] = from_node_id
	if from_node_id.is_empty():
		return

	var path := _shortest_path(graph, from_node_id, target_node_id)
	if path.is_empty():
		path = [from_node_id]
	agent["target_node_id"] = target_node_id
	agent["path"] = path
	agent["path_progress_m"] = 0.0
	agent["last_repath_step"] = step


func _advance_agents(agents: Array, graph: Dictionary, delta_seconds: float) -> void:
	for agent in agents:
		if not bool(agent.get("active", false)):
			continue
		_advance_agent(agent, graph, delta_seconds)


func _advance_agent(agent: Dictionary, graph: Dictionary, delta_seconds: float) -> void:
	var path: Array = agent.get("path", []).duplicate()
	if path.size() <= 1:
		var node_id := str(agent.get("current_node_id", ""))
		if not node_id.is_empty():
			agent["position"] = graph.get("node_positions", {}).get(node_id, agent.get("position", Vector3.ZERO))
		agent["path"] = path
		return

	var node_positions: Dictionary = graph.get("node_positions", {})
	var remaining_distance: float = max(0.0, float(agent.get("speed_mps", 0.0)) * delta_seconds)
	var position: Vector3 = agent.get("position", Vector3.ZERO)
	var path_progress_m: float = float(agent.get("path_progress_m", 0.0))

	while remaining_distance > 0.001 and path.size() >= 2:
		var from_id := str(path[0])
		var to_id := str(path[1])
		var from_position: Vector3 = node_positions.get(from_id, position)
		var to_position: Vector3 = node_positions.get(to_id, from_position)
		var segment_length: float = max(0.001, _edge_length_between(graph, from_id, to_id))
		var available_distance: float = segment_length - path_progress_m
		var travel_distance: float = min(remaining_distance, available_distance)
		path_progress_m += travel_distance
		remaining_distance -= travel_distance
		var progress_ratio: float = clamp(path_progress_m / segment_length, 0.0, 1.0)
		position = from_position.lerp(to_position, progress_ratio)
		if path_progress_m >= segment_length - 0.001:
			path.remove_at(0)
			path_progress_m = 0.0
			agent["current_node_id"] = str(path[0])
			position = to_position
		else:
			agent["current_node_id"] = from_id
			break

	agent["position"] = position
	agent["path_progress_m"] = path_progress_m
	agent["path"] = path


func _resolve_step(
	agents: Array,
	graph: Dictionary,
	zones: Dictionary,
	metrics: Dictionary,
	step: int
) -> Dictionary:
	var step_events: Array = []
	_resolve_evacuations(agents, zones.get("goal_zones", []), metrics, step, step_events)
	_resolve_neutralizations(agents, metrics, step, step_events)
	var converted_agents := _resolve_infections(agents, graph, metrics, step, step_events)
	return {
		"converted_agents": converted_agents,
		"events": step_events
	}


func _resolve_evacuations(
	agents: Array,
	goal_zones: Array,
	metrics: Dictionary,
	step: int,
	step_events: Array
) -> void:
	if goal_zones.is_empty():
		return
	for agent in agents:
		if not bool(agent.get("active", false)):
			continue
		if str(agent.get("faction", "")) != "civilians":
			continue
		for zone in goal_zones:
			var center: Vector3 = zone.get("center_vec3", Vector3.ZERO)
			var radius: float = float(zone.get("radius_m", 0.0))
			if center.distance_to(agent.get("position", Vector3.ZERO)) <= radius:
				agent["active"] = false
				agent["state"] = "evacuated"
				metrics["evacuated_count"] = int(metrics.get("evacuated_count", 0)) + 1
				step_events.append(
					_make_replay_event(
						step,
						"evacuated",
						agent,
						{
							"zone_id": str(zone.get("id", "")),
							"target_zone_id": str(agent.get("target_zone_id", ""))
						}
					)
				)
				break


func _resolve_neutralizations(
	agents: Array,
	metrics: Dictionary,
	step: int,
	step_events: Array
) -> void:
	var active_military := _active_agents_for_faction(agents, "military")
	var active_infected := _active_agents_for_faction(agents, "infected")
	if active_military.is_empty() or active_infected.is_empty():
		return

	var neutralized_ids := {}
	for military_agent in active_military:
		var military_position: Vector3 = military_agent.get("position", Vector3.ZERO)
		for infected_agent in active_infected:
			var infected_id := str(infected_agent.get("id", ""))
			if neutralized_ids.has(infected_id):
				continue
			var infected_position: Vector3 = infected_agent.get("position", Vector3.ZERO)
			if military_position.distance_to(infected_position) <= NEUTRALIZE_RADIUS_M:
				neutralized_ids[infected_id] = true

	for agent in agents:
		var agent_id := str(agent.get("id", ""))
		if neutralized_ids.has(agent_id) and bool(agent.get("active", false)):
			agent["active"] = false
			agent["state"] = "neutralized"
			metrics["neutralized_count"] = int(metrics.get("neutralized_count", 0)) + 1
			step_events.append(_make_replay_event(step, "neutralized", agent))


func _resolve_infections(
	agents: Array,
	graph: Dictionary,
	metrics: Dictionary,
	step: int,
	step_events: Array
) -> Array:
	var active_civilians := _active_agents_for_faction(agents, "civilians")
	var active_infected := _active_agents_for_faction(agents, "infected")
	if active_civilians.is_empty() or active_infected.is_empty():
		return []

	var converted_ids := {}
	var converted_agents: Array = []
	for infected_agent in active_infected:
		var infected_position: Vector3 = infected_agent.get("position", Vector3.ZERO)
		for civilian_agent in active_civilians:
			var civilian_id := str(civilian_agent.get("id", ""))
			if converted_ids.has(civilian_id):
				continue
			var civilian_position: Vector3 = civilian_agent.get("position", Vector3.ZERO)
			if infected_position.distance_to(civilian_position) <= INFECTION_RADIUS_M:
				converted_ids[civilian_id] = true
				break

	for agent in agents:
		var agent_id := str(agent.get("id", ""))
		if converted_ids.has(agent_id) and bool(agent.get("active", false)):
			agent["active"] = false
			agent["state"] = "infected"
			metrics["converted_count"] = int(metrics.get("converted_count", 0)) + 1
			var converted_agent := _make_converted_infected(agent, graph)
			converted_agents.append(converted_agent)
			step_events.append(
				_make_replay_event(
					step,
					"converted",
					agent,
					{
						"spawned_agent_id": str(converted_agent.get("id", "")),
						"spawned_faction": str(converted_agent.get("faction", "")),
						"spawned_state": str(converted_agent.get("state", "")),
						"spawned_position": _vec3_to_dict(converted_agent.get("position", Vector3.ZERO))
					}
				)
			)

	return converted_agents


func _make_converted_infected(source_agent: Dictionary, graph: Dictionary) -> Dictionary:
	var position: Vector3 = source_agent.get("position", Vector3.ZERO)
	var nearest_node_id := _nearest_node_to_position(graph, position)
	var node_positions: Dictionary = graph.get("node_positions", {})
	var snapped_position: Vector3 = node_positions.get(nearest_node_id, position)
	return {
		"id": "infected_%03d" % _take_agent_serial(),
		"faction": "infected",
		"active": true,
		"state": "hunting",
		"spawn_zone_id": str(source_agent.get("spawn_zone_id", "")),
		"home_zone_id": str(source_agent.get("home_zone_id", "")),
		"target_zone_id": "",
		"target_node_id": nearest_node_id,
		"speed_mps": INFECTED_SPEED_MPS,
		"current_node_id": nearest_node_id,
		"position": snapped_position,
		"path": [nearest_node_id],
		"path_progress_m": 0.0,
		"last_repath_step": -9999
	}


func _capture_snapshot(step: int, agents: Array, metrics: Dictionary) -> Dictionary:
	var active_counts := _count_active_agents_by_faction(agents)
	return {
		"step": step,
		"active_civilians": int(active_counts.get("civilians", 0)),
		"active_infected": int(active_counts.get("infected", 0)),
		"active_military": int(active_counts.get("military", 0)),
		"evacuated_count": int(metrics.get("evacuated_count", 0)),
		"converted_count": int(metrics.get("converted_count", 0)),
		"neutralized_count": int(metrics.get("neutralized_count", 0))
	}


func _make_replay_shell(
	pack: Dictionary,
	steps: int,
	delta_seconds: float,
	seed: int,
	replay_stride: int
) -> Dictionary:
	return {
		"schema_version": "0.1.0",
		"pack_id": str(pack.get("manifest", {}).get("pack_id", "")),
		"scenario_id": str(pack.get("scenario", {}).get("scenario_id", "")),
		"recording": {
			"configured_step_count": steps,
			"delta_seconds": delta_seconds,
			"random_seed": seed,
			"frame_stride_steps": replay_stride
		},
		"frames": [],
		"events": []
	}


func _capture_replay_frame(step: int, time_seconds: float, agents: Array, metrics: Dictionary) -> Dictionary:
	var active_counts := _count_active_agents_by_faction(agents)
	return {
		"step": step,
		"time_seconds": snappedf(time_seconds, 0.001),
		"counts": {
			"active_civilians": int(active_counts.get("civilians", 0)),
			"active_infected": int(active_counts.get("infected", 0)),
			"active_military": int(active_counts.get("military", 0)),
			"evacuated_count": int(metrics.get("evacuated_count", 0)),
			"converted_count": int(metrics.get("converted_count", 0)),
			"neutralized_count": int(metrics.get("neutralized_count", 0))
		},
		"agents": _serialize_agents_for_replay(agents)
	}


func _serialize_agents_for_replay(agents: Array) -> Array:
	var serialized: Array = []
	for agent in agents:
		if not agent is Dictionary:
			continue
		serialized.append(
			{
				"id": str(agent.get("id", "")),
				"faction": str(agent.get("faction", "")),
				"state": str(agent.get("state", "")),
				"active": bool(agent.get("active", false)),
				"position": _vec3_to_dict(agent.get("position", Vector3.ZERO)),
				"current_node_id": str(agent.get("current_node_id", "")),
				"target_node_id": str(agent.get("target_node_id", "")),
				"spawn_zone_id": str(agent.get("spawn_zone_id", "")),
				"home_zone_id": str(agent.get("home_zone_id", ""))
			}
		)
	return serialized


func _build_agent_manifest(agents: Array) -> Array:
	var manifest: Array = []
	for agent in agents:
		if not agent is Dictionary:
			continue
		manifest.append(
			{
				"id": str(agent.get("id", "")),
				"faction": str(agent.get("faction", "")),
				"spawn_zone_id": str(agent.get("spawn_zone_id", "")),
				"home_zone_id": str(agent.get("home_zone_id", ""))
			}
		)
	return manifest


func _make_replay_event(step: int, event_type: String, agent: Dictionary, extra: Dictionary = {}) -> Dictionary:
	var event := {
		"step": step,
		"type": event_type,
		"agent_id": str(agent.get("id", "")),
		"faction": str(agent.get("faction", "")),
		"state": str(agent.get("state", "")),
		"position": _vec3_to_dict(agent.get("position", Vector3.ZERO))
	}
	event.merge(extra, true)
	return event


func _finalize_replay(
	replay: Dictionary,
	agents: Array,
	metrics: Dictionary,
	scenario: Dictionary,
	manifest: Dictionary,
	completed_steps: int,
	delta_seconds: float
) -> void:
	replay["completed_step_count"] = completed_steps
	replay["duration_seconds"] = snappedf(completed_steps * delta_seconds, 0.001)
	replay["metrics"] = metrics.duplicate(true)
	replay["agent_manifest"] = _build_agent_manifest(agents)
	replay["map_manifest"] = {
		"pack_id": str(manifest.get("pack_id", "")),
		"schema_version": str(manifest.get("schema_version", "")),
		"scenario_id": str(scenario.get("scenario_id", ""))
	}


func _finalize_metrics(metrics: Dictionary, agents: Array) -> void:
	var active_counts := _count_active_agents_by_faction(agents)
	var inactive_counts := _count_inactive_agents_by_state(agents)
	metrics["remaining_civilian_count"] = int(active_counts.get("civilians", 0))
	metrics["remaining_infected_count"] = int(active_counts.get("infected", 0))
	metrics["active_military_count"] = int(active_counts.get("military", 0))
	metrics["evacuated_ratio"] = _safe_ratio(int(metrics.get("evacuated_count", 0)), int(metrics.get("initial_civilian_count", 0)))
	metrics["conversion_ratio"] = _safe_ratio(int(metrics.get("converted_count", 0)), int(metrics.get("initial_civilian_count", 0)))
	metrics["neutralized_ratio"] = _safe_ratio(int(metrics.get("neutralized_count", 0)), int(metrics.get("initial_infected_count", 0)) + int(metrics.get("converted_count", 0)))
	metrics["inactive_state_counts"] = inactive_counts


func _count_active_agents_by_faction(agents: Array) -> Dictionary:
	var counts := {}
	for agent in agents:
		if not bool(agent.get("active", false)):
			continue
		var faction := str(agent.get("faction", ""))
		counts[faction] = int(counts.get(faction, 0)) + 1
	return counts


func _count_inactive_agents_by_state(agents: Array) -> Dictionary:
	var counts := {}
	for agent in agents:
		if bool(agent.get("active", false)):
			continue
		var state := str(agent.get("state", "inactive"))
		counts[state] = int(counts.get(state, 0)) + 1
	return counts


func _active_agents_for_faction(agents: Array, faction: String) -> Array:
	var filtered: Array = []
	for agent in agents:
		if bool(agent.get("active", false)) and str(agent.get("faction", "")) == faction:
			filtered.append(agent)
	return filtered


func _nearest_zone_to_position(zones: Array, position: Vector3) -> Dictionary:
	var nearest_zone: Dictionary = {}
	var best_distance := INF
	for zone in zones:
		var center: Vector3 = zone.get("center_vec3", Vector3.ZERO)
		var distance := center.distance_to(position)
		if distance < best_distance:
			best_distance = distance
			nearest_zone = zone
	return nearest_zone


func _nearest_agent_to_position(agents: Array, position: Vector3) -> Dictionary:
	var nearest_agent: Dictionary = {}
	var best_distance := INF
	for agent in agents:
		var candidate_position: Vector3 = agent.get("position", Vector3.ZERO)
		var distance := candidate_position.distance_to(position)
		if distance < best_distance:
			best_distance = distance
			nearest_agent = agent
	return nearest_agent


func _pick_spawn_node(zone: Dictionary, graph: Dictionary, distribution: String, rng: RandomNumberGenerator) -> String:
	var candidates := _node_ids_within_radius(graph, zone.get("center_vec3", Vector3.ZERO), float(zone.get("radius_m", 0.0)))
	if candidates.is_empty():
		return str(zone.get("graph_node_id", ""))
	if distribution == "uniform":
		return str(candidates[rng.randi_range(0, candidates.size() - 1)])
	return _nearest_node_from_candidates(graph, zone.get("center_vec3", Vector3.ZERO), candidates)


func _node_ids_within_radius(graph: Dictionary, position: Vector3, radius_m: float) -> Array:
	var node_positions: Dictionary = graph.get("node_positions", {})
	var candidates: Array = []
	for node_id in node_positions.keys():
		var candidate_position: Vector3 = node_positions[node_id]
		if candidate_position.distance_to(position) <= radius_m:
			candidates.append(node_id)
	return candidates


func _nearest_node_from_candidates(graph: Dictionary, position: Vector3, candidates: Array) -> String:
	var node_positions: Dictionary = graph.get("node_positions", {})
	var best_node_id := ""
	var best_distance := INF
	for node_id in candidates:
		var candidate_position: Vector3 = node_positions.get(node_id, position)
		var distance := candidate_position.distance_to(position)
		if distance < best_distance:
			best_distance = distance
			best_node_id = str(node_id)
	return best_node_id


func _nearest_node_to_position(graph: Dictionary, position: Vector3) -> String:
	return _nearest_node_from_candidates(graph, position, graph.get("node_positions", {}).keys())


func _shortest_path(graph: Dictionary, from_id: String, to_id: String) -> Array:
	if from_id.is_empty() or to_id.is_empty():
		return []
	if from_id == to_id:
		return [from_id]
	var cache_key := "%s->%s" % [from_id, to_id]
	if _path_cache.has(cache_key):
		return (_path_cache[cache_key] as Array).duplicate()

	var distances := {from_id: 0.0}
	var previous := {}
	var frontier: Array = [{"id": from_id, "cost": 0.0}]
	var visited := {}
	var adjacency: Dictionary = graph.get("adjacency", {})

	while not frontier.is_empty():
		var best_index := 0
		for frontier_index in range(1, frontier.size()):
			if float(frontier[frontier_index]["cost"]) < float(frontier[best_index]["cost"]):
				best_index = frontier_index
		var current: Dictionary = frontier[best_index]
		frontier.remove_at(best_index)
		var current_id := str(current.get("id", ""))
		if visited.has(current_id):
			continue
		visited[current_id] = true
		if current_id == to_id:
			break
		for neighbor in adjacency.get(current_id, []):
			var neighbor_id := str(neighbor.get("to", ""))
			var travel_cost := float(neighbor.get("cost", 1.0))
			var next_cost := float(distances.get(current_id, INF)) + travel_cost
			if next_cost < float(distances.get(neighbor_id, INF)):
				distances[neighbor_id] = next_cost
				previous[neighbor_id] = current_id
				frontier.append({"id": neighbor_id, "cost": next_cost})

	if not previous.has(to_id):
		return []

	var path: Array = [to_id]
	var walk_id := to_id
	while previous.has(walk_id):
		walk_id = str(previous[walk_id])
		path.push_front(walk_id)
		if walk_id == from_id:
			break

	_path_cache[cache_key] = path.duplicate()
	return path


func _edge_length_between(graph: Dictionary, from_id: String, to_id: String) -> float:
	for edge in graph.get("adjacency", {}).get(from_id, []):
		if str(edge.get("to", "")) == to_id:
			return float(edge.get("cost", 1.0))
	return 1.0


func _agent_is_at_node(agent: Dictionary) -> bool:
	return abs(float(agent.get("path_progress_m", 0.0))) <= 0.001


func _should_stop(agents: Array) -> bool:
	var active_civilians := 0
	var active_infected := 0
	for agent in agents:
		if not bool(agent.get("active", false)):
			continue
		match str(agent.get("faction", "")):
			"civilians":
				active_civilians += 1
			"infected":
				active_infected += 1
	return active_civilians == 0 or active_infected == 0


func _speed_for_faction(faction: String) -> float:
	match faction:
		"civilians":
			return CIVILIAN_SPEED_MPS
		"infected":
			return INFECTED_SPEED_MPS
		"military":
			return MILITARY_SPEED_MPS
		_:
			return 1.0


func _initial_state_for_faction(faction: String) -> String:
	match faction:
		"civilians":
			return "evacuating"
		"infected":
			return "hunting"
		"military":
			return "holding"
		_:
			return "idle"


func _faction_token(faction: String) -> String:
	match faction:
		"civilians":
			return "civilian"
		"infected":
			return "infected"
		"military":
			return "military"
		_:
			return "agent"


func _take_agent_serial() -> int:
	var serial := _next_agent_serial
	_next_agent_serial += 1
	return serial


func _safe_ratio(numerator: int, denominator: int) -> float:
	if denominator <= 0:
		return 0.0
	return snappedf(float(numerator) / float(denominator), 0.0001)


func _vec3_to_dict(source: Vector3) -> Dictionary:
	return {
		"x": snappedf(source.x, 0.001),
		"y": snappedf(source.y, 0.001),
		"z": snappedf(source.z, 0.001)
	}


func _dict_to_vec3(source: Dictionary) -> Vector3:
	return Vector3(
		float(source.get("x", 0.0)),
		float(source.get("y", 0.0)),
		float(source.get("z", 0.0))
	)
