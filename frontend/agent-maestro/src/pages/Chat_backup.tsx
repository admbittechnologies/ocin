import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Bot, User, Paperclip, X, Image as ImageIcon, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import ocinAvatar from "@/assets/avatars/ocin-avatar.png";
import { AVATARS, getAvatarSrc } from "@/lib/avatars";
import { apiGetAgents, apiSendChatMessage, apiStreamChatResponse, type Agent as ApiAgent, apiGetApiKeys, apiGetThreads, apiGetThreadMessages, apiDeleteThread } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

// Avatar color codes matching backend avatar_color field
const AVATAR_COLORS = [
  "#6366f1", "#8b5cf6", "#ec4899", "#f97316", "#eab308",
  "#22c55e", "#14b8a6", "#06b6d4", "#0ea5e9", "#3b82f6",
  "#a855f7", "#d946ef", "#f43f5e", "#ef4444", "#f59e0b",
  "#84cc16", "#10b981", "#0d9488", "#0284c7", "#1d4ed8",
  "#4f46e5", "#7c3aed", "#9333ea", "#c026d3", "#db2777"
];

interface Agent {
  id: string;
  name: string;
  avatar_color: string;
  avatar?: string;
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
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mentionStartRef = useRef<number>(-1);
  const lastAssistantMessageIdRef = useRef<string | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const { toast } = useToast();

  // Load agents and thread in sequence to avoid race
  const [loadedAgents, setLoadedAgents] = useState<Agent[]>([]);
  const [isLoadingThread, setIsLoadingThread] = useState(false);

  const init = async () => {
    await loadAgents();
    if (!isLoadingThread && loadedAgents.length > 0) {
      await loadMostRecentThread();
    }
  };

  useEffect(() => {
    init();
    return () => {
      if (cleanupRef.current) {
        cleanupRef.current();
      }
    };
  }, []);

