# Exit Conditions — When to Stop, Degrade, or Escalate

## L1: Auto Retry
- **Trigger:** Operation failed, retry_count ≤ 3
- **Applies to:** Network timeout, adb disconnect, mitmproxy unresponsive, tool call error
- **Action:** Wait 2 seconds → retry same operation → increment retry_count
- **User visibility:** None (silent)

## L2: Strategy Degradation
- **Trigger:** All attempts at current strategy layer exhausted (retry_count > 3)
- **Action:** Record failure reason → switch to next fallback strategy → reset retry_count → log to workflow.json
- **User visibility:** ⚡ One-line notification
- **Example:** Frida attach ×3 fail → Frida Gadget → ×3 fail → LSPosed → ×3 fail → H5 static

## L3: Path Abandonment
- **Trigger:** All strategy layers for a Phase exhausted
- **Action:** Mark path as `exhausted` in strategy_stack → attempt alternative path → log warning
- **User visibility:** ⚡ One-line notification

## L4: Agent Pause
- **Trigger (any of):**
  1. All known strategies across all paths exhausted
  2. Physical operation needed (SMS code, QR scan, CAPTCHA)
  3. All confidence scores below suspicious threshold
  4. Unknown encryption/signature pattern detected
- **Action:** Save .agent_state.json → generate structured pause report → wait for user input
- **User visibility:** ⏸️ Full pause report (5-15 lines)

## L5: App Abandonment
- **Trigger:** User replies "skip"/"abort" to L4 pause, OR 24h timeout
- **Action:** Save all intermediate artifacts → write case with result "abandoned" → mark resumable
