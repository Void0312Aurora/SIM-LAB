class_name RuntimePackLoader
extends RefCounted

const GENERATED_ROOT_NAME := "GeneratedRuntimePack"


func _read_json(path: String) -> Variant:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		push_error("Failed to open JSON file: %s" % path)
		return null
	var text := file.get_as_text()
	var json := JSON.new()
	var error := json.parse(text)
	if error != OK:
		push_error("Failed to parse JSON file: %s (%s at line %d)" % [path, json.get_error_message(), json.get_error_line()])
		return null
	return json.data


func load_pack(pack_dir: String) -> Dictionary:
	var manifest: Variant = _read_json(pack_dir.path_join("manifest.json"))
	if manifest == null:
		return {}
	var assets: Dictionary = manifest.get("assets", {})
	var pack := {
		"pack_dir": pack_dir,
		"manifest": manifest,
		"world": _read_json(pack_dir.path_join(assets.get("world", "world.json"))),
		"buildings": _read_json(pack_dir.path_join(assets.get("buildings", "buildings.json"))),
		"zones": _read_json(pack_dir.path_join(assets.get("zones", "zones.json"))),
		"nav_pedestrian": _read_json(pack_dir.path_join(assets.get("nav_pedestrian", "nav_pedestrian.json"))),
		"nav_vehicle": _read_json(pack_dir.path_join(assets.get("nav_vehicle", "nav_vehicle.json"))),
		"props": _read_json(pack_dir.path_join(assets.get("props", "props.json"))),
		"scenario": _read_json(pack_dir.path_join(assets.get("scenario", "scenario.json")))
	}
	for key in ["world", "buildings", "zones", "nav_pedestrian", "nav_vehicle", "props", "scenario"]:
		if pack.get(key) == null:
			push_error("Runtime pack is missing or has invalid data for: %s" % key)
			return {}
	return pack


func populate_scene(root: Node3D, pack: Dictionary) -> Dictionary:
	_clear_generated(root)
	var generated := Node3D.new()
	generated.name = GENERATED_ROOT_NAME
	root.add_child(generated)

	var world_root := Node3D.new()
	world_root.name = "World"
	generated.add_child(world_root)
	var buildings_root := Node3D.new()
	buildings_root.name = "Buildings"
	generated.add_child(buildings_root)
	var zones_root := Node3D.new()
	zones_root.name = "Zones"
	generated.add_child(zones_root)
	var nav_root := Node3D.new()
	nav_root.name = "Navigation"
	generated.add_child(nav_root)
	var props_root := Node3D.new()
	props_root.name = "Props"
	generated.add_child(props_root)

	var world: Dictionary = pack.get("world", {})
	_add_ground(world_root, world.get("bounds", {}))
	_add_bounds_outline(world_root, world.get("bounds", {}))

	var building_count := 0
	for building in pack.get("buildings", []):
		if building is Dictionary:
			buildings_root.add_child(_make_building_node(building))
			building_count += 1

	var zone_count := 0
	for zone in pack.get("zones", []):
		if zone is Dictionary:
			zones_root.add_child(_make_zone_node(zone))
			zone_count += 1

	var pedestrian_nav_summary := _add_nav_graph(
		nav_root,
		"PedestrianGraph",
		pack.get("nav_pedestrian", {}),
		Color(0.15, 0.8, 0.35),
		0.15
	)
	var vehicle_nav_summary := _add_nav_graph(
		nav_root,
		"VehicleGraph",
		pack.get("nav_vehicle", {}),
		Color(0.2, 0.55, 0.95),
		0.35
	)

	var prop_count := 0
	for prop in pack.get("props", []):
		if prop is Dictionary:
			props_root.add_child(_make_prop_node(prop))
			prop_count += 1

	return {
		"building_count": building_count,
		"zone_count": zone_count,
		"prop_count": prop_count,
		"pedestrian_node_count": pedestrian_nav_summary.get("node_count", 0),
		"pedestrian_edge_count": pedestrian_nav_summary.get("edge_count", 0),
		"vehicle_node_count": vehicle_nav_summary.get("node_count", 0),
		"vehicle_edge_count": vehicle_nav_summary.get("edge_count", 0)
	}


func _clear_generated(root: Node) -> void:
	if not root.has_node(GENERATED_ROOT_NAME):
		return
	var generated := root.get_node(GENERATED_ROOT_NAME)
	root.remove_child(generated)
	generated.free()


func _make_standard_material(color: Color, transparency: float = 1.0) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	if transparency < 1.0:
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.albedo_color.a = transparency
	return material


func _make_debug_line_material(color: Color) -> StandardMaterial3D:
	var material := _make_standard_material(color)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	return material


func _add_ground(parent: Node3D, bounds: Dictionary) -> void:
	if bounds.is_empty():
		return
	var size_x: float = max(1.0, float(bounds.get("max_x", 0.0)) - float(bounds.get("min_x", 0.0)))
	var size_z: float = max(1.0, float(bounds.get("max_z", 0.0)) - float(bounds.get("min_z", 0.0)))
	var center_x: float = (float(bounds.get("min_x", 0.0)) + float(bounds.get("max_x", 0.0))) / 2.0
	var center_z: float = (float(bounds.get("min_z", 0.0)) + float(bounds.get("max_z", 0.0))) / 2.0

	var ground_mesh := BoxMesh.new()
	ground_mesh.size = Vector3(size_x, 0.1, size_z)

	var ground := MeshInstance3D.new()
	ground.name = "Ground"
	ground.mesh = ground_mesh
	ground.position = Vector3(center_x, -0.05, center_z)
	ground.material_override = _make_standard_material(Color(0.16, 0.18, 0.16))
	parent.add_child(ground)


