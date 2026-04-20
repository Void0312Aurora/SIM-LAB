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
