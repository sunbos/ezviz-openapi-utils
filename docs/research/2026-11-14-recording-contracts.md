# 本地录像查询的地区差异

来源为归档的[国内3922](https://open.ys7.com/help/3922)与[海外2867](https://open.ys7.com/help/en/2867)，正文已按catalog中的SHA-256重新校验。尚无真实录像调用结果。

| 项目 | 国内 | 海外 |
| --- | --- | --- |
| GET路径 | /api/v3/device/local/video/unify/query | /api/v3/das/device/local/video/query |
| Header | accessToken、deviceSerial、可选localIndex | accessToken、deviceSerial、可选channelNo |
| 时间 | 起止必填，10位数字字符串示例，同一天且有序 | 起止分别可选，YYYY-MM-DD HH:MM:SS |
| recordType | 1–5 | 1–4 |
| 地区特有选项 | pageSize、isQueryByNvr、location | 未声明这些选项 |
| data | records、hasMore、nextFileTime等组成的对象 | 录像片段数组 |

两端都明确展示整数meta.code=200，消息位于meta.message。海外错误表存在两列码，但未说明独立设备码在JSON中的路径；SDK不猜造双层解码路径。

国内Unix秒解释依据10位数值示例推断，平台同日边界的时区也未明确，均保留为待实测事项。SDK要求国内传aware datetime并使用其明确时区校验日期，海外传naive datetime保留服务器wall time；不静默删除或推断时区。两个入口都不自动分页、不播放或下载录像。
