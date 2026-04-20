# Tencent Research

建议放置：

- `raw/`
  - 地点搜索响应
  - 路线规划响应
  - 静态底图 PNG 或错误响应快照
- `notes/`
  - 查询关键词
  - 坐标范围
  - 访问日期
  - key 与权限说明
- `derived/`
  - enhancement bundle
  - 人工筛选后的校核结果

推荐文件名：

- `raw/chengdu_scu_jiangan_place_search.json`
- `raw/chengdu_scu_jiangan_walk_route.json`
- `raw/chengdu_scu_jiangan_tx_satellite.png`
- `derived/chengdu_scu_jiangan_places.bundle.json`
- `derived/chengdu_scu_jiangan_walk_route.bundle.json`

注意：

- 原始腾讯响应默认只用于本地研究
- 静态底图抓取报告应当脱敏，不要把 key 直接写进提交物
- 进入 `normalized/` 的应当是项目自己的派生结果，而不是原始接口数据
