extends SceneTree

const RuntimePackLoader = preload("res://scripts/runtime_pack_loader.gd")
const SimulationCore = preload("res://scripts/simulation_core.gd")


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var pack_dir := _extract_string_arg("--pack-dir", "")
	if pack_dir.is_empty():
		push_error("Missing --pack-dir argument")
		quit(1)
		return

	var loader := RuntimePackLoader.new()
	var pack := loader.load_pack(pack_dir)
	if pack.is_empty():
		push_error("Failed to load runtime pack: %s" % pack_dir)
		quit(1)
		return

	var steps := _extract_int_arg("--steps", 300)
	var delta_seconds := _extract_float_arg("--delta", 1.0)
	var seed := _extract_int_arg("--seed", 1337)
	var replay_stride := _extract_int_arg("--replay-stride", 1)
	var simulator := SimulationCore.new()
	var result: Dictionary = simulator.simulate(
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
		push_error("Simulation failed: %s" % str(result.get("error", "<unknown>")))
		quit(1)
		return

	var replay: Dictionary = result.get("replay", {})
	if replay.is_empty():
		push_error("Replay payload is empty")
		quit(1)
		return
	if (replay.get("frames", []) as Array).size() < 2:
		push_error("Replay payload has insufficient frames")
		quit(1)
		return
	if (replay.get("agent_manifest", []) as Array).is_empty():
		push_error("Replay payload has no agent manifest")
		quit(1)
		return

	var metrics: Dictionary = result.get("metrics", {})
	var event_total := int(metrics.get("evacuated_count", 0)) + int(metrics.get("converted_count", 0)) + int(metrics.get("neutralized_count", 0))
	if event_total <= 0:
		push_error("Replay payload contains no observable events")
		quit(1)
		return

	var replay_out := _extract_string_arg("--replay-out", "")
	if not replay_out.is_empty():
		var resolved_output := _resolve_output_path(replay_out)
		_write_json_file(resolved_output, replay)
		print("Replay written to: %s" % resolved_output)

	print("Urban Sim Lab replay export smoke test OK")
	print(pack.get("manifest", {}).get("pack_id", "<unknown>"))
	print(
		JSON.stringify(
			{
				"metrics": metrics,
				"frame_count": (replay.get("frames", []) as Array).size(),
				"event_count": (replay.get("events", []) as Array).size(),
				"agent_manifest_count": (replay.get("agent_manifest", []) as Array).size()
			}
		)
	)
	quit()


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
