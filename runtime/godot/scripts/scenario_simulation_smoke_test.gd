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
	var simulator := SimulationCore.new()
	var result: Dictionary = simulator.simulate(pack, steps, delta_seconds, seed)
	if not bool(result.get("ok", false)):
		push_error("Simulation failed: %s" % str(result.get("error", "<unknown>")))
		quit(1)
		return

	var metrics: Dictionary = result.get("metrics", {})
	var event_total := int(metrics.get("evacuated_count", 0)) + int(metrics.get("converted_count", 0)) + int(metrics.get("neutralized_count", 0))
	if event_total <= 0:
		push_error("Simulation produced no observable events")
		quit(1)
		return

	print("Urban Sim Lab scenario simulation smoke test OK")
	print(pack.get("manifest", {}).get("pack_id", "<unknown>"))
	print(JSON.stringify(metrics))
	quit()


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
