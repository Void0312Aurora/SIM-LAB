extends Node3D

const RuntimePackLoader = preload("res://scripts/runtime_pack_loader.gd")
const SimulationCore = preload("res://scripts/simulation_core.gd")
const ReplayPlayer = preload("res://scripts/replay_player.gd")

const DEBUG_CAMERA_NAME := "DebugCamera"
const DEBUG_SUN_NAME := "DebugSun"
const DEBUG_ENVIRONMENT_NAME := "DebugEnvironment"
const HUD_LAYER_NAME := "HudLayer"
const HUD_PANEL_NAME := "HudPanel"
const HUD_LABEL_NAME := "HudLabel"
const DEFAULT_REPLAY_SPEED := 6.0

var _hud_label: Label
var _replay_player: ReplayPlayer


func _ready() -> void:
	print("Urban Sim Lab Godot bootstrap ready")
	_ensure_debug_environment()
	_ensure_hud()

	var pack_dir := _extract_string_arg("--pack-dir", "")
	if pack_dir.is_empty():
		_set_hud_text(
			"Urban Sim Lab\n\n需要通过命令行传入 runtime pack:\n-- --pack-dir /abs/path/to/pack"
		)
		print("No runtime pack specified. Pass one with: -- --pack-dir /abs/path/to/pack")
		return

	var loader := RuntimePackLoader.new()
	var pack := loader.load_pack(pack_dir)
	if pack.is_empty():
		push_error("Failed to load runtime pack: %s" % pack_dir)
		_set_hud_text("Failed to load runtime pack:\n%s" % pack_dir)
		return

	var summary := loader.populate_scene(self, pack)
	_fit_camera_to_world(pack.get("world", {}).get("bounds", {}))
	print("Loaded runtime pack: %s" % pack.get("manifest", {}).get("pack_id", "<unknown>"))
	print(summary)

	if _extract_bool_arg("--run-sim", true):
		_run_simulation_replay(pack)
	else:
		_set_hud_text(_format_static_status(pack, summary))


func _process(_delta: float) -> void:
	if _replay_player == null or _hud_label == null:
		return
	_set_hud_text(_format_replay_status(_replay_player.get_status()))


func _unhandled_input(event: InputEvent) -> void:
	if _replay_player == null:
		return
	if not (event is InputEventKey):
		return
	var key_event: InputEventKey = event as InputEventKey
	if not key_event.pressed or key_event.echo:
		return

	match key_event.keycode:
		KEY_SPACE:
			_replay_player.toggle_playing()
		KEY_R:
			_replay_player.restart()
		KEY_MINUS:
			_replay_player.set_playback_speed(_replay_player.get_playback_speed() / 2.0)
		KEY_EQUAL, KEY_PLUS:
			_replay_player.set_playback_speed(_replay_player.get_playback_speed() * 2.0)
		KEY_COMMA:
			_replay_player.step_once(-1)
		KEY_PERIOD:
			_replay_player.step_once(1)


func _run_simulation_replay(pack: Dictionary) -> void:
	var simulator := SimulationCore.new()
	var steps := _extract_int_arg("--steps", 300)
	var delta_seconds := _extract_float_arg("--delta", 1.0)
	var seed := _extract_int_arg("--seed", 1337)
	var replay_stride := _extract_int_arg("--replay-stride", 1)
	var result := simulator.simulate(
		pack,
		steps,
		delta_seconds,
		seed,
		{
			"record_replay": true,
			"replay_stride": replay_stride
		}
	)
	if not bool(result.get("ok", false)):
		var error_message := str(result.get("error", "<unknown>"))
		push_error("Simulation failed: %s" % error_message)
		_set_hud_text("Simulation failed:\n%s" % error_message)
		return

	var replay: Dictionary = result.get("replay", {})
	if replay.is_empty():
		push_error("Simulation did not produce replay payload")
		_set_hud_text("Simulation finished without replay payload")
		return

	var replay_out := _extract_string_arg("--replay-out", "")
	if not replay_out.is_empty():
		var resolved_output := _resolve_output_path(replay_out)
		_write_json_file(resolved_output, replay)
		print("Replay written to: %s" % resolved_output)

	if _replay_player != null:
		remove_child(_replay_player)
		_replay_player.queue_free()

	_replay_player = ReplayPlayer.new()
	_replay_player.name = "ReplayPlayer"
	add_child(_replay_player)
	_replay_player.load_replay(replay)
	_replay_player.set_playback_speed(_extract_float_arg("--replay-speed", DEFAULT_REPLAY_SPEED))
	_replay_player.set_playing(not _extract_bool_arg("--start-paused", false))

	var metrics: Dictionary = result.get("metrics", {})
	print("Scenario replay ready")
	print(JSON.stringify(metrics))
	print("Controls: Space play/pause | R restart | +/- speed | ,/. step")


