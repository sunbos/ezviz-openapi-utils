# S018B 云录制2.0原文独立复核

固定devin/swe-2、effort=max。只读本文件及input.json。禁止写文件/命令/联网/配置/凭据。将10篇原文每篇核对为JSON对象，输出单个JSON围栏，不推断海外同路径支持，不以旧utils作为依据，不宣称实测。

输出{"documents":[{"doc_id":str,"method":str,"path":str,"token_location":"header", "body_encoding":"unknown"或"form_urlencoded", "code_path":str,"success_values":[],"message_path":str,"data_path":"data","parameters":[{"name":str,"location":str,"type":str,"required":bool}],"limits":[str],"contradictions":[str]}],"cross_product_notes":[str]}。

方法/路径/位置以原文说明和示例交叉核对，找出相互矛盾处，不统一不同响应结构。Header大小写无关但保留源拼写。响应示例缺message不意味应改成msg；meta规则可按同页示例和返回表明确，若根本未声明message记作"meta.message"并在contradictions注明路径只属SDK同系列约定、原页无字段保证。查询2051/4382以实际顶层code字符串200，不猜meta。3974保留跨open_vod、托管/子账户限制及48小时，不添加源未声明的busType参数。参数表为原始业务约束，日期时区若未写则明确未定义。不要复制任何示例设备ID/Token/所有者ID到输出。
