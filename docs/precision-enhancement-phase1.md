# 精度增强 Phase 1

## 1. 目的

本阶段用于在不推翻 `OSM` 主骨架的前提下，为江安校区核心区接入第一批“研究增强层”能力。

目标不是立即获得一个完美、完整、可公开分发的高精地图，而是：

- 给当前 `normalized city` 增加更强的本地校核能力
- 为 `POI`、步行路线和人工语义修订预留正式导入路径
- 让增强结果可以先在预览页观察，再决定是否并入主包

## 2. 当前实现

当前已经落地的能力：

1. `preview-normalized-city` 支持：
   - `--reference-image-config`
   - `--enhancement-bundle`
2. 新增 `import-tencent-place-search`
3. 新增 `import-tencent-route`
4. 新增 `augment-normalized-city`

## 3. 推荐工作流

### 3.1 天地图参考层

用途：

- 校核道路、地块、水体与建筑分布
- 作为校园核心区真实性判断的人工参考

步骤：

1. 使用 `WMTS` 自动拼接一张 `north-up` 的天地图参考图
2. 生成对应的 reference image config
3. 用预览命令叠加观察

命令：

```bash
python -m urban_sim_lab_pipeline build-tianditu-reference-mosaic \
  --normalized-city-dir /abs/path/to/data/normalized/chengdu_scu_jiangan_core_clipped_v1 \
  --overlay-polygon /abs/path/to/configs/overlays/chengdu_scu_jiangan_campus_core_v1.local.json \
  --env-file /abs/path/to/.env \
  --output-image /abs/path/to/data/research/tdt/derived/chengdu_scu_jiangan_core_tdt_img_cia_z17.png \
  --output-config /abs/path/to/configs/references/chengdu_scu_jiangan_core_tdt_img_cia_z17.local.json \
  --report /abs/path/to/reports/chengdu_scu_jiangan_core_tdt_img_cia_z17.json
```

```bash
python -m urban_sim_lab_pipeline preview-normalized-city \
  --normalized-city-dir /abs/path/to/data/normalized/chengdu_scu_jiangan_core_clipped_v1 \
  --output-html /abs/path/to/reports/previews/chengdu_scu_jiangan_core_research.html \
  --overlay-polygon /abs/path/to/configs/overlays/chengdu_scu_jiangan_campus_core_v1.local.json \
  --reference-image-config /abs/path/to/configs/references/chengdu_scu_jiangan_core_tdt_img_cia_z17.local.json
```

## 3.2 腾讯地点搜索导入

用途：

- 补充 `POI`
- 补充校门、功能点、园区子点
- 为建筑名称和入口候选点提供交叉参考

步骤：

1. 保存腾讯地点搜索 JSON 到：
   - `data/research/tencent/raw/`
2. 执行导入命令，生成 enhancement bundle
3. 在预览页叠加观察
4. 如果结果可信，再并入新的 `normalized city` 副本

导入命令：

```bash
python -m urban_sim_lab_pipeline import-tencent-place-search \
  --normalized-city-dir /abs/path/to/data/normalized/chengdu_scu_jiangan_core_clipped_v1 \
  --input-json /abs/path/to/data/research/tencent/raw/place_search.json \
  --output-bundle /abs/path/to/data/research/tencent/derived/chengdu_scu_jiangan_places.bundle.json
```

## 3.3 腾讯路线导入

用途：

- 补充或校核 `walk` 网络
- 作为校园内部真实通行组织的研究参考

导入命令：

```bash
python -m urban_sim_lab_pipeline import-tencent-route \
  --normalized-city-dir /abs/path/to/data/normalized/chengdu_scu_jiangan_core_clipped_v1 \
  --input-json /abs/path/to/data/research/tencent/raw/walk_route.json \
  --output-bundle /abs/path/to/data/research/tencent/derived/chengdu_scu_jiangan_walk_route.bundle.json \
  --route-index 0 \
  --route-mode walking
```

## 3.4 叠加多个增强包预览

