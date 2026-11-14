# 海外鉴权证据补充

完整文档采集后，已取得官方英文 [Get Access Token，文档473](https://open.ys7.com/help/en/473) 的正文。这补齐了首轮搜索调研中未能读取的认证协议，不代表已经完成真实账号调用。

本地证据：`data/official-docs/2026-11-14/pages/overseas/473.source.json`；请求原件与哈希位于同批次的 `sources/current/overseas-473.*`。

| 项目 | 文档内容 |
| --- | --- |
| 请求 | POST `https://open.ezvizlife.com/api/lapp/token/get` |
| 编码 | application/x-www-form-urlencoded |
| 必填Body | appKey、appSecret |
| 成功判断 | 顶层字符串 code="200" |
| 返回 | data.accessToken、data.expireTime、data.areaDomain |
| 过期时间 | 毫秒精度的时间戳 |
| 区域约束 | areaDomain 是用户所属区域的 Open API 域名，token 仅在该区域有效 |

实现据此读取实际 expireTime，并绑定返回的业务域名。文档没有在本页承诺固定7天生命周期，不能复制国内7天规则。示例中的美国区域域名不是所有海外账户的统一地址。

后续[真实联调](../validation/live/2026-11-14-overseas/README.md)发现：当前新加坡账号在上述默认入口返回10017，显式指定`https://isgpopen.ezvizlife.com`后认证成功，返回的业务域名为同一origin，设备列表成功且为空。失败与成功记录分开保存；这不是所有海外账号的入口映射证明，SDK不自动尝试其他区域。

用户暂时没有测试设备，当前继续离线开发。设备功能、其他海外集群与异步真实行为仍未验证。
