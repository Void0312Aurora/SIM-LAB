# Blender Authoring

本目录预留给 Blender 自动化脚本和模板文件。

建议后续放置：

- 建筑体块挤出脚本
- 道路与人行道 mesh 生成脚本
- 程序化道具摆放脚本
- glTF 导出脚本

推荐工作流：

1. `pipeline/` 输出规范化几何和语义数据
2. Blender 脚本读取这些数据
3. 生成或修饰网格
4. 导出 `glTF` 给 `Godot` 运行时加载

当前已包含：

- `scripts/smoke_test.py`
