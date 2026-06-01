# Quality Gate Rules

## 全协议 config.json Quality
- 必须通过结构校验（5 个顶层字段全部存在且类型正确）
- meta.config_schema 必须为 "2.0"
- meta.platform 必须为 "Android"
- server.base_url 必须以 "https://" 开头
- server.default_headers 至少含 2 个字段，必须含 clienttype 和 appversion
- pipeline 四类处理器全部非 null
- pipeline.encryption: 字符串 "plaintext" 或 {plugin, params} 对象（非 frida-rpc）
- pipeline.signing: 字符串 "plaintext" 或 {plugin, params} 对象（非 frida-rpc）
- pipeline.auth: {plugin, params} 对象（非 frida-rpc）
- pipeline.messaging: 字符串或 {plugin, params} 对象
- endpoints.all_rooms 非 null，output_mapping 必须覆盖 id, name
- endpoints.ranking 非 null，output_mapping 必须覆盖 uid, nick
- 模板变量 {{...}} 引用字段必须在 output_mapping 或 runtime_config 中有定义
- body 中不确定的固定字段 → 填抓包中看到的字面值，不做猜测

## RPC config.json Quality (Auth-only / Full RPC)
- 全协议所有结构规则
- frida 顶层字段存在且: enabled=true, package 非空且为实际包名, device∈{usb,local}, script 为 .js 文件名
- frida.script 指向的 .js 文件存在且非空
- Auth-only: auth = {"plugin":"frida-rpc",...}; encryption + signing = 原生 processor (非 plaintext 非 frida-rpc)
- Full RPC: auth + messaging = {"plugin":"frida-rpc",...}; encryption + signing = "plaintext"
- frida_script.js: login() 存在，返回 {token, uid}；Auth-only 额外返回 {encryption_key, encryption_iv}
- frida_script.js: sendMessage() 仅在 Full RPC 模式存在，返回 {success}
- 方法引用闭环: pipeline 中所有 frida-rpc 引用的 rpc_method 必须在 script rpc.exports 中存在

## Pre-commit Gate
- 全协议: 所有结构校验通过 → Phase 5 SUCCESS
- RPC: 结构校验 + script 存在 + 方法引用闭环 → Phase 5 SUCCESS
- 任何校验失败 → 反馈回路到对应 Phase
