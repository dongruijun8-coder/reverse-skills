# 知识反馈规则 — Agent 自主更新知识库

Agent 在逆向过程中发现新模式/突破时，**不直接修改正式 KB 文件**，而是提交提案到 `kb/_proposals/`。

## 触发条件

### 1. 新签名模式 (new_pattern → sign_patterns.md)
- **触发:** 当前 Pattern KB 中无匹配，但 Agent 成功提取并验证了签名算法
- **验证要求:** crypto_sign_verify 至少 3 个不同请求返回 match
- **提案文件:** `kb/_proposals/{date}-sign-{pattern_name}.json`
- **示例:** 发现 `SHA256(body + key)` 而 KB 只有 MD5 模式

### 2. 新加密模式 (new_pattern → crypto_patterns.md)
- **触发:** crypto_detection 识别出 KB 中未列出的加密模式
- **验证要求:** crypto_aes/crypto_rc4/crypto_rsa 成功解密真实响应
- **提案文件:** `kb/_proposals/{date}-crypto-{algo}.json`
- **示例:** 发现 AES-GCM 模式（当前 KB 只有 ECB/CBC）

### 3. 新加固方案 (packer_update → packer_patterns.md)
- **触发:** apk_detect_packer 发现未知特征 .so 文件
- **验证要求:** 确认该 .so 属于加固产品（非普通 native lib）
- **提案文件:** `kb/_proposals/{date}-packer-{name}.json`
- **示例:** 检测到 libnaga.so → 确认为网易易盾

### 4. 反模式突破 (correction → anti_patterns.md)
- **触发:** 之前标记为反模式的操作，在新版本/新场景下成功
- **验证要求:** 该操作在至少 2 次独立尝试中成功
- **提案文件:** `kb/_proposals/{date}-anti_pattern_update-{name}.json`
- **示例:** 360加固 v12.0 Frida attach 不再崩溃（旧版 2 秒 SIGSEGV）

### 5. 退出条件修正 (correction → exit_conditions.md)
- **触发:** L1-L5 退出规则在实战中表现不当（过早/过晚退出）
- **提案文件:** `kb/_proposals/{date}-exit_condition-{issue}.json`
- **示例:** L4 "所有策略耗尽" 太早触发——应该先尝试组合策略

### 6. 新认证模式 (new_pattern → auth_flow_patterns.md)
- **触发:** 发现 Pattern KB 中未列出的认证流程
- **验证要求:** 完整认证链通过，返回真实数据
- **提案文件:** `kb/_proposals/{date}-auth-{pattern_name}.json`

## Agent 行为

### Phase 3-4 完成后检查：
```
FOR each finding that doesn't match any existing KB pattern:
  1. Check if already in kb/_proposals/ (avoid duplicates)
  2. Write proposal JSON with full evidence
  3. Log to audit.jsonl: KB_PROPOSAL event
  4. Output notification: "📝 发现新模式 → kb/_proposals/{file}"
```

### Phase 5 完成后：
```
IF any proposals written this session:
  List all proposals in final summary
  Suggest user review and merge
```

## 提案引用

Agent 在启动时加载 `kb/_proposals/`：
- `confirmed` 提案 → 视同正式 pattern，参与匹配
- `suspected` 提案 → 仅作为参考，不加权
- `anti_pattern` 提案 → 视同正式反模式，直接使用

## 人工合并

用户定期 review `kb/_proposals/`，将验证过的提案合并到正式 KB，删除已合并的提案文件。
