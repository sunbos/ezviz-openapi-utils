# RAM子账户与授权模型

本批基于2026-11-14归档的国内649/777、说明68/69，以及海外485/487。新增11项地区契约，未实际创建、删除账号、签发子token或修改任何权限。来源哈希在S015A/B的source-provenance.json中保留。

## 端点与地区

入口为`client.subaccounts`，异步对应AsyncClient，所有方法返回ApiResponse：

| 方法 | 已审核地区 | 作用 |
| --- | --- | --- |
| create(account_name, password_digest) | 国内/海外 | 创建B模式子账户 |
| add_statement(account_id, statement) | 国内/海外 | 追加一条授权语句 |
| get(account_id=None, account_name=None) | 海外 | 查询子账户；两个筛选参数均为keyword-only |
| list(page_start=None, page_size=None) | 海外 | 单页查询，保留raw.page |
| change_password(account_id, old_password_digest, new_password_digest) | 海外 | 显式修改密码摘要 |
| set_policy(account_id, statements) | 海外 | 提交调用方完整权限策略 |
| remove_device_permissions(account_id, device_serial) | 海外 | 撤销一个设备相关的全部授权语句 |
| issue_token(account_id) | 海外 | 请求子账户访问凭证 |
| delete(account_id) | 海外 | 单次删除请求，无SDK后续清理 |

国内当前归档仅找到创建和追加权限这两个明确RAM端点；其他国内对应接口继续待查证，不从海外路径推定可用或不可用。所有调用均POST form、accessToken在form；仅get/list按既有规则允许过期token刷新后重试一次，其余操作不自动重放。

国内创建名限定4–40位ASCII字母、数字或下划线；海外只按其文档检查4–40字符和控制字符。get的两个筛选条件可以同时省略，适用于持有子账户token的自身查询；若使用其他主体，必填条件由平台判断。两个筛选同时提供时原样发送，由平台优先accountId。SDK不根据参数自动改变身份。

## 密码与策略

门面只接受32位小写hex摘要，不接收自动代算密码；形状校验不能证明摘要的来源。纯本地辅助函数严格采用官网`MD5(AppKey + '#' + 明文)`规则：

```python
from ezviz_unified import RamStatement, ram_password_digest

digest = ram_password_digest("APP_KEY_PLACEHOLDER", "PASSWORD_PLACEHOLDER", encoding="utf-8")
statement = RamStatement(("Get", "Real"), ("dev:DEVICE_SERIAL",))
```

encoding必填，因为原文未说明摘要输入的字符编码；示例UTF-8不构成服务器兼容性实测。输入不去空格、不缓存或记录。MD5在这里是既有接口格式，不用于应用自己的密码存储。

RamStatement将permissions/resources复制为tuple并隐藏repr，按Permission逗号字符串和Resource数组序列化为form内的JSON。仅校验`dev:<id>`、`cam:<id>:<channel>`结构，不转换通道数字、不规范权限大小写、不展开资源、不默认加入DevCtrl。国内68/69和海外487列表不完全一致，因此没有伪完整权限枚举；可授予的权限与资源组合由平台判断。DevCtrl本身涵盖平台当前及未来定义的控制权限，SDK不会自动选择它。

set_policy只提交显式给出的列表；空列表可被序列化，但不代表已证明平台接受或已知其清空语义。add_statement不会自动读取、合并或替换已有策略。

## Token与证据边界

issue_token返回的accessToken、expireTime、areaDomain原样保留。该页只给出13位expireTime示例，没有独立单位定义；SDK不自动转换期限、建立provider或将子token写回父客户端。调用方确认有效期与区域后，可用既有外部TokenProvider接口建立独立客户端，主体由调用方维护。

SDK对账号标识、账号名、密码摘要、policy/statement，以及其Resource内的设备标识做诊断脱敏；不会改写实际发送的JSON或资源顺序。返回data仍可能包含敏感凭证，应由调用方按访问凭证处理。

AuthenticationError.invalid_token记录原始10002的布尔语义，刷新逻辑使用该标记；账号名与状态码文本碰巧重合时，诊断脱敏也不会阻断只读请求的一次刷新。未脱敏错误码不会另行保存。

海外列表HTTP示例误写account/get、追加/删除权限示例多出等号，均以明确请求地址和参数表为准；这些问题与编码、权限列表、到期单位差异均登记在source-issues。辅助说明页的变化还需结合harness的unmapped项人工审查；当前直接绑定分析不是完整依赖图。
