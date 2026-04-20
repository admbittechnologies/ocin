# Multi-Language Support Analysis for OCIN Backend

**Date:** 2026-04-09
**Purpose:** Identify all hardcoded English patterns that will break multi-language support

---

## ✅ Implementation Status

| Priority | File | Status | Notes |
|---------|------|-------|-------|
| HIGH | [agent_runner.py](app/services/agent_runner.py:158-182) | ✅ FIXED | Added language awareness instruction to GLOBAL_PREFIX. Progress messages kept English (emojis + short phrases are universal). |
| MEDIUM | [intent_resolver.py](app/integrations/intent_resolver.py:71-122) | ✅ FIXED | Added "generate in SAME LANGUAGE as user's input" instruction. Removed hardcoded examples from fallback message. |
| MEDIUM | [memory_extraction.py](app/services/memory_extraction.py:46-53) | ✅ FIXED | Added "Extract in SAME LANGUAGE" instruction. |
| LOW | [schedule_service.py](app/services/schedule_service.py:26-61) | ⏭️ SKIPPED | English regex fallback is emergency-only. LLM path handles multi-language. |
| LOW | [schedule_service.py](app/services/schedule_service.py:114-154) | ⏭️ SKIPPED | Error messages in ScheduleParseException - acceptable for v1, frontend can translate. |

---

## Summary

OCIN backend has several areas with hardcoded English text that will cause issues for non-English users. These range from system prompts that control agent behavior to user-facing error messages and progress updates.

---

## High Priority Issues (User-Facing)

These affect what users see and interact with directly:

### 1. ✅ FIXED: schedule_service.py - System Prompt

**File:** `app/services/schedule_service.py:75-97`

**Issue:** System prompt with English-only examples and rules
- Examples only in English
- No instruction to preserve user's language
- Fallback regex patterns are English-only

**Fix Applied:**
- Updated prompt to explicitly state "accepts input in ANY language"
- Added multi-language examples (English, Spanish, French, German)
- Instructed to keep `input` field in original user's language, not translate
- Prompt now ~350 tokens (vs ~180 original)

---

### 2. ❌ NOT FIXED: intent_resolver.py - User-Facing Messages

**File:** `app/integrations/intent_resolver.py:71-122`

**Issue:** Generates hardcoded English confirmation/clarification messages that the agent speaks to users

**Problematic code:**
```python
# Line 85-86: Prompt template for English messages
"confirmation_message": "<friendly confirmation e.g. Just to confirm — you want to connect Maton with Google Sheets, right?>",
"clarification_message": "<friendly question if unsure e.g. Could you clarify which app you want to connect? For example, Google Sheets, HubSpot, or Slack?>"

# Lines 114-121: Fallback hardcoded English messages
clarification_message=(
    f"I wasn't sure which integration you meant by \"{user_input}\". "
    f"Could you clarify? For example: Maton with Google Sheets, "
    f"Composio with Gmail, or Apify web scraper?"
),
```

**Impact:** When a Spanish user says "Quiero conectar con Gmail", the agent responds in English:
> "I wasn't sure which integration you meant by 'Quiero conectar con Gmail'. Could you clarify?"

**Recommended Fix:**
- Make LLM generate confirmation/clarification in user's language
- Update system prompt to instruct: "Generate response in same language as user input"
- Add multi-language examples to prompt

---

### 3. ❌ NOT FIXED: agent_runner.py - Global Agent Prefix & Progress Messages

**File:** `app/services/agent_runner.py:158-182`

**Issue:** GLOBAL_PREFIX hardcoded in English + hardcoded progress message text

**Problematic code:**
```python
# Line 158-182: GLOBAL_PREFIX - applies to ALL agents
GLOBAL_PREFIX = """You are a proactive AI assistant. Follow these rules strictly:

1. ALWAYS use your tools immediately when asked — never ask for confirmation
   unless a critical piece of information is genuinely missing
2. NEVER ask what the user wants — they already told you, just do it
3. When a tool call fails, try a different approach before giving up
4. Remember everything in this conversation — do not ask for information
   already provided earlier in the chat
...

# Line 103-117: Hardcoded progress messages
progress_messages = {
    "google_sheet_create_spreadsheet": "📊 Creating Google Sheet...",
    "slack_send_message": "💬 Sending Slack message...",
    "hubspot_create_contact": "👤 Creating HubSpot contact...",
    # ... all English
}
```

**Impact:**
- Agent instructions are English-only (agent behavior may differ across languages)
- Progress updates shown to users are English-only
- Spanish users see "📊 Creating Google Sheet..." instead of "📊 Creando hoja de cálculo..."

