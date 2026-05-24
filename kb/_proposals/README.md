# KB 更新提案 (Knowledge Base Update Proposals)

Agent 在逆向过程中发现新模式时，将提案写入此目录，而非直接修改正式 KB 文件。

## 提案格式

每个提案一个 `.json` 文件，命名：`{YYYY-MM-DD}-{简短描述}.json`

## 合并流程

1. Agent 发现新模式 → 写入提案
2. 后续逆向任务先查 `_proposals/`（非正式但已验证）
3. 用户定期 review → 正式合并到 patterns/ → 删除提案

## 提案优先级

- **confirmed**: 已验证通过（sign_verify / decrypt 成功），可放心引用
- **suspected**: 观察到的模式但未验证，仅供参考
- **anti_pattern**: 新发现的反模式