func _add_bounds_outline(parent: Node3D, bounds: Dictionary) -> void:
	if bounds.is_empty():
		return
	var min_x: float = float(bounds.get("min_x", 0.0))
	var max_x: float = float(bounds.get("max_x", 0.0))
	var min_z: float = float(bounds.get("min_z", 0.0))
	var max_z: float = float(bounds.get("max_z", 0.0))
	var y := 0.03
	var corners := [
		Vector3(min_x, y, min_z),
		Vector3(max_x, y, min_z),
		Vector3(max_x, y, max_z),
		Vector3(min_x, y, max_z)
	]
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_LINES, _make_debug_line_material(Color(0.95, 0.95, 0.4)))
	for index in range(corners.size()):
		mesh.surface_add_vertex(corners[index])
		mesh.surface_add_vertex(corners[(index + 1) % corners.size()])
	mesh.surface_end()

	var instance := MeshInstance3D.new()
	instance.name = "BoundsOutline"
	instance.mesh = mesh
	parent.add_child(instance)


func _make_building_node(building: Dictionary) -> Node3D:
	var points: Array = building.get("footprint", [])
	var min_x := INF
	var max_x := -INF
	var min_z := INF
	var max_z := -INF
	for point in points:
		if point is Array and point.size() >= 2:
			var x := float(point[0])
			var z := float(point[1])
			min_x = min(min_x, x)
			max_x = max(max_x, x)
			min_z = min(min_z, z)
			max_z = max(max_z, z)
	if min_x == INF:
		min_x = 0.0
		max_x = 1.0
		min_z = 0.0
		max_z = 1.0
	var width: float = max(1.0, max_x - min_x)
	var depth: float = max(1.0, max_z - min_z)
	var height: float = max(1.0, float(building.get("height_m", 9.0)))

	var mesh := BoxMesh.new()
	mesh.size = Vector3(width, height, depth)

	var instance := MeshInstance3D.new()
	instance.name = str(building.get("id", "Building"))
	instance.mesh = mesh
	instance.position = Vector3((min_x + max_x) / 2.0, height / 2.0, (min_z + max_z) / 2.0)
	instance.material_override = _make_standard_material(Color(0.55, 0.65, 0.8))
	return instance


func _make_zone_node(zone: Dictionary) -> Node3D:
	var radius: float = max(1.0, float(zone.get("radius_m", 10.0)))
	var center: Dictionary = zone.get("center", {"x": 0.0, "y": 0.0, "z": 0.0})

	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = 0.25

	var instance := MeshInstance3D.new()
	instance.name = str(zone.get("id", "Zone"))
	instance.mesh = mesh
	instance.position = Vector3(float(center.get("x", 0.0)), float(center.get("y", 0.0)) + 0.125, float(center.get("z", 0.0)))
	instance.material_override = _make_standard_material(Color(0.9, 0.45, 0.2), 0.45)
	return instance


func _add_nav_graph(
	parent: Node3D,
	graph_name: String,
	graph: Dictionary,
	color: Color,
	y_offset: float
) -> Dictionary:
	var graph_root := Node3D.new()
	graph_root.name = graph_name
	parent.add_child(graph_root)

	var node_positions := _index_graph_nodes(graph)
	var edges: Array = graph.get("edges", [])
	if node_positions.is_empty() or edges.is_empty():
		return {
			"node_count": node_positions.size(),
			"edge_count": 0
		}

	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_LINES, _make_debug_line_material(color))
	var edge_count := 0
	for edge in edges:
		if not edge is Dictionary:
			continue
		var from_id := str(edge.get("from", ""))
		var to_id := str(edge.get("to", ""))
		if not node_positions.has(from_id) or not node_positions.has(to_id):
			continue
		var start: Vector3 = node_positions[from_id] + Vector3(0.0, y_offset, 0.0)
		var ending: Vector3 = node_positions[to_id] + Vector3(0.0, y_offset, 0.0)
		mesh.surface_add_vertex(start)
		mesh.surface_add_vertex(ending)
		edge_count += 1
	mesh.surface_end()

	var instance := MeshInstance3D.new()
	instance.name = "Edges"
	instance.mesh = mesh
	graph_root.add_child(instance)

	return {
		"node_count": node_positions.size(),
		"edge_count": edge_count
	}


func _index_graph_nodes(graph: Dictionary) -> Dictionary:
	var node_positions := {}
	for node in graph.get("nodes", []):
		if not node is Dictionary:
			continue
		var node_id := str(node.get("id", ""))
		if node_id.is_empty():
			continue
		node_positions[node_id] = _dict_to_vec3(node.get("position", {}))
	return node_positions


func _dict_to_vec3(source: Dictionary) -> Vector3:
	return Vector3(
		float(source.get("x", 0.0)),
		float(source.get("y", 0.0)),
		float(source.get("z", 0.0))
	)


func _make_prop_node(prop: Dictionary) -> Node3D:
	var transform_data: Dictionary = prop.get("transform", {})
	var position: Dictionary = transform_data.get("position", {"x": 0.0, "y": 0.0, "z": 0.0})
	var scale_data: Dictionary = transform_data.get("scale", {"x": 1.0, "y": 1.0, "z": 1.0})

	var mesh := BoxMesh.new()
	mesh.size = Vector3(1.0, 1.0, 1.0)

	var instance := MeshInstance3D.new()
	instance.name = str(prop.get("id", "Prop"))
	instance.mesh = mesh
	instance.position = Vector3(float(position.get("x", 0.0)), float(position.get("y", 0.0)) + 0.5, float(position.get("z", 0.0)))
	instance.scale = Vector3(float(scale_data.get("x", 1.0)), float(scale_data.get("y", 1.0)), float(scale_data.get("z", 1.0)))
	instance.material_override = _make_standard_material(Color(0.85, 0.75, 0.35))
	return instance
