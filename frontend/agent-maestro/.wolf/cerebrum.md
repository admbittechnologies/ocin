# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-04-13

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings

- **Project:** vite_react_shadcn_ts (OCIN Frontend)
- **Description:** React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui
- **Chat streaming:** Backend sends character-level SSE events ("token" event with single char). Cache replay was sending word-level tokens - fixed to character-level
- **Fallback timezone bug:** Frontend used timestamp comparison (created_at > cutoff) which failed due to UTC timezone differences. Fixed by using message count instead - track msgCountBefore, then check if total > msgCountBefore + 1
- **React Router navigation:** Use `navigate()` from react-router-dom for client-side navigation, NOT `window.location.href` which causes full page reloads and 404 errors when routes don't exist
- **Avatar mapping:** Agent avatars use hash-based naming (avatar-01 to avatar-30) and can be loaded using `getAvatarSrc()` helper from @/lib/avatars.ts
- **Approval workflow:** Pending approvals need direct action buttons (Approve/Reject) on the card itself, not hidden in a modal that users might not discover
- **Message rendering duplication:** When rendering message bubbles with attachments, avoid calling renderMessageContent() multiple times. Content should render exactly once per message bubble, preferably after attachments.
- **IME composition handling:** Textareas need composition event handlers (onCompositionStart, onCompositionEnd) and isComposing state to prevent submission of partial/dead-key characters. Always check isComposing in handleKeyDown before allowing Enter to submit.
- **SSE resilience and message correlation:** When SSE drops mid-stream, use timestamp-based correlation (created_at comparison) to find the correct assistant reply, not "newest message". Store user message_id and created_at when sending, then poll for assistant message where created_at > user_message.created_at - 5s. Keep isTyping=true until content found, hide empty messages (typing indicator shows separately).
- **Agent-specific memory toggle:** Use localStorage with per-agent keys (`ocin_agent_advanced_{agentId}`) to persist advanced toggle state. Each agent remembers its own toggle independently.
- **Memory API endpoints:** Backend provides agent-specific memory endpoints (`/api/v1/memory/{agent_id}`) that accept plain text body for PUT operations (not JSON).
- **Relative time formatting:** Simple helper function for user-friendly time display ("2h ago", "3 days ago") improves UX over raw timestamps.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

- **[2026-04-13] SSE fallback correlation:** Do NOT use "newest assistant message" in poll fallback - this can return stale content from previous turns. Instead, correlate by timestamp: find assistant message where created_at > user_message.created_at (with 5s tolerance for clock skew). Store user message_id and created_at when sending, use these for correlation.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