func _ensure_debug_environment() -> void:
	if not has_node(DEBUG_SUN_NAME):
		var sun := DirectionalLight3D.new()
		sun.name = DEBUG_SUN_NAME
		sun.rotation_degrees = Vector3(-58.0, 35.0, 0.0)
		sun.light_energy = 1.8
		add_child(sun)

	if not has_node(DEBUG_ENVIRONMENT_NAME):
		var world_environment := WorldEnvironment.new()
		world_environment.name = DEBUG_ENVIRONMENT_NAME
		var environment := Environment.new()
		environment.background_mode = Environment.BG_COLOR
		environment.background_color = Color(0.92, 0.95, 0.98)
		environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		environment.ambient_light_color = Color(0.84, 0.88, 0.92)
		environment.ambient_light_energy = 0.9
		world_environment.environment = environment
		add_child(world_environment)

	if not has_node(DEBUG_CAMERA_NAME):
		var camera := Camera3D.new()
		camera.name = DEBUG_CAMERA_NAME
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.near = 0.1
		camera.far = 4096.0
		camera.current = true
		add_child(camera)


func _fit_camera_to_world(bounds: Dictionary) -> void:
	if bounds.is_empty():
		return
	var camera := get_node_or_null(DEBUG_CAMERA_NAME) as Camera3D
	if camera == null:
		return
	var min_x := float(bounds.get("min_x", -10.0))
	var max_x := float(bounds.get("max_x", 10.0))
	var min_z := float(bounds.get("min_z", -10.0))
	var max_z := float(bounds.get("max_z", 10.0))
	var width: float = max(10.0, max_x - min_x)
	var depth: float = max(10.0, max_z - min_z)
	var longest_axis: float = max(width, depth)
	var center := Vector3((min_x + max_x) / 2.0, 0.0, (min_z + max_z) / 2.0)
	camera.size = longest_axis * 0.62
	camera.position = center + Vector3(0.0, longest_axis * 1.6 + 180.0, 0.0)
	camera.look_at(center, Vector3.FORWARD)


func _ensure_hud() -> void:
	if has_node(HUD_LAYER_NAME):
		var existing_layer := get_node(HUD_LAYER_NAME)
		if existing_layer.has_node(HUD_PANEL_NAME + "/" + HUD_LABEL_NAME):
			_hud_label = existing_layer.get_node(HUD_PANEL_NAME + "/" + HUD_LABEL_NAME) as Label
		return

	var hud_layer := CanvasLayer.new()
	hud_layer.name = HUD_LAYER_NAME
	add_child(hud_layer)

	var panel := PanelContainer.new()
	panel.name = HUD_PANEL_NAME
	panel.offset_left = 16.0
	panel.offset_top = 16.0
	panel.offset_right = 520.0
	panel.offset_bottom = 300.0
	hud_layer.add_child(panel)

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 12)
	margin.add_theme_constant_override("margin_top", 10)
	margin.add_theme_constant_override("margin_right", 12)
	margin.add_theme_constant_override("margin_bottom", 10)
	panel.add_child(margin)

	var label := Label.new()
	label.name = HUD_LABEL_NAME
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	margin.add_child(label)
	_hud_label = label


