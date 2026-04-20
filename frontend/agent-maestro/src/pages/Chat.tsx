import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, User, Paperclip, X, FileText, Loader2, ArrowLeft, MessageSquarePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAgentAvatar } from "@/lib/agentAvatar";
import {
  apiGetAgents,
  apiSendChatMessage,
  type Agent as ApiAgent,
  apiGetThreads,
  apiGetThreadMessages,
  apiDeleteThread,
} from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

// Format message timestamp: "2:34 PM" for today, "Mar 31, 2:34 PM" for older
const formatMessageTime = (date: Date): string => {
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  if (isToday) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' }) +
    ', ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

// Google Sheets link preview component
function GoogleSheetPreview({ url }: { url: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-3 mt-3 p-3 rounded-xl bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 hover:opacity-80 transition-opacity no-underline"
      onClick={e => e.stopPropagation()}
    >
      <span className="text-2xl flex-shrink-0">📊</span>
      <div className="flex flex-col min-w-0">
        <span className="text-xs font-medium text-green-800 dark:text-green-300">
          Google Sheets
        </span>
        <span className="text-xs text-green-600 dark:text-green-400 truncate">
          Open spreadsheet ↗
        </span>
      </div>
    </a>
  );
}

// Render message content with URL linkification
function renderMessageContent(content: string, isAssistant: boolean) {
  if (!isAssistant) {
    return <span style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{content}</span>;
  }

  const urlRegex = /(https?:\/\/[^\s]+)/g;
  const sheetsUrl = content.match(/https:\/\/docs\.google\.com\/spreadsheets\/[^\s]+/)?.[0];
  const parts = content.split(urlRegex);

  return (
    <div>
      <span style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {parts.map((part, i) => {
          urlRegex.lastIndex = 0;
          const isUrl = /^https?:\/\//.test(part);
          return isUrl ? (
            <a
              key={i}
              href={part}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline break-all hover:opacity-80"
              onClick={e => e.stopPropagation()}
            >
              {part}
            </a>
          ) : (
            <span key={i}>{part}</span>
          );
        })}
      </span>
      {sheetsUrl && <GoogleSheetPreview url={sheetsUrl} />}
    </div>
  );
}

interface Agent {
  id: string;
  name: string;
  avatar: string;
}

interface ChatAttachment {
  id: string;
  name: string;
  type: "image" | "file";
  url: string;
  mimeType: string;
  dataBase64?: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  agent: Agent;
  timestamp: Date;
  attachments?: ChatAttachment[];
  messageId?: string;
  isSystem?: boolean;
  progressMessages?: string[];
}

interface LastMessage {
  content: string;
  time: Date;
}

// Small subcomponents that resolve avatars via the shared cached hook.
// Needed because hooks cannot be called inside .map() callbacks.
function AgentAvatarImg({
  agentId,
  alt,
  className,
}: {
  agentId: string | null | undefined;
  alt: string;
  className?: string;
}) {
  const src = useAgentAvatar(agentId);
  return <img src={src} alt={alt} className={className} />;
}

export default function Chat() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [activeAgent, setActiveAgent] = useState<Agent | null>(null);
  const [showMentions, setShowMentions] = useState(false);
  const [mentionFilter, setMentionFilter] = useState("");
  const [mentionIndex, setMentionIndex] = useState(0);
  const [isTyping, setIsTyping] = useState(false);
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);

  // New state for agent thread mapping
  const [agentThreads, setAgentThreads] = useState<Record<string, string>>({});
  const [agentLastMessages, setAgentLastMessages] = useState<Record<string, LastMessage>>({});
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [showSidebar, setShowSidebar] = useState(false);
  const [isComposing, setIsComposing] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const attemptsRef = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mentionStartRef = useRef<number>(-1);
  const streamDoneRef = useRef(false);  // Prevent duplicate fallback triggers
  const eventSourceRef = useRef<EventSource | null>(null);  // Track active EventSource for cleanup
  const userMessageIdRef = useRef<string | null>(null);  // Track current user message_id for correlation
  const userMessageCreatedAtRef = useRef<Date | null>(null);  // Track user message created_at for correlation
  const pollFallbackActiveRef = useRef(false);  // Prevent multiple concurrent poll fallbacks
  const { toast } = useToast();

  // Filtered agents for @ mention
  const filteredAgents = agents.filter(a =>
    a.name.toLowerCase().includes(mentionFilter.toLowerCase())
  );

  // Resolve active agent's avatar src via shared cached hook
  const activeAgentAvatarSrc = useAgentAvatar(activeAgent?.id);

  // Scroll to bottom helper
  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }, 50);
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping, scrollToBottom]);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        try { eventSourceRef.current.close(); } catch {}
        eventSourceRef.current = null;
      }
    };
  }, []);

  // STARTUP: Load agents, set active agent, load most recent thread
  useEffect(() => {
    const init = async () => {
      try {
        // 1. Load agents from GET /api/v1/agents
        const data = await apiGetAgents();
        const mappedAgents: Agent[] = data.map((a: ApiAgent) => ({
          id: a.id,
          name: a.name,
          avatar: (a as any).avatar || "avatar-01",
        }));
        setAgents(mappedAgents);

        // 2. Load all threads from GET /api/v1/chat/threads
        const threadData = await apiGetThreads();
        const threadList = Array.isArray(threadData) ? threadData : (threadData as any).threads || [];

        // 3. Build agentId -> threadId map
        const threadMap: Record<string, string> = {};
        const lastMsgMap: Record<string, LastMessage> = {};

        for (const thread of threadList) {
          // Keep only most recent thread per agent
          if (!threadMap[thread.agent_id]) {
            threadMap[thread.agent_id] = thread.id;
            lastMsgMap[thread.agent_id] = {
              content: thread.last_message || "No messages yet",
              time: new Date(thread.last_message_at || thread.created_at),
            };
          }
        }
        setAgentThreads(threadMap);
        setAgentLastMessages(lastMsgMap);

        // 4. Restore last active agent from localStorage or use first agent
        const lastAgentId = localStorage.getItem("ocin_last_agent_id");
        const targetAgent = mappedAgents.find(a => a.id === lastAgentId)
          || mappedAgents[0];

        if (targetAgent) {
          setActiveAgent(targetAgent);
          const threadId = threadMap[targetAgent.id];
          if (threadId) {
            await loadThreadMessages(threadId, targetAgent, mappedAgents);
          }
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to initialize chat";
        toast({ title: "Error", description: message, variant: "destructive" });
      } finally {
        setLoading(false);
      }
    };

    init();
  }, [toast]);

  // Load thread messages helper
  const loadThreadMessages = async (
    threadId: string,
    agent: Agent,
    allAgents?: Agent[]
  ) => {
    setCurrentThreadId(threadId);
    const data = await apiGetThreadMessages(threadId);
    const msgList = Array.isArray(data) ? data : (data as any).messages || [];
    const agentList = allAgents || agents;

    const mapped: ChatMessage[] = msgList.map((m: any) => ({
      id: m.id,
      role: m.role as "user" | "assistant",
      content: m.content || "",
      agent: m.role === "assistant"
        ? (agentList.find(a => a.id === agent.id) || agent)
        : agent,
      timestamp: new Date(m.created_at),
    }));
    setMessages(mapped);
    setTimeout(scrollToBottom, 100);
  };

  // Switch to a specific agent and load their thread
  const switchToAgent = async (agent: Agent) => {
    setActiveAgent(agent);
    localStorage.setItem("ocin_last_agent_id", agent.id);
    const threadId = agentThreads[agent.id];
    if (threadId) {
      await loadThreadMessages(threadId, agent);
    } else {
      setMessages([]);
      setCurrentThreadId(null);
    }
    // Close sidebar on mobile after selection
    setShowSidebar(false);
  };

  // Handle file attachments
  const addFiles = (files: FileList | File[]) => {
    const newAttachments: ChatAttachment[] = [];
    Array.from(files).forEach(file => {
      const url = URL.createObjectURL(file);
      const isImage = file.type.startsWith("image/");

      // Read image as base64 for API
      if (isImage) {
        const reader = new FileReader();
        reader.onload = (e) => {
          const base64 = e.target?.result as string;
          setAttachments(prev =>
            prev.map(att =>
              att.id === newAttachments.find(na => na.name === file.name)?.id
                ? { ...att, dataBase64: base64 }
                : att
            )
          );
        };
        reader.readAsDataURL(file);
      }

      newAttachments.push({
        id: crypto.randomUUID(),
        name: file.name,
        type: isImage ? "image" : "file",
        url,
        mimeType: file.type,
      });
    });
    setAttachments(prev => [...prev, ...newAttachments]);
  };

  const removeAttachment = (id: string) => {
    setAttachments(prev => {
      const att = prev.find(a => a.id === id);
      if (att) URL.revokeObjectURL(att.url);
      return prev.filter(a => a.id !== id);
    });
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const files: File[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.kind === "file") {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }
    if (files.length > 0) {
      e.preventDefault();
      addFiles(files);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  };

  // AGENT SWITCHING: @ mention popup
  const selectAgent = (agent: Agent) => {
    const before = input.slice(0, mentionStartRef.current);
    const after = input.slice(inputRef.current?.selectionStart ?? input.length);
    setInput(before + after);
    switchToAgent(agent);
    setShowMentions(false);
    setMentionFilter("");
    mentionStartRef.current = -1;
    inputRef.current?.focus();
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setInput(val);

    const cursorPos = e.target.selectionStart;
    const textBeforeCursor = val.slice(0, cursorPos);

    // Detect @ for agent mentions
    const atMentionIndex = textBeforeCursor.lastIndexOf("@");
    if (atMentionIndex !== -1 && (atMentionIndex === 0 || textBeforeCursor[atMentionIndex - 1] === " ")) {
      const query = textBeforeCursor.slice(atMentionIndex + 1);
      if (!query.includes(" ")) {
        mentionStartRef.current = atMentionIndex;
        setMentionFilter(query);
        setShowMentions(true);
        setMentionIndex(0);
        return;
      }
    }

    setShowMentions(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showMentions) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMentionIndex(i => (i + 1) % filteredAgents.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMentionIndex(i => (i - 1 + filteredAgents.length) % filteredAgents.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        if (filteredAgents[mentionIndex]) {
          selectAgent(filteredAgents[mentionIndex]);
        }
        return;
      }
      if (e.key === "Escape") {
        setShowMentions(false);
        return;
      }
    }

    // Prevent submit during IME composition (e.g., typing accent keys)
    if (isComposing) {
      return;
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Poll fallback function that finds the assistant message correlated with the user message
  const startPollFallback = (
    threadId: string,
    userMessageId: string | null,
    userMessageCreatedAt: Date | null
  ) => {
    // Prevent multiple concurrent poll fallbacks
    if (pollFallbackActiveRef.current) {
      console.log("Poll fallback already active, skipping duplicate request");
      return;
    }

    pollFallbackActiveRef.current = true;
    const maxAttempts = 30; // 30 seconds total (1 second intervals)
    let pollAttempts = 0;

    const poll = async () => {
      pollAttempts++;
      if (pollAttempts > maxAttempts) {
        console.warn("Poll fallback timeout after 30 seconds");
        pollFallbackActiveRef.current = false;
        setIsTyping(false);
        setSending(false);
        return;
      }

      try {
        const msgs = await apiGetThreadMessages(threadId);
        const msgList = Array.isArray(msgs)
          ? msgs
          : (msgs as any).messages || [];

        const assistantMsgs = msgList.filter((m: any) => m.role === "assistant");
        console.log(`POLL: attempt ${pollAttempts}/${maxAttempts}, found ${assistantMsgs.length} assistant msgs`);

        // Find the assistant message that comes after our user message
        const assistantMsg = findCorrelatedAssistantMessage(msgList, userMessageCreatedAt);

        if (assistantMsg) {
          console.log(`ASSISTANT_MSG_RESOLVED message_id=${assistantMsg.id} content_length=${assistantMsg.content.length} first_chars="${assistantMsg.content.slice(0, 50)}..."`);

          // Update the last assistant message with the correct content
          setMessages(prev => {
            const updated = [...prev];
            const lastMsg = updated[updated.length - 1];
            if (lastMsg?.role === "assistant" && lastMsg?.agent?.id === activeAgent?.id) {
              updated[updated.length - 1] = { ...lastMsg, content: assistantMsg.content };
            }
            return updated;
          });

          // Update last messages map
          if (activeAgent) {
            setAgentLastMessages(prev => ({
              ...prev,
              [activeAgent.id]: {
                content: assistantMsg.content.slice(0, 60),
                time: new Date(),
              },
            }));
          }

          pollFallbackActiveRef.current = false;
          setIsTyping(false);
          setSending(false);
          setTimeout(scrollToBottom, 50);
        } else {
          // No matching assistant message yet, continue polling
          setTimeout(poll, 1000);
        }
      } catch (err) {
        console.error("Poll fallback error:", err);
        setTimeout(poll, 1000);
      }
    };

    // Start polling immediately
    poll();
  };

  // Find the assistant message that corresponds to the user message we just sent
  const findCorrelatedAssistantMessage = (
    messages: any[],
    userMessageCreatedAt: Date | null
  ) => {
    if (!userMessageCreatedAt) return null;

    const userMsgTime = userMessageCreatedAt.getTime();
    let candidateMsg: any = null;

    // Find the first assistant message created after our user message
    for (const msg of messages) {
      if (msg.role === "assistant") {
        const msgTime = new Date(msg.created_at).getTime();
        // Allow for small timing differences (up to 5 seconds before to account for clock skew)
        if (msgTime > userMsgTime - 5000) {
          candidateMsg = msg;
          console.log(`POLL: found candidate assistant msg created ${new Date(msg.created_at).toISOString()} (user msg created ${userMessageCreatedAt.toISOString()})`);
          break;
        }
      }
    }

    return candidateMsg;
  };

  // Handle clear conversation
  const handleClearConversation = async () => {
    if (!activeAgent) return;
    const threadId = agentThreads[activeAgent.id];
    if (threadId) {
      try {
        await apiDeleteThread(threadId);
      } catch (e) {
        console.error("Failed to delete thread", e);
      }
    }
    // Remove from thread map
    setAgentThreads(prev => {
      const updated = { ...prev };
      delete updated[activeAgent.id];
      return updated;
    });
    setAgentLastMessages(prev => {
      const updated = { ...prev };
      delete updated[activeAgent.id];
      return updated;
    });
    setMessages([]);
    setCurrentThreadId(null);
    setShowClearConfirm(false);
  };

  // SENDING A MESSAGE
  const handleSend = async () => {
    if (!activeAgent || (!input.trim() && attachments.length === 0) || isTyping) return;

    // Reset flags for each new message
    streamDoneRef.current = false;
    attemptsRef.current = 0;
    pollFallbackActiveRef.current = false;

    // Close any prior EventSource before opening new one
    if (eventSourceRef.current) {
      try { eventSourceRef.current.close(); } catch {}
      eventSourceRef.current = null;
    }

    // 1. Record message count BEFORE sending for fallback comparison
    const msgCountBefore = messages.length;

    // 2. Add user message to UI immediately
    const userMsgTimestamp = new Date();
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: input.trim(),
      agent: activeAgent,
      timestamp: userMsgTimestamp,
      attachments: attachments.length > 0 ? [...attachments] : undefined,
    };
    setMessages(prev => [...prev, userMsg]);

    // Store user message timestamp for correlation with assistant reply
    userMessageCreatedAtRef.current = userMsgTimestamp;
    setInput("");
    setAttachments([]);

    setIsTyping(true);
    setSending(true);

    try {
      // 3. Call apiSendChatMessage(activeAgent.id, input, currentThreadId)
      const apiAttachments = attachments.map(att => ({
        name: att.name,
        type: att.mimeType,
        data_base64: att.dataBase64 || att.url,
      }));

      const response = await apiSendChatMessage(
        activeAgent.id,
        input.trim() || (attachments.length > 0 ? "Attached files" : ""),
        currentThreadId || undefined,
        apiAttachments.length > 0 ? apiAttachments : undefined
      );

      // 4. Store returned message_id and thread_id
      userMessageIdRef.current = response.message_id;
      const activeThreadId = response.thread_id || currentThreadId;
      if (response.thread_id) {
        setCurrentThreadId(response.thread_id);
        // Update agentThreads map with new thread ID
        setAgentThreads(prev => ({
          ...prev,
          [activeAgent.id]: response.thread_id,
        }));
      }

      // 5. Add optimistic assistant placeholder (empty content - will show typing indicator)
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",  // Empty content triggers typing indicator
        agent: activeAgent!,
        timestamp: new Date(),
      }]);

      // 6. Connect to SSE stream using EventSource
      const token = localStorage.getItem("ocin_jwt_token");
      const esUrl = `${import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1"}/chat/stream?message_id=${response.message_id}&token=${token}`;
      const eventSource = new EventSource(esUrl);
      eventSourceRef.current = eventSource;  // Track for cleanup
      let sseTimeout: NodeJS.Timeout | null = null;

      let streamReceivedTokens = false;

      // Log ALL events for debugging
      eventSource.onopen = () => {
        console.log("SSE connection opened");
      };

      // Hard timeout after 30s - force close if SSE stalls
      sseTimeout = setTimeout(() => {
        if (!streamDoneRef.current) {
          console.warn("SSE hard timeout (30s) — triggering poll fallback");
          try { eventSource.close(); } catch {}
          eventSourceRef.current = null;
          // Trigger poll fallback
          startPollFallback(activeThreadId, userMessageIdRef.current, userMessageCreatedAtRef.current);
        }
      }, 30000);

      // Catch-all for any event types we might be missing
      eventSource.addEventListener("message", (e) => {
        // Guard: ignore late events from done streams
        if (streamDoneRef.current) return;

        console.log("SSE message event:", e.type, e.data);
        streamReceivedTokens = true;
        try {
          const data = JSON.parse(e.data);
          if (data.content) {
            setMessages(prev => {
              const lastMsg = prev[prev.length - 1];
              // If last message is assistant with this agent, update it; otherwise create new
              if (lastMsg?.role === "assistant" && lastMsg?.agent?.id === activeAgent?.id && lastMsg.content === "") {
                return [...prev.slice(0, -1), { ...lastMsg, content: data.content }];
              }
              return [...prev, {
                id: crypto.randomUUID(),
                role: "assistant",
                content: data.content,
                agent: activeAgent!,
                timestamp: new Date(),
              }];
            });
          }
        } catch (err) {
          console.error("SSE message parse error:", err);
        }
      });

      eventSource.addEventListener("token", (e) => {
        // Guard: ignore late events from done streams
        if (streamDoneRef.current) return;

        streamReceivedTokens = true;
        try {
          const data = JSON.parse(e.data) as { token?: string };
          if (data.token) {
            setMessages(prev => {
              const lastMsg = prev[prev.length - 1];
              // If last message is assistant with this agent, update it; otherwise create new
              if (lastMsg?.role === "assistant" && lastMsg?.agent?.id === activeAgent?.id) {
                return [...prev.slice(0, -1), { ...lastMsg, content: lastMsg.content + data.token }];
              }
              return [...prev, {
                id: crypto.randomUUID(),
                role: "assistant",
                content: data.token,
                agent: activeAgent!,
                timestamp: new Date(),
              }];
            });
          }
        } catch (err) {
          console.error("SSE token parse error:", err);
        }
      });

      const handleSSEDone = () => {
        // Clear timeout when stream completes normally
        if (sseTimeout) {
          clearTimeout(sseTimeout);
          sseTimeout = null;
        }
        // Clear backup poll
        clearTimeout(backupPoll);

        console.log("SSE done event received");
        streamDoneRef.current = true;  // Mark stream as complete

        // Explicitly close EventSource
        try { eventSource.close(); } catch {}
        eventSourceRef.current = null;

        setIsTyping(false);
        setSending(false);

        // Update last messages map after response
        setMessages(prev => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.role === "assistant" && lastMsg.content) {
            setAgentLastMessages(prevLast => ({
              ...prevLast,
              [activeAgent.id!]: {
                content: lastMsg.content.slice(0, 60),
                time: new Date(),
              },
            }));
          }
          return prev;
        });
      };

      eventSource.addEventListener("done", handleSSEDone);

      eventSource.onerror = (err) => {
        // Clear timeout on error
        if (sseTimeout) {
          clearTimeout(sseTimeout);
          sseTimeout = null;
        }
        console.error("SSE error:", err, "message_id:", userMessageIdRef.current);

        // Trigger immediate poll fallback with proper correlation
        console.log(`SSE_FALLBACK_TRIGGERED message_id=${userMessageIdRef.current} reason=onerror`);

        try { eventSource.close(); } catch {}
        eventSourceRef.current = null;

        // DO NOT set isTyping/sending to false here - let the poll handle it
        // Start aggressive polling (every 1 second) to fetch the correct assistant message
        startPollFallback(activeThreadId, userMessageIdRef.current, userMessageCreatedAtRef.current);
      };

      // 7. Start backup poll in case SSE is slow (2 second delay to let SSE try first)
      const backupPoll = setTimeout(() => {
        if (!streamDoneRef.current) {
          console.log("SSE appears slow after 2s, starting backup poll");
          // This will race with the error handler's poll, but startPollFallback has its own attempt counter and flag
          startPollFallback(activeThreadId, userMessageIdRef.current, userMessageCreatedAtRef.current);
        }
      }, 2000);

    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to send message";
      toast({ title: "Error", description: message, variant: "destructive" });
      setIsTyping(false);
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div
      className="flex h-full overflow-hidden"
      onDragOver={e => e.preventDefault()}
      onDrop={handleDrop}
    >
      {/* LEFT PANEL: Agent List Sidebar */}
      <div className={`${showSidebar ? "fixed inset-0 z-40 md:relative" : "hidden md:flex"} md:w-64 flex-shrink-0 border-r border-border flex flex-col overflow-hidden bg-card`}>
        {/* Header */}
        <div className="flex-shrink-0 p-4 border-b border-border">
          <h2 className="font-semibold text-foreground">Agents</h2>
        </div>

        {/* Agent list */}
        <div className="flex-1 overflow-y-auto">
          {agents.map(agent => {
            const isActive = activeAgent?.id === agent.id;
            const lastMsg = agentLastMessages[agent.id];
            const hasThread = !!agentThreads[agent.id];

            return (
              <button
                key={agent.id}
                onClick={() => switchToAgent(agent)}
                className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-accent/50 ${
                  isActive ? "bg-accent" : ""
                }`}
              >
                <div className="relative flex-shrink-0">
                  <AgentAvatarImg
                    agentId={agent.id}
                    alt={agent.name}
                    className="h-10 w-10 rounded-full object-cover"
                  />
                  {hasThread && (
                    <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-green-500 border-2 border-background" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-foreground truncate">
                      {agent.name}
                    </span>
                    {lastMsg && (
                      <span className="text-[10px] text-muted-foreground ml-1 flex-shrink-0">
                        {formatMessageTime(lastMsg.time)}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground truncate mt-0.5">
                    {lastMsg?.content || "No messages yet"}
                  </p>
                </div>
              </button>
            );
          })}
        </div>

        {/* New agent button */}
        <div className="flex-shrink-0 p-3 border-t border-border">
          <a
            href="/agents"
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors"
          >
            <MessageSquarePlus className="h-4 w-4" />
            <span>New Agent</span>
          </a>
        </div>
      </div>

      {/* RIGHT PANEL: Active Conversation */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Header */}
        <div className="flex-shrink-0 flex items-center gap-3 py-3 px-4 border-b border-border">
          {/* Mobile: Back button */}
          <button
            onClick={() => setShowSidebar(false)}
            className="md:hidden mr-2 text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>

          {/* Mobile: Open sidebar button */}
          {!showSidebar && (
            <button
              onClick={() => setShowSidebar(true)}
              className="md:hidden mr-2 text-muted-foreground hover:text-foreground transition-colors"
            >
              <MessageSquarePlus className="h-5 w-5" />
            </button>
          )}

          <img
            src={activeAgentAvatarSrc}
            alt={activeAgent?.name || ""}
            className="h-8 w-8 rounded-full object-cover"
          />
          <div className="flex-1">
            <h1 className="text-sm font-semibold text-foreground">
              {activeAgent?.name || "Select an agent"}
            </h1>
            <p className="text-xs text-muted-foreground">
              Type <kbd className="px-1 py-0.5 rounded bg-secondary text-[10px] font-mono">@</kbd> to switch agents
            </p>
          </div>
          {agentThreads[activeAgent?.id || ""] && (
            <button
              onClick={() => setShowClearConfirm(true)}
              className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
            >
              <Paperclip className="h-3 w-3 rotate-45" />
              <span>Clear chat</span>
            </button>
          )}
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto py-6 px-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <img
                src={activeAgentAvatarSrc}
                alt={activeAgent?.name || ""}
                className="h-16 w-16 rounded-2xl object-cover"
              />
              <div className="text-center">
                <h2 className="text-lg font-semibold text-foreground">
                  Chat with {activeAgent?.name}
                </h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Send a message to start the conversation.
                </p>
              </div>
            </div>
          )}

          <AnimatePresence>
            {messages.map(msg => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.role === "assistant" && (
                  <AgentAvatarImg
                    agentId={msg.agent?.id}
                    alt={msg.agent?.name || "Agent"}
                    className="h-8 w-8 rounded-full object-cover flex-shrink-0 mt-1"
                  />
                )}
                <div className={`max-w-[70%] ${msg.role === "user" ? "order-first" : ""}`}>
                  {msg.isSystem ? (
                    <div className="w-full text-center py-4">
                      <span className="text-sm text-muted-foreground">{msg.content}</span>
                    </div>
                  ) : (
                    <>
                      <div className={`text-[10px] mb-1 ${msg.role === "user" ? "text-right" : "text-left"} text-muted-foreground`}>
                        {msg.role === "assistant" ? msg.agent?.name : "You"}
                      </div>
                      <div
                        className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                          msg.role === "user"
                            ? "bg-primary text-primary-foreground rounded-br-md"
                            : "bg-secondary text-foreground rounded-bl-md"
                        }`}
                        style={{ wordBreak: "break-word", overflowWrap: "break-word" }}
                      >
                        {msg.attachments && msg.attachments.length > 0 && (
                          <div className="flex flex-wrap gap-2 mb-2">
                            {msg.attachments.map(att => (
                              att.type === "image" ? (
                                <img
                                  key={att.id}
                                  src={att.url}
                                  alt={att.name}
                                  className="max-w-[200px] max-h-[150px] rounded-lg object-cover"
                                />
                              ) : (
                                <div
                                  key={att.id}
                                  className="flex items-center gap-2 px-3 py-2 rounded-lg bg-background/20 text-xs"
                                >
                                  <FileText className="h-4 w-4 flex-shrink-0" />
                                  <span className="truncate max-w-[150px]">{att.name}</span>
                                </div>
                              )
                            ))}
                          </div>
                        )}
                        {msg.content
                          ? renderMessageContent(msg.content, msg.role === "assistant")
                          : null  // Empty messages are hidden - typing indicator shows separately
                        }
                      </div>
                      <div className={`text-[10px] mt-1 text-muted-foreground ${msg.role === "user" ? "text-right" : "text-left"}`}>
                        {formatMessageTime(msg.timestamp)}
                      </div>
                    </>
                  )}
                </div>
                {msg.role === "user" && (
                  <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center flex-shrink-0 mt-1">
                    <User className="h-4 w-4 text-muted-foreground" />
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {/* TYPING INDICATOR */}
          {isTyping && activeAgent && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3 items-start">
              <img
                src={activeAgentAvatarSrc}
                alt={activeAgent.name}
                className="h-8 w-8 rounded-full object-cover"
              />
              <div className="bg-secondary rounded-2xl rounded-bl-md px-4 py-3">
                <div className="flex gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce [animation-delay:0ms]" />
                  <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
                  <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
                </div>
              </div>
            </motion.div>
          )}
        </div>

        {/* Input area */}
        <div className="flex-shrink-0 relative border-t border-border p-4">
          {/* Agent mention popup */}
          <AnimatePresence>
            {showMentions && filteredAgents.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                className="absolute bottom-full left-4 right-4 mb-2 bg-card border border-border rounded-xl shadow-lg overflow-hidden z-50"
              >
                <div className="p-1.5">
                  <p className="text-[10px] text-muted-foreground px-2 py-1 uppercase tracking-wider font-medium">
                    Switch agent
                  </p>
                  {filteredAgents.map((agent, i) => (
                    <button
                      key={agent.id}
                      onClick={() => selectAgent(agent)}
                      className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm transition-colors ${
                        i === mentionIndex
                          ? "bg-accent text-accent-foreground ring-2 ring-accent"
                          : "text-foreground hover:bg-accent/50"
                      }`}
                    >
                      <AgentAvatarImg
                        agentId={agent.id}
                        alt={agent.name}
                        className="h-7 w-7 rounded-full object-cover"
                      />
                      <span className="font-medium">{agent.name}</span>
                    </button>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Attachment previews */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {attachments.map(att => (
                <div key={att.id} className="relative group">
                  {att.type === "image" ? (
                    <img
                      src={att.url}
                      alt={att.name}
                      className="h-16 w-16 rounded-lg object-cover border border-border"
                    />
                  ) : (
                    <div className="h-16 px-3 rounded-lg border border-border bg-secondary flex items-center gap-2 text-xs text-muted-foreground">
                      <FileText className="h-4 w-4 flex-shrink-0" />
                      <span className="truncate max-w-[100px]">{att.name}</span>
                    </div>
                  )}
                  <button
                    onClick={() => removeAttachment(att.id)}
                    className="absolute -top-1.5 -right-1.5 h-5 w-5 rounded-full bg-destructive text-destructive-foreground flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-end gap-2">
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                onPaste={handlePaste}
                onCompositionStart={() => setIsComposing(true)}
                onCompositionEnd={() => setIsComposing(false)}
                placeholder={`Message ${activeAgent?.name || "an agent"}... (@ to switch)`}
                rows={1}
                disabled={!activeAgent || sending}
                className="w-full resize-none rounded-xl border border-border bg-secondary pl-4 pr-12 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent min-h-[44px] max-h-[120px]"
                style={{ height: "auto", overflow: "auto" }}
                onInput={e => {
                  const t = e.currentTarget;
                  t.style.height = "auto";
                  t.style.height = Math.min(t.scrollHeight, 120) + "px";
                }}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="absolute right-3 bottom-3 text-muted-foreground hover:text-foreground transition-colors"
              >
                <Paperclip className="h-4 w-4" />
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*,.pdf,.txt,.csv,.json,.md,.doc,.docx,.xls,.xlsx"
                className="hidden"
                onChange={e => {
                  if (e.target.files) addFiles(e.target.files);
                  e.target.value = "";
                }}
              />
            </div>
            <Button
              onClick={handleSend}
              disabled={!activeAgent || (!input.trim() && attachments.length === 0) || sending}
              size="icon"
              className="gradient-primary text-primary-foreground h-11 w-11 rounded-xl shrink-0"
            >
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>

      {/* Clear conversation confirmation dialog */}
      <AlertDialog open={showClearConfirm} onOpenChange={setShowClearConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Clear conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete your conversation with {activeAgent?.name}.
              This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleClearConversation}
              className="bg-destructive text-destructive-foreground"
            >
              Clear conversation
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}