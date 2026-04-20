# 工程阶段计划

## 1. 文档目的

本文档用于从工程和代码实现角度定义项目的阶段拆分、模块任务、完成标准、依赖关系与当前状态。

它服务于两个目标：

- 让项目进度可被持续判断，而不是停留在抽象讨论
- 让后续实现优先级稳定，不因想法扩张导致主线失焦

## 2. 当前定位

当前项目处于：

- `预制作后期`
- `技术原型早期`

当前已经完成的底座工作：

- 项目方向和技术路线已收敛
- `Godot + Blender + Python` 工具链已接通
- 第一批 schema 已建立
- OSM 到规范化城市包的最小导入链已跑通
- 最小 runtime pack 构建已跑通
- JSON schema 校验命令已接入

当前尚未进入的阶段：

- Blender 自动资产导出
- NPC 生成、移动和模拟规则
- 回放与结果分析
- 真实地图数据的首次人工真实性校核

## 3. 系统拆分

从代码和工程职责上，项目当前拆为 8 个模块：

1. 数据接入模块 `pipeline.ingest`
2. 规范化模块 `pipeline.normalize`
3. 语义推导模块 `pipeline.derive`
4. 运行包构建模块 `pipeline.runtime_pack`
5. Blender 资产编译模块 `authoring.blender`
6. Godot 场景加载模块 `runtime.godot.loader`
7. 模拟核心模块 `runtime.godot.simulation`
8. 回放与分析模块 `runtime.godot.replay` / `pipeline.analytics`

## 4. 阶段划分

### 阶段 A：项目冻结与数据契约

目标：

- 冻结首发方向、首发地图、首发技术栈和首发不做项
- 冻结第一批 schema 和中间数据分层

主要任务：

- 编写冻结基线文档
- 固定首发地图选址
- 固定首批 schema 范围
- 固定最小闭环目标

完成标准：

- 有书面冻结文档
- 有首发地图配置文件
- 有明确的不做项列表

当前状态：

- `已完成`

### 阶段 B：规范化城市数据闭环

目标：

- 让一个真实区域稳定导入为规范化城市包

主要任务：

- 完成 bbox 配置输入
- 接入 OSM 下载和缓存
- 输出 `city_manifest.json`
- 输出 `roads.json`
- 输出 `buildings.json`
- 输出占位层 `landuse/poi/barriers/pedestrian_areas`

完成标准：

- 一条命令能稳定产出规范化城市目录
- 关键元数据满足 schema

当前状态：

- `已完成最小版本`

后续补强任务：

- `landuse`
- `poi`
- `barriers`
- `pedestrian_areas`
- 更稳定的字段映射和置信度记录

### 阶段 C：schema 校验与运行包闭环

目标：

- 让规范化数据可以被显式验证，并转换为运行时资产包

主要任务：

- 接入 `validate-json`
- 接入 `build-runtime-pack`
- 输出 `manifest/world/buildings/zones/nav/scenario`
- 为关键产物建立 schema

完成标准：

- `normalized city` 可校验
- `scenario` 可校验
- `runtime pack manifest` 可校验
- `nav graph` 可校验

当前状态：

- `已完成最小版本`

后续补强任务：

- 为 `world/buildings/zones/props` 增加正式 schema
- 增强 zone 和 graph 的语义精度

### 阶段 D：Godot 场景加载闭环

目标：

- 让 Godot 直接加载 runtime pack 并显示真实场景

主要任务：

- 编写 runtime pack loader
- 将 `world/buildings/zones/nav` 映射为 Godot 节点
- 提供基础调试图层
- 提供地图边界和对象可视化

完成标准：

- 一条命令可以启动 Godot 并显示目标区域
- 场景中能看见建筑、道路边界和调试信息

当前状态：

- `已启动，最小加载与调试层已接通`

当前已完成：

- Godot 可读取 `runtime pack`
- 可显示地面、建筑、区域提示
- 可显示地图边界和导航图调试线
- 已有 headless smoke test 可做基础回归

剩余关键任务：

- 将道路表面从 runtime pack 中显式可视化
- 增加开关式调试图层控制
- 建立相机、光照和观察入口
- 为四川大学江安校区数据做首次真实性校核

依赖：

- 阶段 B
- 阶段 C

### 阶段 E：Blender 资产编译闭环

