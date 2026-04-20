# Godot Runtime

本目录预留给 Godot 工程。

建议第一阶段先实现：

1. 运行时资产包加载器
2. 静态场景生成
3. 时间控制与调试 UI
4. 平民、感染者、军队三类 NPC 的基础状态机
5. 回放、热力图和事件标记

当前建议通过命令行优先验证：

- `godot --headless --path <project> --script <script>`

这样更适合自动化测试和 agent 驱动调试。

当前已包含：

- `project.godot`
- `scenes/bootstrap.tscn`
- `scripts/smoke_test.gd`
