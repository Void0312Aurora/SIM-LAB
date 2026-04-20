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
- `scripts/replay_player.gd`
- `scripts/scenario_replay_export_smoke_test.gd`

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

第一版 replay 导出 smoke test：

```bash
godot --headless --path /abs/path/to/runtime/godot \
  --script res://scripts/scenario_replay_export_smoke_test.gd -- \
  --pack-dir /abs/path/to/data/runtime/pack_id \
  --steps 300 \
  --delta 1.0 \
  --seed 1337 \
  --replay-out /abs/path/to/reports/replays/pack_id_replay.json
```

可视化回放入口：

```bash
godot --path /abs/path/to/runtime/godot -- \
  --pack-dir /abs/path/to/data/runtime/pack_id \
  --steps 300 \
  --delta 1.0 \
  --seed 1337 \
  --replay-speed 6.0
```

当前模拟是最小原型：

- `civilians` 会沿步行图向最近的 `safe_zone / evac_point` 移动
- `infected` 会沿步行图追逐最近的平民
- `military` 会以检查点为基地，对响应半径内感染者进行追击
- `SimulationCore` 可输出逐帧 replay、事件日志和 agent manifest
- `ReplayPlayer` 会在常规 Godot 场景中回放实体轨迹

当前回放控制：

- `Space`: 播放 / 暂停
- `R`: 从头重放
- `+ / -`: 调整回放速度
- `, / .`: 单帧前进 / 后退

当前回放入口支持的常用参数：

- `--run-sim false`: 只看静态 runtime pack，不执行模拟
- `--replay-speed <float>`: 设置播放倍速
- `--replay-stride <int>`: 每隔多少 simulation step 记录一帧
- `--start-paused true`: 启动后暂停在首帧
- `--replay-out <path>`: 启动场景时同步导出 replay JSON
