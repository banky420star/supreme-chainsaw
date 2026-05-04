---
name: Session filter disabled-session bug
description: _check_session_filter cannot block trading — disabled sessions produce empty matching_sessions which defaults to allowed
type: project
---

_check_session_filter in Python/mt5_executor.py has a logic bug: when all sessions covering a given hour are disabled, `matching_sessions` is empty and the method returns `(True, "ok")` — identical to "no session covers this hour." This means disabling all sessions does NOT block trading. The method can never return `(False, ...)` under any configuration.

**Why:** The `matching_sessions` list only gets entries when a session is BOTH in-range AND enabled. The early-return on line 228-229 (`if not matching_sessions: return True, "ok"`) was intended for hours outside any session range (21-23 UTC), but it also fires when all applicable sessions are disabled.

**How to apply:** If the intent is that disabled sessions should block trading, the code needs a separate check for "hour falls in a session range but that session is disabled." A fix would track which sessions *cover* the hour regardless of enabled status, then check if any of those are enabled. Only if no session covers the hour at all should trading default to allowed.

Also found: `active_session` variable (lines 204-210) is dead code — set but never read.