目标：

- 把规范化几何转成真正可渲染的基础网格资产

主要任务：

- 建筑体块挤出
- 道路和人行道 mesh 生成
- glTF 导出
- 建立 Godot 侧 `mesh_ref` 约定

完成标准：

- 至少一版建筑和道路资产可通过 Blender 自动导出
- Godot 能加载对应 glTF

当前状态：

- `已启动，最小图上实体模拟已接通`

当前已完成：

- 可从 `scenario.spawn_rules` 生成平民、感染者、军队三类实体
- 可基于 `nav_pedestrian` 做最小路径跟随
- 可消费 `safe_zone / evac_point / military_control / outbreak_origin`
- 已有 Godot headless 模拟 smoke test

剩余关键任务：

- 将实体运动可视化接入常规场景而不只是 headless 脚本
- 为不同 faction 增加更明确的状态切换与参数配置
- 让 `nav_vehicle` 与军队/封锁逻辑发生更真实的耦合
- 将模拟事件显式输出为可记录结果

依赖：

- 阶段 B
- 阶段 C

### 阶段 F：实体与导航基础闭环

目标：

- 让 NPC 能够在地图上生成、寻路和移动

主要任务：

- 读取 `nav_pedestrian` 和 `nav_vehicle`
- 生成平民、感染者、军队三类实体
- 实现基础路径跟随
- 实现最小状态机

完成标准：

- 三类实体可在地图上移动
- 行为切换可被调试和观察

当前状态：

- `已启动最小原型`

当前已完成：

- 最小感染扩散
- 基于安全区和疏散点的平民撤离
- 基于检查点的军队响应
- 基于时间步推进的 headless 模拟闭环

剩余关键任务：

- 加入恐慌、拥堵、封锁失败等更细行为规则
- 让感染、拦截、疏散对路径选择产生反馈
- 输出可比较的模拟结果指标

依赖：

- 阶段 D

### 阶段 G：模拟规则闭环

目标：

- 让一局模拟可以完整跑完

主要任务：

- 感染扩散
- 恐慌状态
- 封锁节点控制
- 安全区和疏散目标
- 事件触发和时间推进

完成标准：

- 一次完整模拟可运行
- 不同参数下会出现可观察差异

当前状态：

- `未开始`

依赖：

- 阶段 F

### 阶段 H：回放与分析闭环

目标：

- 让模拟结果可以被回放、比较和分析

主要任务：

- 轨迹记录
- 事件记录
- 热力图
- 统计指标
- 回放控制

完成标准：

- 至少一局模拟可复盘
- 有基础统计结果输出

当前状态：

- `未开始`

依赖：

- 阶段 G

## 5. 当前模块状态表

| 模块 | 当前状态 | 说明 |
| --- | --- | --- |
| `pipeline.ingest` | 已有最小能力 | 已能通过 OSMnx 拉取 OSM 数据 |
| `pipeline.normalize` | 已有最小能力 | 已能输出 roads/buildings/manifest |
| `pipeline.derive` | 未开始 | 语义层仍未正式实现 |
| `pipeline.runtime_pack` | 已有最小能力 | 已能输出最小 runtime pack |
| `authoring.blender` | 仅 smoke test | 还未开始真正资产构建 |
| `runtime.godot.loader` | 已有最小能力 | 已能读取 runtime pack 并做基础场景映射 |
| `runtime.godot.simulation` | 已有最小能力 | 已有 headless 图上实体模拟与 smoke test |
| `runtime.godot.replay` | 未开始 | 尚无回放与统计 |

## 6. 最近三阶段的实际工作重点

当前最值得推进的顺序是：

1. 把 headless 模拟结果可视化接入常规 Godot 场景
2. 实现 Blender 建筑体块和道路 mesh 导出
3. 为模拟补事件记录与结果分析

原因：

- 这三项一旦打通，项目就会从“图上数据原型”进入“可观察的游戏原型”

## 7. 当前结论

如果用工程语言来定义当前进度：

- 数据底座已经建立
- 运行时边界已经建立
- 已进入“可运行模拟”的最小闭环阶段
- 但还没有进入“具备正式可视表现和结果分析”的阶段

所以当前阶段最重要的不是继续扩想法，而是把：

- runtime pack
- Godot simulation
- Blender mesh/export

这三者连接起来。
