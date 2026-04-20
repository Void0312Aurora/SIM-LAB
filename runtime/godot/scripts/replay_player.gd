class_name ReplayPlayer
extends Node3D

signal status_changed(status)
signal playback_finished

const AGENTS_ROOT_NAME := "ReplayAgents"
const RECENT_EVENT_LIMIT := 5

var _replay: Dictionary = {}
var _frames: Array = []
var _frame_maps: Array = []
var _agent_nodes: Dictionary = {}
var _playback_time := 0.0
var _frame_index := 0
var _playing := false
var _playback_speed := 1.0
var _duration_seconds := 0.0


func load_replay(replay: Dictionary) -> void:
	_replay = replay.duplicate(true)
	_frames = _replay.get("frames", [])
	_frame_maps = []
	_playback_time = 0.0
	_frame_index = 0
	_duration_seconds = 0.0
	if not _frames.is_empty():
		_duration_seconds = float(_frames[_frames.size() - 1].get("time_seconds", 0.0))
	_build_frame_maps()
	_build_agent_nodes()
	_render_current_state()


func set_playing(enabled: bool) -> void:
	_playing = enabled and _frames.size() > 1
	_emit_status()


func is_playing() -> bool:
	return _playing


func restart() -> void:
	_playback_time = 0.0
	_frame_index = 0
	_playing = _frames.size() > 1
	_render_current_state()


func step_once(direction: int) -> void:
	if _frames.is_empty():
		return
	_playing = false
	_frame_index = clampi(_frame_index + direction, 0, _frames.size() - 1)
	_playback_time = float(_frames[_frame_index].get("time_seconds", 0.0))
	_render_current_state()


func toggle_playing() -> void:
	set_playing(not _playing)


func set_playback_speed(speed: float) -> void:
	_playback_speed = clampf(speed, 0.25, 32.0)
	_emit_status()


func get_playback_speed() -> float:
	return _playback_speed


func get_status() -> Dictionary:
	if _frames.is_empty():
		return {
			"has_replay": false,
			"playing": false,
			"speed": _playback_speed,
			"recent_events": []
		}
	var frame: Dictionary = _frames[_frame_index]
	var step: int = int(frame.get("step", 0))
	return {
		"has_replay": true,
		"playing": _playing,
		"speed": _playback_speed,
		"step": step,
		"time_seconds": _playback_time,
		"frame_index": _frame_index,
		"frame_count": _frames.size(),
		"duration_seconds": _duration_seconds,
		"counts": frame.get("counts", {}),
		"metrics": _replay.get("metrics", {}),
		"recent_events": _collect_recent_event_lines(step)
	}


func _process(delta: float) -> void:
	if _frames.is_empty():
		return
	if _playing and _frame_index < _frames.size() - 1:
		_playback_time = min(_duration_seconds, _playback_time + delta * _playback_speed)
		while _frame_index + 1 < _frames.size() and _playback_time >= float(_frames[_frame_index + 1].get("time_seconds", 0.0)):
			_frame_index += 1
		if _playback_time >= _duration_seconds - 0.0001:
			_playback_time = _duration_seconds
			_playing = false
			emit_signal("playback_finished")
	_render_current_state()


func _build_frame_maps() -> void:
	for frame in _frames:
		var map: Dictionary = {}
		for agent_state in frame.get("agents", []):
			if not agent_state is Dictionary:
				continue
			var agent_id := str(agent_state.get("id", ""))
			if agent_id.is_empty():
				continue
			map[agent_id] = agent_state
		_frame_maps.append(map)


func _build_agent_nodes() -> void:
	_clear_agents_root()
	var agents_root := Node3D.new()
	agents_root.name = AGENTS_ROOT_NAME
	add_child(agents_root)

	var manifest_agents: Array = _replay.get("agent_manifest", [])
	if manifest_agents.is_empty():
		manifest_agents = _collect_manifest_from_frames()
	for manifest_agent in manifest_agents:
		if manifest_agent is Dictionary:
			_create_agent_node(agents_root, manifest_agent)


func _clear_agents_root() -> void:
	if has_node(AGENTS_ROOT_NAME):
		var existing := get_node(AGENTS_ROOT_NAME)
		remove_child(existing)
		existing.free()
	_agent_nodes.clear()


func _collect_manifest_from_frames() -> Array:
	var manifest: Array = []
	var seen := {}
	for frame in _frames:
		for agent_state in frame.get("agents", []):
			if not agent_state is Dictionary:
				continue
			var agent_id := str(agent_state.get("id", ""))
			if agent_id.is_empty() or seen.has(agent_id):
				continue
			seen[agent_id] = true
			manifest.append(
				{
					"id": agent_id,
					"faction": str(agent_state.get("faction", "")),
					"spawn_zone_id": str(agent_state.get("spawn_zone_id", "")),
					"home_zone_id": str(agent_state.get("home_zone_id", ""))
				}
			)
	return manifest


func _create_agent_node(parent: Node3D, manifest_agent: Dictionary) -> void:
	var agent_id := str(manifest_agent.get("id", ""))
	if agent_id.is_empty() or _agent_nodes.has(agent_id):
		return

	var faction := str(manifest_agent.get("faction", ""))
	var root := Node3D.new()
	root.name = agent_id
	root.visible = false

	var mesh_instance := MeshInstance3D.new()
	mesh_instance.mesh = _mesh_for_faction(faction)
	mesh_instance.position = Vector3(0.0, _mesh_height_offset(faction), 0.0)
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mesh_instance.material_override = material
	root.add_child(mesh_instance)
	parent.add_child(root)

	_agent_nodes[agent_id] = {
		"root": root,
		"material": material
	}


