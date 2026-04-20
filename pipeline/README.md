# Pipeline

这里放置 Python 离线城市编译器。

第一阶段建议包含这些模块：

- `ingest`: 拉取和缓存公开数据
- `normalize`: 统一坐标系、清洗几何、构建 canonical schema
- `derive`: 生成导航图、用途标签、封锁点、安全区等语义资产
- `build`: 生成可供运行时加载的 mesh 和数据包
- `analytics`: 对实验输出做批处理和统计

当前已实现的最小命令：

```bash
python -m urban_sim_lab_pipeline normalize-osm \
  --config /abs/path/to/config.json \
  --normalized-root /abs/path/to/data/normalized \
  --raw-root /abs/path/to/data/raw
```

```bash
python -m urban_sim_lab_pipeline validate-json \
  --schema /abs/path/to/schema.json \
  --input /abs/path/to/document.json
```

```bash
python -m urban_sim_lab_pipeline validate-runtime-pack \
  --pack-dir /abs/path/to/data/runtime/pack_id
```

```bash
python -m urban_sim_lab_pipeline build-runtime-pack \
  --normalized-city-dir /abs/path/to/data/normalized/city_id \
  --output-root /abs/path/to/data/runtime \
  --scenario /abs/path/to/scenario.json
```

```bash
python -m urban_sim_lab_pipeline preview-normalized-city \
  --normalized-city-dir /abs/path/to/data/normalized/city_id \
  --output-html /abs/path/to/reports/preview.html
```

```bash
python -m urban_sim_lab_pipeline clip-normalized-city \
  --normalized-city-dir /abs/path/to/data/normalized/city_id \
  --polygon-config /abs/path/to/configs/overlays/clip.local.json \
  --output-dir /abs/path/to/data/normalized/city_id_clipped
```

```bash
python -m urban_sim_lab_pipeline import-tencent-place-search \
  --normalized-city-dir /abs/path/to/data/normalized/city_id \
  --input-json /abs/path/to/data/research/tencent/raw/place_search.json \
  --output-bundle /abs/path/to/data/research/tencent/derived/place_search.bundle.json
```

```bash
python -m urban_sim_lab_pipeline import-tencent-route \
  --normalized-city-dir /abs/path/to/data/normalized/city_id \
  --input-json /abs/path/to/data/research/tencent/raw/walk_route.json \
  --output-bundle /abs/path/to/data/research/tencent/derived/walk_route.bundle.json
```

```bash
python -m urban_sim_lab_pipeline augment-normalized-city \
  --normalized-city-dir /abs/path/to/data/normalized/city_id \
  --enhancement-bundle /abs/path/to/data/research/tencent/derived/place_search.bundle.json \
  --output-dir /abs/path/to/data/normalized/city_id_enhanced
```

```bash
python -m urban_sim_lab_pipeline audit-route-building-conflicts \
  --normalized-city-dir /abs/path/to/data/normalized/city_id \
  --enhancement-bundle /abs/path/to/data/research/tencent/derived/walk_route.bundle.json \
  --output-json /abs/path/to/reports/route_building_audit.json
```

```bash
python -m urban_sim_lab_pipeline fetch-static-research-image \
  --provider tencent \
  --center-lat 30.556000 \
  --center-lng 104.001000 \
  --zoom 17 \
  --maptype satellite \
  --size 512*512 \
  --env-file /abs/path/to/.env \
  --output /abs/path/to/data/research/tencent/raw/chengdu_scu_jiangan_satellite.png \
  --report /abs/path/to/reports/tencent_satellite_fetch.json
```

```bash
python -m urban_sim_lab_pipeline build-tianditu-reference-mosaic \
  --normalized-city-dir /abs/path/to/data/normalized/chengdu_scu_jiangan_core_clipped_v1 \
  --overlay-polygon /abs/path/to/configs/overlays/chengdu_scu_jiangan_campus_core_v1.local.json \
  --env-file /abs/path/to/.env \
  --output-image /abs/path/to/data/research/tdt/derived/chengdu_scu_jiangan_core_tdt_img_cia_z17.png \
  --output-config /abs/path/to/configs/references/chengdu_scu_jiangan_core_tdt_img_cia_z17.local.json \
  --report /abs/path/to/reports/chengdu_scu_jiangan_core_tdt_img_cia_z17.json
```

推荐先用这个样例配置：

- `../configs/areas/chengdu_scu_jiangan_core.json`

当前输出：

- `city_manifest.json`
- `roads.json`
- `buildings.json`
- 空占位层文件：`pedestrian_areas.json`、`landuse.json`、`poi.json`、`barriers.json`

当前还支持：

- 使用 `schemas/json/*.schema.json` 做 JSON schema 校验
- 从规范化城市目录构建最小 `runtime pack`
- 对完整 runtime pack 目录做一键校验
- 生成规范化城市数据的本地 HTML 预览
- 使用本地坐标 polygon 对规范化城市包做裁剪
- 叠加本地参考图层与 enhancement bundle 做研究预览
- 将腾讯地点搜索和路线规划 JSON 导入为本地米制增强包
- 将增强包合并成新的 `normalized city` 副本
- 审计导入路线是否与建筑 footprint 发生穿模几何冲突
- 抓取腾讯/天地图研究底图并输出脱敏抓取报告
- 用天地图 WMTS 自动拼接参考底图并生成 reference-image config
