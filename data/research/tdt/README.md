# TianDiTu Research

建议放置：

- `raw/`
  - 北向朝上的底图或影像截图
  - 查询参数记录
- `notes/`
  - 获取日期
  - 图层类型
  - 缩放级别
  - 截图范围说明
- `derived/`
  - 拼接后的 WMTS 参考底图
  - 对齐后的参考配置
  - 人工校核记录

推荐文件名：

- `raw/chengdu_scu_jiangan_core_tdt_vector.png`
- `raw/chengdu_scu_jiangan_core_tdt_imagery.png`
- `derived/chengdu_scu_jiangan_core_tdt_img_cia_z17.png`
- `derived/chengdu_scu_jiangan_core_tdt_img_cia_z17.local.json`

注意：

- 参考图层应保持 `north-up`
- `WMTS` 比静态截图更适合做可复现的本地研究底图
- 不建议将原始瓦片直接沉淀进公开仓库
