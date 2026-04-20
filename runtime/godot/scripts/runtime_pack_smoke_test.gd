extends SceneTree

const RuntimePackLoader = preload("res://scripts/runtime_pack_loader.gd")


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var pack_dir := _extract_pack_dir()
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

	var root := Node3D.new()
	root.name = "RuntimePackRoot"
	get_root().add_child(root)
	var summary := loader.populate_scene(root, pack)
	await process_frame
	print("Urban Sim Lab runtime pack smoke test OK")
	print(pack.get("manifest", {}).get("pack_id", "<unknown>"))
	print(summary)
	get_root().remove_child(root)
	root.free()
	await process_frame
	quit()


func _extract_pack_dir() -> String:
	var args := OS.get_cmdline_user_args()
	for index in range(args.size()):
		if args[index] == "--pack-dir" and index + 1 < args.size():
			return args[index + 1]
	return ""
