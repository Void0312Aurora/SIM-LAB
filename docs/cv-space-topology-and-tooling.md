# CV 空间拓扑方案与开源工具部署

## 1. 文档目的

本文档用于把项目的数据主线从“路网优先”调整为“空间拓扑优先”，并给出第一批可直接部署的开源 CV / 遥感工具。

目标不是立刻做出高精复原，而是先建立一条可以在低到中等分辨率卫星图上工作的工程路线：

- 提取建筑占据区
- 提取开放空间与步行候选面
- 提取障碍边界和连通口
- 为后续区域图、可见性分析和简化 3D 体块提供基础

## 2. 方向结论

当前 MVP 更关心：

- 空间是否连通
- 哪些区域可走、不可走、半可走
- 建筑与空地如何分布
- 哪些位置是瓶颈、入口、围栏口、校门、广场、走廊

因此，`roads / roads_walk` 不应再被视为唯一骨架。

更合理的主线是：

`影像 / 静态图 -> CV 分割 -> 空间层 -> 区域连通图 -> 派生路网 / 派生导航图`

## 3. 工程目标分层

### 3.1 MVP 目标

只依赖公开影像或静态图，先构造：

- `building_footprints`
- `open_space_mask`
- `walkable_surface`
- `barrier_lines`
- `portal_candidates`
- `region_graph`
- `building_massing_stub`

### 3.2 后续增强目标

在 MVP 之上增加：

- 建筑类别识别
- 入口候选点
- 校门、围栏缺口、桥、连廊
- 粗高度估计
- 代表性建筑的简化 3D 体块

### 3.3 暂不作为首发目标

- 精确室内结构恢复
- 高精立面生成
- 单靠单张卫星图完成高可信 3D 资产
- 用消费级导航结果直接替代空间拓扑真值

## 4. 推荐开源项目

### 4.1 第一优先级：`SamGeo / segment-geospatial`

用途：

- 基于 `SAM` 的地理影像交互式分割
- 适合快速提取建筑、广场、操场、水体、绿地、开放空间
- 支持 `GeoTIFF`、矢量导出和 `QGIS` 工作流

为什么优先：

- 上手成本低
- 适合提示式分割
- 很适合作为第一版“空间层提取器”

建议用法：

- 手动或半自动提取校园核心建筑和开放空间
- 先做几个局部 patch，验证空间层是否足够支持模拟

来源：

- <https://github.com/opengeos/segment-geospatial>
- <https://samgeo.gishub.org/>

### 4.2 第二优先级：`Raster Vision`

用途：

- 遥感 CV 训练与推理框架
- 支持语义分割、目标检测、数据切片与地理输出

为什么适合：

- 当我们从“交互式提取”转向“批处理和训练”时，它是比较稳的工程骨架
- 适合构建项目自己的 `walkable / barrier / building` 分类器

建议用法：

- 第二阶段建立训练管线
- 用项目自己的校园样本微调分割模型

来源：

- <https://rastervision.io/>
- <https://docs.rastervision.io/en/stable/framework/quickstart.html>

### 4.3 第三优先级：`TorchGeo`

用途：

- 面向地理遥感任务的 `PyTorch` 框架

为什么适合：

- 适合长期沉淀训练代码、数据集定义和评估逻辑
- 比 `Raster Vision` 更底层、更灵活

建议用法：

- 当我们开始维护自己的训练集和模型时接入

来源：

- <https://torchgeo.org/>
- <https://torchgeo.readthedocs.io/>

### 4.4 研究增强：`GeoSAM`

用途：

- 面向 `mobility infrastructure segmentation` 的研究型项目
- 更贴近道路、步行基础设施和交通设施分割

为什么值得关注：

- 它和“空间拓扑优先”的目标相近
- 适合做道路/步行候选层的补强实验

限制：

- 更偏研究原型
- 开箱稳定性与文档成熟度不如 `SamGeo`

来源：

- <https://github.com/rafiibnsultan/GeoSAM>

### 4.5 数据与基准：`OpenEarthMap`、`SpaceNet`

用途：

- 提供高分辨率遥感分割与道路/建筑提取基准

为什么重要：

- 它们不是直接部署到项目里的“产品工具”
- 但很适合作为训练、评估和任务定义参考

来源：

- <https://open-earth-map.org/overview_oem.html>
- <https://spacenet.ai/datasets/>
- <https://spacenet.ai/sn5-challenge/>

### 4.6 3D 路线：`OpenDroneMap`、`COLMAP`、`Meshroom`

用途：

- 多视图摄影测量与 3D 重建

当前判断：

- 如果只有卫星图或静态图，它们不是主线工具
- 如果未来获得多视角地面图或无人机图，这批工具再进入主线

来源：

- <https://docs.opendronemap.org/>
- <https://github.com/colmap/colmap>
- <https://github.com/alicevision/Meshroom>

## 5. 项目内推荐部署顺序

### 阶段 1：快速实验

部署：

- `SamGeo`
- 基础 GIS 依赖
- 本地影像检查脚本

目标：

- 手工/提示式提取建筑与开放空间
- 验证是否能构造第一版 `space topology`

### 阶段 2：批处理化

部署：

- `Raster Vision`
- `TorchGeo`
- 项目自己的数据样本与标签目录

目标：

- 把第一阶段的手工成果转成训练样本
- 跑第一版校园分割模型

### 阶段 3：高级增强

部署：

- `GeoSAM`
- 额外的道路/步行基础设施实验模型

目标：

- 补强入口、围栏口、校园小路等细粒度结构

## 6. 当前推荐策略

第一阶段直接采用：

1. `OSM` 保留为语义和基础几何参考
2. `SamGeo` 作为主 CV 工具
3. `reference image overlay` 继续保留，用于人工校核
4. `manual overlay` 作为关键拓扑修订层

也就是说：

- `OSM` 不是唯一真值
- `route API` 不再作为主路网来源
- `CV` 负责更贴近模拟目标的空间结构提取

## 7. 数据输出建议

CV 层不应直接输出运行时路网，而应优先输出：

- `occupancy_mask`
- `building_polygons`
- `walkable_polygons`
- `barrier_lines`
- `portal_candidates`
- `region_graph`

之后再派生：

- `nav_pedestrian`
- `nav_vehicle`
- `building_massing`

## 8. 与项目示例的关系

像《Infection Free Zone》这类作品，更像是在消费真实地理空间的“简化结构”而不是精确 GIS 真值。

对我们来说，最值得学习的不是它是否精确复原，而是：

- 它把复杂现实空间压缩成了可模拟的简单结构
- 它优先保留了空间关系，而不是高保真视觉

这正是当前阶段最适合我们的方向。

## 9. 当前落地决定

仓库内将新增 `image/cv/` 实验骨架，包含：

- 环境部署脚本
- 推荐依赖清单
- 影像检查脚本
- 数据目录约定

优先目标不是训练一个完整模型，而是：

- 确认现有影像输入质量
- 跑通一个最小空间分割实验
- 确认输出是否足够支撑 `space topology schema v1`
