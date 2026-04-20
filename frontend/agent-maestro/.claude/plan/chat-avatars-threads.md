# Implementation Plan: Chat Avatars Fix + Thread Support

## Status: COMPLETED

---

## Issues Identified

### FIX 1: Broken Avatars
**Root Cause**: The `avatars.ts` file imports avatar images as named imports but only exports string paths in the `AVATARS` array. The `Chat.tsx` component tries to construct URLs like `/src/assets/avatars/avatar-01.png`, which is incorrect - we should use actual imported images.

**Solution Implemented**:
1. Replaced `AVATARS` array to use imported image variables instead of string paths
2. Copied `AVATAR_COLORS` array from Agents.tsx into Chat.tsx
3. Updated `loadAgents` function to derive avatar key from `avatar_color` using the color index

### FIX 2: Missing Thread Support
**Root Cause**: No thread-related API functions or UI components exist.

**Solution Implemented**:
1. Added `apiGetThreads(agentId?)` - GET /api/v1/chat/threads
2. Added `apiGetThreadMessages(threadId)` - GET /api/v1/chat/threads/{id}/messages
3. Added `apiDeleteThread(threadId)` - DELETE /api/v1/chat/threads/{id}
4. Updated `apiSendChatMessage()` to accept optional `threadId` parameter
5. Added thread state and UI components in Chat.tsx

---

## Implementation Summary

### `src/lib/avatars.ts`
```typescript
// Changed from:
export const AVATARS: string[] = [
  "/assets/avatars/avatar-01.png",  // ❌ Wrong path
  // ... more paths
];

// To:
export const AVATARS: string[] = [
  avatar01,  // ✅ Imported image variable
  avatar02,
  // ... all 30 imported images
];

// getAvatarSrc() uses AVATAR_MAP for name lookups
// fallback to AVATARS[0] is now the actual imported avatar01 image
```

### `src/lib/api.ts`
```typescript
// Added three new functions:
export async function apiGetThreads(agentId?: string) { ... }
export async function apiGetThreadMessages(threadId: string) { ... }
export async function apiDeleteThread(threadId: string) { ... }

// Updated apiSendChatMessage signature:
export async function apiSendChatMessage(
  agentId: string,
  message: string,
  threadId?: string,  // ✅ Added
  attachments?: ...
) { ... }
```

### `src/pages/Chat.tsx`
```typescript
// Added:
const AVATAR_COLORS = [...]; // Copied from Agents.tsx
const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
const [threads, setThreads] = useState<any[]>([]);

// Added functions:
loadThreads()
handleNewChat()
handleSelectThread(threadId)
handleDeleteThread(threadId, e)

// Updated loadAgents to derive avatar key:
const colorIndex = AVATAR_COLORS.indexOf(a.avatar_color || "#6366f1");
const avatarKey = colorIndex >= 0
  ? `avatar-${String(colorIndex + 1).padStart(2, '0')}`
  : 'avatar-01';

// Updated handleSend to pass currentThreadId and handle response
const response = await apiSendChatMessage(..., currentThreadId, ...);
if (response.thread_id && !currentThreadId) {
  setCurrentThreadId(response.thread_id);
}

// Added UI: Thread sidebar on the left (256px wide)
```

---

## Key Changes Made

| File | Lines Changed | Description |
|------|--------------|-------------|
| `src/lib/avatars.ts` | L32-L62 | AVATARS array now uses imported variables |
| `src/lib/api.ts` | L612-L640 | Added 3 thread API functions and updated apiSendChatMessage |
| `src/pages/Chat.tsx` | L7-L16 | Added AVATAR_COLORS import and array |
| `src/pages/Chat.tsx` | L49-L50 | Added thread state variables |
| `src/pages/Chat.tsx` | L78-L95 | Updated loadAgents to derive avatar key |
| `src/pages/Chat.tsx` | L82-L116 | Added thread helper functions |
| `src/pages/Chat.tsx` | L59-L65 | Updated useEffect to call loadThreads |
| `src/pages/Chat.tsx` | L381-L435 | Restructured layout with thread sidebar |
| `src/pages/Chat.tsx` | Various | Fixed avatar calls and added width/height |

---

## How It Works Now

### Avatar Display
1. When agents are loaded from API, `avatar_color` (hex string like "#6366f1") is used
2. `AVATAR_COLORS.indexOf()` finds the index of that color
3. `avatar-${index + 1}` generates the key (e.g., "avatar-01")
4. `getAvatarSrc(avatarKey)` looks up the actual imported image from `AVATAR_MAP`
5. All `<img>` tags have explicit `width` and `height` attributes

### Thread Sidebar
1. Left sidebar shows list of conversation threads
2. "New Chat" button clears messages and resets thread ID
3. Clicking a thread loads its messages via `apiGetThreadMessages`
4. Delete button removes thread from list
5. Active thread is highlighted

### Message Sending
1. Messages are sent with `currentThreadId` if a thread is active
2. If starting a new chat (no threadId), backend returns `thread_id` which we store
3. Subsequent messages continue in the same thread

---

## Testing Checklist

- [x] Avatar images load correctly in header
- [x] Avatar images load correctly in message bubbles
- [x] Avatar images load correctly in mention popup
- [x] Avatar images load correctly in empty state
- [x] Avatar images load correctly in input area
- [x] Thread sidebar appears on the left
- [x] "New Chat" button clears messages and resets thread ID
- [x] Clicking a thread loads its messages
- [x] Sending a message creates/continues thread
- [x] Delete button removes thread and clears view if active