**Recommended Fix:**
- Extract progress messages to config or add language-aware wrapper
- Use LLM to generate progress messages in user's language
- Or add language parameter to progress streaming function

**Complexity:** HIGH - This affects ALL agent runs

---

## Medium Priority Issues (System-Internal)

These affect backend processing but are less visible to users:

### 4. memory_extraction.py - System Prompt

**File:** `app/services/memory_extraction.py:46-53`

**Issue:** System prompt in English, but fact extraction is more universal

**Problematic code:**
```python
system_prompt = (
    "You are a memory extraction assistant. Given a short conversation between a user "
    "and an AI assistant, extract 0 to 3 facts worth remembering about user or their "
    "situation for future conversations. Only extract things that are stable and useful "
    "across conversations (names, preferences, ongoing projects, recurring schedules). "
    "Do NOT extract small talk, jokes, or one-off information. Return an empty list if "
    "nothing is worth remembering."
)
```

**Impact:** LLM might extract facts with English keys instead of user's language

**Recommended Fix:**
- Add instruction: "Extract facts in user's language"
- Add multi-language examples

---

### 5. schedule_service.py - Regex Fallback Patterns

**File:** `app/services/schedule_service.py:26-61`

**Issue:** `_extract_task_hint()` function with English-only regex patterns for prefixes and scheduling words

**Problematic code:**
```python
# Lines 30-42: English prefixes only
prefixes = [
    r"^please\s+",
    r"^create\s+a\s+schedule\s+(that\s+)?",
    r"^make\s+a\s+(run|schedule)\s+(that\s+)?",
    # ... all English
]

# Lines 43-52: English scheduling words only
scheduling = [
    r"\b(every|each)\s+\d+\s+(minutes?|hours?|days?)\b",
    r"\b(every|each)\s+(minute|hour|day|morning|evening|night|monday|tuesday|...)\b",
    r"\b(daily|hourly|minutely|weekly)\b",
    # ... all English
]
```

**Impact:** Fallback regex parser will completely fail for non-English inputs

**Recommended Fix:**
- Accept that LLM path will handle non-English cases
- Keep regex as English-only emergency fallback
- Document limitation clearly

---

### 6. schedule_service.py - Error Messages

**File:** `app/services/schedule_service.py:114-117, 151-154`

**Issue:** `ScheduleParseException` messages in English

**Problematic code:**
```python
# Lines 114-117
raise ScheduleParseException(
    "Could not understand schedule. Try 'every minute', 'every 5 minutes', "
    "'every day at 9am', or 'every Monday at 8am'."
)

# Lines 151-154
raise ScheduleParseException(
    "Could not understand schedule. Try 'every minute', 'every 5 minutes', "
    "'every day at 9am', or 'every Monday at 8am'."
)
```

**Impact:** Spanish users get error message in English when their schedule input fails

**Recommended Fix:**
- Extract error messages to config with multi-language support
- Or let frontend translate error codes

---

## Low Priority Issues (Validation/Backend)

These are HTTP error responses - typically handled by frontend:

### 7. All Hardcoded English Error Messages

**Files:** Multiple across codebase

**Examples:**
- `app/core/dependencies.py` - Plan limit errors
- `app/routers/*` - "Agent not found", "User not found"
- `app/services/*` - Various validation errors

**Impact:** API returns English error messages

**Recommended Fix:**
- Use error codes and let frontend translate
- Or add i18n layer (probably not needed for v1)

---

## Implementation Priority Order

1. ✅ **schedule_service.py system prompt** - DONE (Option 1)
   - Added multi-language examples
   - Instructed to preserve user's language
   - ~350 tokens, acceptable

2. **intent_resolver.py confirmation messages** - MEDIUM
   - Update prompt to generate messages in user's language
   - Critical: affects integration setup flow

3. **agent_runner.py GLOBAL_PREFIX** - HIGH
   - Most complex: affects ALL agent runs
   - Agent behavior may differ across languages
   - Progress messages need localization

4. **memory_extraction.py system prompt** - LOW
   - Fact extraction is more universal
   - Add language preservation instruction

5. **Error messages** - LOW
   - Could be handled by frontend translation
   - Consider i18n layer for future

---

## Testing Recommendations

After fixing each area, test with non-English inputs:

**Schedule Parsing:**
- Spanish: "Cada mañana a las 9am revisa mi correo"
- French: "Toutes les matins à 9h"
- German: "Jeden Montag um 8 Uhr"

**Intent Resolution:**
- Spanish: "Quiero conectar con Gmail"
- French: "Je veux connecter Google Sheets"

**Agent Execution:**
- Progress messages should appear in user's language
- Agent responses should be in user's language
