# Data

本目录用于存放本地实验数据和编译中间产物。

建议后续细分为：

- `raw/`: 原始公开数据快照
- `normalized/`: 统一 schema 后的城市数据
- `runtime/`: 供 Godot 加载的运行时资产包
- `research/`: 仅供本地研究和核验使用的下载包与中间件

当前已约定的研究增强工作流见：

- `research/tdt/`: 天地图底图与影像参考
- `research/tencent/`: 腾讯地点搜索与路线规划研究导入

详细流程见：

- [docs/precision-enhancement-phase1.md](/home/void0312/Workshop/urban-sim-lab/docs/precision-enhancement-phase1.md)

这些目录默认不纳入版本管理。
