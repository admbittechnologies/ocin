# Tool Connection Counting & API Key Disconnect Fixes

## Issues Fixed

### Issue 1: Tool connections count included LLM provider API keys
**Problem**: The tool integration limit was counting ALL tools (including LLM provider API keys like Google, Anthropic, etc.) instead of only actual tool integrations (Composio, Apify, Maton).

**Location**: `app/core/dependencies.py` line 130

**Fix**: Updated the tool counting query to exclude tools with `source="api_key"`:

```python
# OLD (incorrect):
select(func.count(Tool.id)).where(
    Tool.user_id == user.id,
    Tool.is_active == True,
    Tool.source != "builtin"  # Only excluded builtin tools
)

# NEW (correct):
select(func.count(Tool.id)).where(
    Tool.user_id == user.id,
    Tool.is_active == True,
    Tool.source != "builtin",
    Tool.source != "api_key"  # Also exclude LLM provider API keys
)
```

**Result**: Now only external tool integrations (Composio, Apify, Maton) count toward the `max_tool_integrations` plan limit.

---

### Issue 2: No way to disconnect/delete LLM provider API keys
**Problem**: Users could add API keys for LLM providers but had no way to remove them. They were stuck with a provider they no longer wanted to use.

**Location**: `app/routers/settings.py`

**Fix**: Added DELETE endpoint to allow users to remove their API keys:

```python
@router.delete("/api-keys/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    provider: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Delete/disconnect an API key for a specific provider."""
```

**How it works**:
- Accepts provider name as path parameter (e.g., `/api-keys/google`)
- Validates the provider is supported
- Finds the tool storing that provider's API key (`source="api_key"`, `source_key=provider`)
- Deletes the tool record
- Returns 204 No Content on success

**Frontend integration**: To disconnect a provider's API key, call:
```javascript
DELETE /api/v1/settings/api-keys/{provider}
```

Example: `DELETE /api/v1/settings/api-keys/google` to remove the Google API key.

---

## Database Schema Context

LLM provider API keys are stored in the `tools` table as:
- `source = "api_key"` (distinguishes them from real tool integrations)
- `source_key = provider name` (e.g., "google", "anthropic", "openai")
- `config = {"api_key": "<encrypted_value>"}`

Real tool integrations are stored as:
- `source = "composio" | "apify" | "maton"`
- `source_key = connection/app identifier (e.g., "gmail", "google-sheets", "webhook-scraper")
- `config = {connection credentials}`

---

## Testing

To verify the fix works:

1. Add API keys for multiple LLM providers (Google, Anthropic, OpenAI)
2. Add a real tool integration (e.g., Composio Gmail)
3. Check that only the real integration counts toward your plan limit
4. Test disconnecting an API key: `DELETE /api/v1/settings/api-keys/google`
5. Verify the API key is removed and no longer counted (it wasn't counting anyway, but it's gone from your account)

---

## Files Modified

1. `app/core/dependencies.py` - Fixed tool counting to exclude `source="api_key"`
2. `app/routers/settings.py` - Added `DELETE /api-keys/{provider}` endpoint

## Typo Fixes

- Fixed `intEgrations` → `integrations` in `dependencies.py`
- Fixed `normalEze_provider` → `normalize_provider` in `settings.py`
- Fixed `result.scalars()` → `result.scalars()` in `settings.py`
