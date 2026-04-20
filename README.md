# Urban Sim Lab

一个以“现实城市/街区转游戏资源与群体行为模拟”为核心的项目草案。

当前阶段目标：

- 明确产品方向：游戏原型、模拟平台，或二者结合
- 讨论技术栈与资产生产流程
- 收敛首个最小可行版本（MVP）
- 建立离线编译器、资产编译器与运行时模拟器的工程骨架

项目想法文档见 [docs/idea.md](docs/idea.md)。
公开数据与资产流水线调研见 [docs/data-sources-and-asset-pipeline.md](docs/data-sources-and-asset-pipeline.md)。
第一版资产清单见 [docs/asset-inventory.md](docs/asset-inventory.md)。
技术栈与架构文档见 [docs/tech-stack-and-architecture.md](docs/tech-stack-and-architecture.md)。
数据模型与 schema 设计见 [docs/data-model-and-schemas.md](docs/data-model-and-schemas.md)。

当前仓库结构：

- `authoring/`: Blender 资产编译与自动化脚本
- `configs/`: 规则配置和映射表
- `data/`: 原始数据、规范化数据和运行时资产包
- `docs/`: 需求、调研和架构文档
- `pipeline/`: Python 离线城市编译器
- `runtime/`: Godot 运行时模拟器工程
- `scenarios/`: 场景配置
- `schemas/`: JSON schema 与数据结构定义
