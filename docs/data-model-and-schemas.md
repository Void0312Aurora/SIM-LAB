# 数据模型与 Schema 设计

## 1. 文档目的

本文档定义项目第一阶段的数据设计原则、中间数据层、运行时资产包结构，以及首批 schema 的边界。

目标是先把“数据契约”定稳，再去写导入器、生成器和运行时加载器。

## 2. 设计原则

- `engine-agnostic`
  - 离线编译器输出的数据不能绑定某个引擎专有格式
  - `Godot` 是当前首选运行时，但 schema 应保持可被其他运行时复用

- `事实与推导分离`
  - 原始真实世界数据、规则推导结果、ML 补全结果要分开表达

- `结构先于表现`
  - 第一版优先保存道路、建筑、导航、区域语义和事件配置
  - 贴图、立面细节和高保真资产不是首批 schema 核心

- `可追溯`
  - 每个重要对象应尽量带有 `source`、`confidence`、`last_updated` 等字段

- `本地坐标优先`
  - 输入数据可保留原始经纬度
  - 规范化层和运行时层统一使用局部投影平面坐标，单位为米

## 3. 数据层次

第一阶段建议把数据拆成三层：

1. 原始数据层
2. 规范化城市层
3. 运行时资产包层

### 3.1 原始数据层

放在 `data/raw/`，内容包括：

- OSM / Overture 原始文件
- DEM / 栅格数据
- 人口或地址数据
- 街景特征数据

这一层不做 schema 强约束，只记录来源和快照。

### 3.2 规范化城市层

放在 `data/normalized/`，用于统一多源数据。

这一层是 Python 管线的 canonical model，建议包含：

- `city_manifest.json`
- `roads.json`
- `pedestrian_areas.json`
- `buildings.json`
- `landuse.json`
- `poi.json`
- `barriers.json`
- `terrain.json`

### 3.3 运行时资产包层

放在 `data/runtime/`，由 `Godot` 直接加载。

建议包含：

- `manifest.json`
- `world.json`
- `buildings.json`
- `zones.json`
- `nav_pedestrian.json`
- `nav_vehicle.json`
- `props.json`
- `scenario.json`
- `meshes/*.gltf`

## 4. 坐标与单位约定

### 4.1 输入层

- 原始 GIS 数据可保留 `WGS84` 经纬度

### 4.2 规范化层

- 所有几何统一投影到局部平面坐标
- 单位统一为米
- 推荐为每个街区选择一个本地投影 CRS，并记录在 manifest 中

### 4.3 运行时层

为了与 `Godot` 对齐，建议运行时使用：

- `x`: 东西方向
- `z`: 南北方向
- `y`: 高度

也就是说：

- 2D GIS 平面坐标 `(x, y)` 进入运行时时应映射为 `(x, 0, z)`
- 建筑高度、地形高度映射到 Godot 的 `y`

## 5. ID 与命名约定

建议统一使用稳定字符串 ID：

- `road_<source>_<id>`
- `building_<source>_<id>`
- `zone_<type>_<serial>`
- `poi_<source>_<id>`
- `scenario_<name>`

规则：

- ID 一旦进入规范化层，后续尽量保持稳定
- 如果对象由多源合并而来，应在 provenance 字段中保留原始来源列表

## 6. 规范化城市数据模型

### 6.1 `city_manifest.json`

建议包含：

- `city_id`
- `display_name`
- `bbox_wgs84`
- `local_crs`
- `origin`
- `units`
- `sources`
- `compiled_at`

### 6.2 `roads.json`

建议一条道路最少包含：

- `id`
- `class`
- `name`
- `centerline`
- `lanes`
- `width_m`
- `is_vehicle_accessible`
- `is_pedestrian_accessible`
- `source`
- `confidence`

### 6.3 `buildings.json`

建议一栋建筑最少包含：

- `id`
- `footprint`
- `height_m`
- `levels`
- `usage_class`
- `entrances`
- `capacity_estimate`
- `source`
- `confidence`

### 6.4 `landuse.json`

建议包含：

- `id`
- `class`
- `polygon`
- `source`

### 6.5 `poi.json`

建议包含：

- `id`
- `class`
- `name`
- `position`
- `linked_building_id`
- `source`

### 6.6 `barriers.json`

建议包含：

- `id`
- `class`
- `geometry`
- `blocks_pedestrians`
- `blocks_vehicles`

## 7. 运行时资产包模型

### 7.1 `manifest.json`

记录运行时资产包元信息：

- `pack_id`
- `city_id`
- `runtime_target`
- `schema_version`
- `compiled_at`
- `source_manifest`
- `assets`

### 7.2 `world.json`

描述运行时世界骨架：

- 地形边界
- 水体
- 绿地
- 围栏与大型障碍
- 地表类型区块

### 7.3 `buildings.json`

描述运行时建筑对象：

- `id`
- `mesh_ref`
- `footprint`
- `height_m`
- `usage_class`
- `entrances`
- `capacity_estimate`
- `occlusion_class`

### 7.4 `zones.json`

描述模拟关键区域：

- `safe_zone`
- `evac_point`
- `military_control`
- `outbreak_origin`
- `high_density_area`

### 7.5 `nav_pedestrian.json` 与 `nav_vehicle.json`

建议使用显式图结构：

- `nodes`
- `edges`
- `cost`
- `width_m`
- `capacity`
- `blocked`

### 7.6 `props.json`

描述程序化摆放的轻量道具：

- `id`
- `class`
- `transform`
- `variant`
- `blocks_movement`

### 7.7 `scenario.json`

描述单次模拟输入：

- `scenario_id`
- `map_pack_id`
- `time_of_day`
- `civilian_count`
- `infected_count`
- `military_units`
- `spawn_rules`
- `win_or_observation_goals`

## 8. Provenance 与置信度

建议在建筑、道路、区域和 POI 等关键对象上统一保留：

- `source.provider`
- `source.dataset`
- `source.record_id`
- `confidence`
- `derived_from`

这样后续能分清：

- 哪些字段来自 OSM
- 哪些字段来自规则推导
- 哪些字段来自 ML 补全

## 9. 第一批 schema 范围

第一批建议先落这四份 schema：

1. `normalized-city.schema.json`
2. `runtime-pack-manifest.schema.json`
3. `nav-graph.schema.json`
4. `scenario.schema.json`

原因是这四个文件已经能锁定：

- 规范化层入口
- 运行时资产包入口
- 导航数据结构
- 模拟配置结构

## 10. 后续可扩展 schema

第二批可以继续补：

- `buildings.schema.json`
- `world.schema.json`
- `zones.schema.json`
- `props.schema.json`
- `simulation-results.schema.json`
- `replay-events.schema.json`

## 11. 当前建议

当前最重要的不是一次写完整个数据宇宙，而是先把最小闭环打通：

- 一份规范化城市描述
- 一份运行时包 manifest
- 一份导航图
- 一份场景配置

只要这四个契约稳定，我们就可以开始写：

- 地图导入器
- 规范化转换器
- `Godot` 运行时加载器
- 基础 NPC 模拟系统