```bash
python -m urban_sim_lab_pipeline preview-normalized-city \
  --normalized-city-dir /abs/path/to/data/normalized/chengdu_scu_jiangan_core_clipped_v1 \
  --output-html /abs/path/to/reports/previews/chengdu_scu_jiangan_core_research.html \
  --reference-image-config /abs/path/to/configs/references/chengdu_scu_jiangan_core_tdt_reference.local.json \
  --enhancement-bundle /abs/path/to/data/research/tencent/derived/chengdu_scu_jiangan_places.bundle.json \
  --enhancement-bundle /abs/path/to/data/research/tencent/derived/chengdu_scu_jiangan_walk_route.bundle.json
```

## 3.5 并入增强结果

如果增强层经过人工确认，可以生成一个新的增强版 `normalized city`：

```bash
python -m urban_sim_lab_pipeline augment-normalized-city \
  --normalized-city-dir /abs/path/to/data/normalized/chengdu_scu_jiangan_core_clipped_v1 \
  --enhancement-bundle /abs/path/to/data/research/tencent/derived/chengdu_scu_jiangan_places.bundle.json \
  --enhancement-bundle /abs/path/to/data/research/tencent/derived/chengdu_scu_jiangan_walk_route.bundle.json \
  --output-dir /abs/path/to/data/normalized/chengdu_scu_jiangan_core_clipped_v1_enhanced
```

## 3.6 Manual Bundle 与语义锚点

当参考图和在线增强层已经足够稳定后，可以补一层手工语义锚点：

- `safe_zone`
- `outbreak_origin`
- `military_control`
- `evac_point`
- `campus_gate_marker`

当前仓库提供：

- 模板：
  - `configs/enhancements/chengdu_scu_jiangan_manual_semantics_v1.template.local.json`
- 样例：
  - `configs/enhancements/chengdu_scu_jiangan_manual_semantics_v1.local.json`

推荐命令：

```bash
python -m urban_sim_lab_pipeline augment-normalized-city \
  --normalized-city-dir /abs/path/to/data/normalized/chengdu_scu_jiangan_core_clipped_v1 \
  --enhancement-bundle /abs/path/to/configs/enhancements/chengdu_scu_jiangan_manual_semantics_v1.local.json \
  --output-dir /abs/path/to/data/normalized/chengdu_scu_jiangan_core_clipped_v1_manual_semantics
```

这些手工 POI 可以附带：

- `runtime_zone`
- `runtime_prop`

这样它们会在 `build-runtime-pack` 阶段自动落成 `zones.json` 和 `props.json`。

然后可以直接用示例场景构建 runtime pack：

```bash
python -m urban_sim_lab_pipeline build-runtime-pack \
  --normalized-city-dir /abs/path/to/data/normalized/chengdu_scu_jiangan_core_clipped_v1_manual_semantics \
  --output-root /abs/path/to/data/runtime \
  --scenario /abs/path/to/scenarios/chengdu_scu_jiangan_core_outbreak_mvp.json
```

## 4. 文件格式

### 4.1 reference image config

要求：

- `coordinate_space = local_meters`
- 图像必须是 `north-up`
- `anchor_bounds` 用局部米制坐标表示截图覆盖范围

### 4.2 enhancement bundle

用于承载研究增强层，不直接等价于第三方原始响应。

当前支持层：

- `roads`
- `roads_walk`
- `pedestrian_areas`
- `landuse`
- `poi`
- `barriers`

## 5. 边界

本阶段的默认工程边界：

- `OSM` 仍然是主几何骨架
- 第三方服务原始返回值默认只放在 `data/research/raw/`
- 进入 `normalized/` 的只能是项目自己的派生结果
- 参考图层优先用于人工判断，不自动宣布其为“真值”

## 6. 下一步

当这条链稳定后，下一阶段建议做：

1. 加入手工 `manual bundle`
2. 给校门、检查点、爆发点和安全区建立人工语义锚点
3. 用增强后的 `walk` 网络支撑第一轮 NPC 逃生/追逐模拟