func _set_hud_text(text: String) -> void:
	if _hud_label == null:
		return
	_hud_label.text = text


func _format_static_status(pack: Dictionary, summary: Dictionary) -> String:
	var pack_id := str(pack.get("manifest", {}).get("pack_id", "<unknown>"))
	return (
		"Urban Sim Lab\n"
		+ "Pack: %s\n" % pack_id
		+ "Static preview loaded\n"
		+ "Buildings: %d  Zones: %d  Props: %d\n" % [
			int(summary.get("building_count", 0)),
			int(summary.get("zone_count", 0)),
			int(summary.get("prop_count", 0))
		]
		+ "North is screen-up in the orthographic view\n"
		+ "Pass --run-sim false to keep static preview only"
	)


func _format_replay_status(status: Dictionary) -> String:
	if not bool(status.get("has_replay", false)):
		return "Urban Sim Lab\nReplay unavailable"

	var counts: Dictionary = status.get("counts", {})
	var metrics: Dictionary = status.get("metrics", {})
	var recent_events: Array = status.get("recent_events", [])
	var recent_event_text := "No events yet"
	if not recent_events.is_empty():
		recent_event_text = "\n".join(recent_events)

	return (
		"Urban Sim Lab Replay\n"
		+ "North is screen-up\n"
		+ "Step: %d  Time: %.1fs / %.1fs\n" % [
			int(status.get("step", 0)),
			float(status.get("time_seconds", 0.0)),
			float(status.get("duration_seconds", 0.0))
		]
		+ "Playback: %s  Speed: %.2fx\n" % [
			"playing" if bool(status.get("playing", false)) else "paused",
			float(status.get("speed", 1.0))
		]
		+ "Active C/I/M: %d / %d / %d\n" % [
			int(counts.get("active_civilians", 0)),
			int(counts.get("active_infected", 0)),
			int(counts.get("active_military", 0))
		]
		+ "Evacuated: %d  Converted: %d  Neutralized: %d\n" % [
			int(counts.get("evacuated_count", 0)),
			int(counts.get("converted_count", 0)),
			int(counts.get("neutralized_count", 0))
		]
		+ "Final evacuated ratio: %.2f  Final conversion ratio: %.2f\n" % [
			float(metrics.get("evacuated_ratio", 0.0)),
			float(metrics.get("conversion_ratio", 0.0))
		]
		+ "Controls: Space play/pause | R restart | +/- speed | ,/. step\n"
		+ "Recent events:\n%s" % recent_event_text
	)


func _write_json_file(path: String, payload: Dictionary) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("Failed to write replay JSON: %s" % path)
		return
	file.store_string(JSON.stringify(payload, "  "))


func _resolve_output_path(path: String) -> String:
	if path.is_absolute_path():
		return path
	if path.begins_with("user://") or path.begins_with("res://"):
		return ProjectSettings.globalize_path(path)
	return ProjectSettings.globalize_path("res://".path_join(path))


func _extract_string_arg(flag: String, fallback: String) -> String:
	var args := OS.get_cmdline_user_args()
	for index in range(args.size()):
		if args[index] == flag and index + 1 < args.size():
			return args[index + 1]
	return fallback


func _extract_bool_arg(flag: String, fallback: bool) -> bool:
	var raw := _extract_string_arg(flag, "")
	if raw.is_empty():
		return fallback
	return not (raw.to_lower() in ["0", "false", "no", "off"])


func _extract_int_arg(flag: String, fallback: int) -> int:
	var raw := _extract_string_arg(flag, "")
	if raw.is_empty():
		return fallback
	return int(raw)


func _extract_float_arg(flag: String, fallback: float) -> float:
	var raw := _extract_string_arg(flag, "")
	if raw.is_empty():
		return fallback
	return float(raw)
