# CV Lab

这个目录用于承接“空间拓扑优先”的影像实验。

当前推荐目标：

- 检查我们手上的影像质量
- 用开源分割工具提取建筑和开放空间
- 为后续 `walkable_surface / barriers / region_graph` 输出准备原始材料

## 目录约定

- `requirements/`
  - CV 实验依赖清单
- `scripts/`
  - 环境部署与影像检查脚本
- `workspace/`
  - 本地实验数据与缓存说明

## 推荐工作流

### 1. 部署最小 CV 环境

```bash
cd image/cv
bash scripts/bootstrap_cv_env.sh segmentation
```

默认会创建：

- `image/cv/.venv-segmentation`

如果你希望直接带上 `JupyterLab`，再用：

```bash
bash scripts/bootstrap_cv_env.sh segmentation-notebook
```

### 2. 检查影像质量

如果你手上有：

- `GeoTIFF`
- 带 worldfile 的 `PNG/JPG`
- 普通 `PNG/JPG`

都可以先跑检查脚本：

```bash
./.venv-segmentation/bin/python scripts/inspect_raster.py \
  --input /abs/path/to/image.tif
```

### 3. 决定实验类型

- 如果影像有地理参考：直接做地理分割实验
- 如果只有普通图片：先做视觉分割，再通过项目的 `reference image overlay` 完成人工配准

## 当前推荐部署顺序

### A. `segmentation`

推荐给第一轮实验：

- `segment-geospatial`
- `rasterio`
- `geopandas`
- `shapely`
- `pyproj`

用途：

- 快速分割建筑、操场、广场、开放地和障碍物候选层

说明：

- 这是更轻的默认环境
- 不默认带 `JupyterLab`
- 但 `SamGeo` 本身仍会拉取 `torch`，首次安装体积依然较大

### A2. `segmentation-notebook`

适合需要 notebook 交互实验时使用。

附加内容：

- `jupyterlab`
- `ipykernel`

### B. `training`

推荐给第二轮：

- `torchgeo`
- `rastervision`
- 训练与批处理依赖

用途：

- 做项目自己的校园场景微调和批量推理

## 当前不建议

- 一开始就把重心放在高精 3D 重建
- 一开始就要求自动识别全部入口、围栏缺口和室内结构
- 用导航路线结果直接替代空间拓扑
