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
- `scripts/runtime_pack_loader.gd`
- `scripts/runtime_pack_smoke_test.gd`

最小运行示例：

```bash
godot --headless --path /abs/path/to/runtime/godot \
  --script res://scripts/runtime_pack_smoke_test.gd -- \
  --pack-dir /abs/path/to/data/runtime/pack_id
```

第一版场景模拟 smoke test：

```bash
godot --headless --path /abs/path/to/runtime/godot \
  --script res://scripts/scenario_simulation_smoke_test.gd -- \
  --pack-dir /abs/path/to/data/runtime/pack_id \
  --steps 300 \
  --delta 1.0 \
  --seed 1337
```

当前模拟是最小原型：

- `civilians` 会沿步行图向最近的 `safe_zone / evac_point` 移动
- `infected` 会沿步行图追逐最近的平民
- `military` 会以检查点为基地，对响应半径内感染者进行追击