  // Load most recent thread on mount
  const loadMostRecentThread = async () => {
    try {
      setIsLoadingThread(true);
      const data = await apiGetThreads();
      if (data.threads && data.threads.length > 0) {
        const mostRecent = data.threads[0];
        const threadData = await apiGetThreadMessages(mostRecent.id);
        const mappedMessages: ChatMessage[] = threadData.messages.map((m: any) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          agent: m.role === "assistant"
            ? (loadedAgents.find(a => a.id === mostRecent.agent_id) || activeAgent)
            : activeAgent || { id: "", name: "Assistant", avatar_color: "#6366f1" },
          timestamp: new Date(m.created_at),
        }));
        setMessages(mappedMessages);
        setCurrentThreadId(mostRecent.id);
      }
    } catch (error) {
      console.error("Failed to load thread:", error);
    } finally {
      setIsLoadingThread(false);
    }
  };

  const loadAgents = async () => {
    try {
      setLoading(true);
      const data = await apiGetAgents();
      const mappedAgents: Agent[] = data.map((a: ApiAgent) => {
        // Derive avatar key from avatar_color using AVATAR_COLORS index
        const colorIndex = AVATAR_COLORS.indexOf(a.avatar_color || "#6366f1");
        const avatarKey = colorIndex >= 0
          ? `avatar-${String(colorIndex + 1).padStart(2, '0')}`
          : 'avatar-01';

        return {
          id: a.id,
          name: a.name,
          avatar_color: a.avatar_color || "#6366f1",
          avatar: a.avatar || avatarKey,
        };
      });
      setLoadedAgents(mappedAgents);
      setAgents(mappedAgents);
      if (mappedAgents.length > 0 && !activeAgent) {
        setActiveAgent(mappedAgents[0]);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load agents";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const filteredAgents = agents.filter(a =>
    a.name.toLowerCase().includes(mentionFilter.toLowerCase())
  );

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

  const addFiles = (files: FileList | File[]) => {
    const newAttachments: ChatAttachment[] = [];
    Array.from(files).forEach(file => {
      const url = URL.createObjectURL(file);
      const isImage = file.type.startsWith("image/");
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
      if (isImage) {
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

  const selectAgent = (agent: Agent) => {
    const before = input.slice(0, mentionStartRef.current);
    const after = input.slice(inputRef.current?.selectionStart ?? input.length);
    setInput(before + after);
    setActiveAgent(agent);
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
    const atIndex = textBeforeCursor.lastIndexOf("@");

    if (atIndex !== -1 && (atIndex === 0 || textBeforeCursor[atIndex - 1] === " ")) {
      const query = textBeforeCursor.slice(atIndex + 1);
      if (!query.includes(" ")) {
        mentionStartRef.current = atIndex;
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
        if (filteredAgents[mentionIndex]) selectAgent(filteredAgents[mentionIndex]);
        return;
      }
      if (e.key === "Escape") {
        setShowMentions(false);
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = async () => {
    if (!activeAgent || (!input.trim() && attachments.length === 0) || isTyping) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: input.trim(),
      agent: activeAgent,
      timestamp: new Date(),
      attachments: attachments.length > 0 ? [...attachments] : undefined,
    };

    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setAttachments([]);
    setIsTyping(true);
    setSending(true);

    try {
      // Prepare attachments for API
      const apiAttachments = attachments.map(att => ({
        name: att.name,
        type: att.mimeType,
        data_base64: att.dataBase64 || att.url,
      }));

      const response = await apiSendChatMessage(
        activeAgent.id,
        input.trim() || (attachments.length > 0 ? "Attached files" : ""),
        currentThreadId,
        apiAttachments.length > 0 ? apiAttachments : undefined
      );

      // Update threadId if a new thread was created
      if (response.thread_id && !currentThreadId) {
        setCurrentThreadId(response.thread_id);
      }

      // Add initial assistant message placeholder FIRST (so it's in state when streaming tokens arrive)
      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        agent: activeAgent,
        timestamp: new Date(),
        messageId: response.message_id,
      };
      lastAssistantMessageIdRef.current = assistantMsg.id;
      setMessages(prev => [...prev, assistantMsg]);

      // Now start streaming (placeholder is now in state)
      let streamText = "";
      const cleanup = apiStreamChatResponse(
        response.message_id,
        (data) => {
          if (typeof data === 'string') {
            streamText += data;
            // Update assistant message with streaming content
            setMessages(prev => {
              const lastMsg = prev[prev.length - 1];
              if (lastMsg?.role === "assistant" && lastMsg.messageId === response.message_id && lastMsg.id === lastAssistantMessageIdRef.current) {
                return [...prev.slice(0, -1), { ...lastMsg, content: streamText }];
              }
              return prev;
            });
          } else if (typeof data === 'object' && data !== null) {
            const dataObj = data as Record<string, unknown>;
            if (typeof dataObj.content === 'string') {
              streamText += dataObj.content;
              setMessages(prev => {
                const lastMsg = prev[prev.length - 1];
                if (lastMsg?.role === "assistant" && lastMsg.messageId === response.message_id && lastMsg.id === lastAssistantMessageIdRef.current) {
                  return [...prev.slice(0, -1), { ...lastMsg, content: streamText }];
                }
                return prev;
              });
            }
          }
        },
        () => {
          setIsTyping(false);
          setSending(false);
        }
      );

      cleanupRef.current = cleanup;

    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to send message";
      toast({ title: "Error", description: message, variant: "destructive" });
      setIsTyping(false);
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col h-[calc(100vh-2rem)] max-w-4xl mx-auto items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div
      className="flex flex-col h-[calc(100vh-2rem)] max-w-4xl mx-auto"
      onDragOver={e => e.preventDefault()}
      onDrop={handleDrop}
    >
      {/* Header */}
      <div className="flex items-center gap-3 py-4 px-2 border-b border-border">
        <img src={getAvatarSrc(activeAgent?.avatar)} alt={activeAgent?.name || ""} className="h-9 w-9 rounded-lg object-cover" width={32} height={32} />
        <div>
          <h1 className="text-sm font-semibold text-foreground">Chat with {activeAgent?.name || "Select an agent"}</h1>
          <p className="text-xs text-muted-foreground">Type <kbd className="px-1.5 py-0.5 rounded bg-secondary text-foreground text-[10px] font-mono">@</kbd> to switch agents · Paste or drop files</p>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto py-6 px-2 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-4">
            <div className="h-16 w-16 rounded-2xl gradient-primary flex items-center justify-center">
              <Bot className="h-8 w-8 text-primary-foreground" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-foreground">Start a conversation</h2>
              <p className="text-sm text-muted-foreground mt-1 max-w-md">
                Chat with your agents. Use <kbd className="px-1.5 py-0.5 rounded bg-secondary text-foreground text-xs font-mono">@</kbd> to mention and switch between agents. Paste or drag images and files.
              </p>
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {agents.map(agent => (
                <button
                  key={agent.id}
                  onClick={() => setActiveAgent(agent)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-all ${
                    activeAgent?.id === agent.id
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border bg-card text-muted-foreground hover:border-primary/30"
                  }`}
                >
                  <img src={getAvatarSrc(agent.avatar)} alt={agent.name} className="h-5 w-5 rounded object-cover" width={20} height={20} />
                  {agent.name}
                </button>
              ))}
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
                <img src={getAvatarSrc(msg.agent?.avatar)} alt={msg.agent.name} className="h-8 w-8 rounded-lg object-cover flex-shrink-0 mt-1" width={32} height={32} />
              )}
              <div className={`max-w-[70%] ${msg.role === "user" ? "order-first" : ""}`}>
                <div className={`text-[10px] mb-1 ${msg.role === "user" ? "text-right" : "text-left"} text-muted-foreground`}>
                  {msg.role === "assistant" ? msg.agent.name : "You"}
                </div>
                <div
                  className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground rounded-br-md"
                      : "bg-secondary text-foreground rounded-bl-md"
                  }`}
                >
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-2">
                      {msg.attachments.map(att => (
                        att.type === "image" ? (
                          <img key={att.id} src={att.url} alt={att.name} className="max-w-[200px] max-h-[150px] rounded-lg object-cover" />
                        ) : (
                          <div key={att.id} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-background/20 text-xs">
                            <FileText className="h-4 w-4 flex-shrink-0" />
                            <span className="truncate max-w-[150px]">{att.name}</span>
                          </div>
                        )
                      ))}
                    </div>
                  )}
                  {msg.content || <span className="text-muted-foreground">...</span>}
                </div>
              </div>
              {msg.role === "user" && (
                <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center flex-shrink-0 mt-1">
                  <User className="h-4 w-4 text-muted-foreground" />
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {isTyping && activeAgent && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3 items-start">
            <img src={getAvatarSrc(activeAgent?.avatar)} alt={activeAgent?.name} className="h-8 w-8 rounded-lg object-cover" width={32} height={32} />
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
      <div className="relative border-t border-border p-4">
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
                <p className="text-[10px] text-muted-foreground px-2 py-1 uppercase tracking-wider font-medium">Switch agent</p>
                {filteredAgents.map((agent, i) => (
                  <button
                    key={agent.id}
                    onClick={() => selectAgent(agent)}
                    className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm transition-colors ${
                      i === mentionIndex ? "bg-accent text-accent-foreground ring-2 ring-accent" : "text-foreground hover:bg-accent/50"
                    }`}
                  >
                    <img src={getAvatarSrc(agent.avatar)} alt={agent.name} className="h-7 w-7 rounded object-cover" />
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
                  <img src={att.url} alt={att.name} className="h-16 w-16 rounded-lg object-cover border border-border" />
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
            <div className="flex items-center gap-2 mb-2">
              <img src={getAvatarSrc(activeAgent?.avatar)} alt={activeAgent?.name || ""} className="h-5 w-5 rounded object-cover" width={20} height={20} />
              <span className="text-xs text-muted-foreground">Talking to <span className="text-foreground font-medium">{activeAgent?.name || "..."}</span></span>
            </div>
            <div className="relative">
              <textarea
                ref={inputRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                onPaste={handlePaste}
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

      {/* Hidden file input */}
    </div>
  );
}
