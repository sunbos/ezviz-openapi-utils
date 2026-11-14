# H005B：核心业务评测用例生成器

固定devin/swe-2，effort=max。只读本文件、docs/coordination/H005A/request.md、本目录input.json、tests/test_sdk_{devices,management,ptz,cruise,diagnostics,settings,imaging,auth,auth_models}.py。必要时可读src/ezviz_unified/cruise.py里的CruisePeriod定义，但不能调用SDK来录制期望。禁止写文件/命令/网络/配置/账号访问。

输出一个完整Python围栏，作为本目录case_builder.py，定义build_cases(contracts, bindings)->list[dict]。输入是本目录input.json的contracts/bindings列表，仅为分配到的子集；每个operation_id必须正好一个完整case，不允许skip、空占位或从运行时SDK采样期望。未知绑定必须抛ValueError而非悄悄遗漏。只导入标准库，不导入SDK/pytest/测试模块，不发请求或写文件。

case格式和占位/DTO规则完全遵循H005A/request.md。fields为独立期望wire值，位置由reviewed contract提供；不要含accessToken。表单或query可用str/int，bool应明确写为0/1或"0"/"1"。auth两项允许空args/kwargs/fields且data=null，runner专项验证。其他case必须基于已审核单测的合法调用和期望字段，尤其注意channel vs channelNo、header/query差异、result/meta包、settings的switch常量、imaging的setting常量、托管list的version3.0、国内pageSize默认字段。

使用H005A合成上下文或EVAL/TEST标记的假数据；绝不复制官网真实示例凭证/设备号。从tests取调用结构和wire期望即可，不复制测试代码执行。create/bind等验证码可用ABCDEF，名字用eval_name。查询data使用非空合成JSON以检查透传；可含page之外的标记，但raw由runner构造；setter可data=null。涉及JSON form字段（例如timerDefenceQos）提供对象/数组作为fields值，并在json_fields列名，runner进行结构比较。CruisePeriod用DTO标签，不真正创建实例。

可以用按public_entry分派的小字典/辅助函数、按region分支和binding.argument_constants生成case，减少重复；不能给所有参数机械填1或生成无效调用。返回case列表排序稳定，长度必须等于bindings。输出完整可运行的纯生成器代码，不宣称测试已通过。
