# Parallel Execution Rules

## When to Split
- No data dependency between tasks
- Input set can be independently partitioned (different files / different analysis dimensions)
- Single task estimated > 15 seconds

## When NOT to Split
- Strict sequential dependency (Phase 4 auth chain)
- Splitting overhead > parallel benefit (small files, simple tasks)
- Requires sharing large context between agents

## Limits
- Max 5 parallel agents per Phase
- JS files > 3 AND total > 200KB → split by file (one agent per file)
- JS files ≤ 3 OR total ≤ 200KB → single agent

## Agent Dispatch
- Use Claude Code Agent tool: `Agent(description="...", prompt="...", run_in_background=true)`
- Each sub-agent prompt must be self-contained (no conversation history dependency)
- Sub-agent prompt must specify: exact file paths, expected output format, tool restrictions

## Timeout & Recovery
- Single agent timeout: 120 seconds
- On timeout → kill agent → mark timed_out → decide retry/reassign/skip
- Other agents continue independently

## Merge Rules (conflicting results from multiple agents)
- Sort by confidence (from confidence_rules.json) → pick highest
- If confidence equal → verify with crypto_sign_verify → pick passing one
- If both pass → pick simpler code
- If neither passes → loop back to Phase 3 with more context