func _mesh_for_faction(faction: String) -> Mesh:
	match faction:
		"civilians":
			var mesh := CapsuleMesh.new()
			mesh.radius = 0.75
			mesh.height = 2.0
			return mesh
		"infected":
			var mesh := SphereMesh.new()
			mesh.radius = 0.95
			mesh.height = 1.9
			return mesh
		"military":
			var mesh := BoxMesh.new()
			mesh.size = Vector3(1.5, 2.0, 1.5)
			return mesh
		_:
			var mesh := SphereMesh.new()
			mesh.radius = 0.8
			mesh.height = 1.6
			return mesh


func _mesh_height_offset(faction: String) -> float:
	match faction:
		"civilians":
			return 1.45
		"infected":
			return 0.95
		"military":
			return 1.0
		_:
			return 1.0


func _render_current_state() -> void:
	if _frames.is_empty():
		_emit_status()
		return
	var from_frame: Dictionary = _frames[_frame_index]
	var to_index: int = min(_frame_index + 1, _frames.size() - 1)
	var to_frame: Dictionary = _frames[to_index]
	var from_time := float(from_frame.get("time_seconds", 0.0))
	var to_time := float(to_frame.get("time_seconds", from_time))
	var alpha: float = 0.0
	if to_index != _frame_index and to_time - from_time > 0.0001:
		alpha = clampf((_playback_time - from_time) / (to_time - from_time), 0.0, 1.0)
	var from_map: Dictionary = _frame_maps[_frame_index]
	var to_map: Dictionary = _frame_maps[to_index]

	for agent_id in _agent_nodes.keys():
		var from_state: Dictionary = from_map.get(agent_id, {})
		var to_state: Dictionary = to_map.get(agent_id, from_state)
		_apply_agent_state(str(agent_id), from_state, to_state, alpha)

	_emit_status()


func _apply_agent_state(agent_id: String, from_state: Dictionary, to_state: Dictionary, alpha: float) -> void:
	var agent_entry: Dictionary = _agent_nodes.get(agent_id, {})
	if agent_entry.is_empty():
		return
	var root: Node3D = agent_entry.get("root")
	var material: StandardMaterial3D = agent_entry.get("material")
	if from_state.is_empty():
		root.visible = false
		return

	var from_position := _dict_to_vec3(from_state.get("position", {}))
	var to_position := from_position
	if not to_state.is_empty():
		to_position = _dict_to_vec3(to_state.get("position", {}))
	root.position = from_position.lerp(to_position, alpha)

	var active := bool(from_state.get("active", false))
	var state := str(from_state.get("state", ""))
	var keep_visible := active or state == "neutralized"
	root.visible = keep_visible
	if not keep_visible:
		return

	var color := _color_for_agent_state(from_state)
	material.transparency = BaseMaterial3D.TRANSPARENCY_DISABLED
	if not active:
		color.a = 0.8
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	root.scale = Vector3.ONE
	if state == "neutralized":
		root.scale = Vector3(0.85, 0.4, 0.85)
	material.albedo_color = color


func _color_for_agent_state(agent_state: Dictionary) -> Color:
	var faction := str(agent_state.get("faction", ""))
	var state := str(agent_state.get("state", ""))
	var active := bool(agent_state.get("active", false))
	if not active:
		match state:
			"neutralized":
				return Color(0.35, 0.35, 0.38)
			"evacuated":
				return Color(0.22, 0.72, 0.32)
			_:
				return Color(0.45, 0.2, 0.2)
	match faction:
		"civilians":
			return Color(0.24, 0.88, 0.35)
		"infected":
			return Color(0.94, 0.22, 0.18)
		"military":
			return Color(0.2, 0.56, 0.95)
		_:
			return Color(0.9, 0.88, 0.5)


func _collect_recent_event_lines(current_step: int) -> Array:
	var lines: Array = []
	for event in _replay.get("events", []):
		if not event is Dictionary:
			continue
		if int(event.get("step", 0)) > current_step:
			continue
		lines.append(_format_event_line(event))
		if lines.size() > RECENT_EVENT_LIMIT:
			lines.remove_at(0)
	return lines


func _format_event_line(event: Dictionary) -> String:
	var event_type := str(event.get("type", "event"))
	var agent_id := str(event.get("agent_id", "<agent>"))
	var step := int(event.get("step", 0))
	match event_type:
		"evacuated":
			return "step %d: %s evacuated to %s" % [step, agent_id, str(event.get("zone_id", "<zone>"))]
		"neutralized":
			return "step %d: %s neutralized" % [step, agent_id]
		"converted":
			return "step %d: %s converted -> %s" % [step, agent_id, str(event.get("spawned_agent_id", "<spawn>"))]
		_:
			return "step %d: %s %s" % [step, agent_id, event_type]


func _emit_status() -> void:
	emit_signal("status_changed", get_status())


func _dict_to_vec3(source: Dictionary) -> Vector3:
	return Vector3(
		float(source.get("x", 0.0)),
		float(source.get("y", 0.0)),
		float(source.get("z", 0.0))
	)
