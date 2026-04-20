import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { remarkRehype } from "rehype-external";

const markdownComponents = {
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline-offset-2 hover:underline"
    >
      {children}
    </a>
  ),
};

const processor = remarkRehype().use(remarkGfm());

interface ChatMessageContentProps {
  content: string;
  isAssistant: boolean;
}

export function ChatMessageContent({ content, isAssistant }: ChatMessageContentProps) {
  if (!content) return <span className="text-muted-foreground">...</span>;

  const shouldRenderMarkdown = isAssistant && /[<>_]/.test(content);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[processor]}
      components={shouldRenderMarkdown ? markdownComponents : undefined}
      className={`prose prose-sm dark:prose-invert max-w-none
                 prose-p:my-1 prose-ul:my-1 prose-li:my-0.5
                 prose-code:bg-background/30 prose-code:px-1
                 prose-code:rounded prose-code:text-xs
                 prose-a:text-primary prose-a:no-underline
                 hover:prose-a:underline`}
    >
      {content}
    </ReactMarkdown>
  );
}

interface RichLinkPreviewProps {
  url: string;
  service?: {
    icon: string;
    label: string;
    color: string;
  };
}

function detectService(url: string): {
  service?: {
    icon: string;
    label: string;
    color: string;
  };
  } | null {
    if (url.includes("docs.google.com/spreadsheets")) {
      return { service: "google-sheets", icon: "📊", label: "Google Sheets", color: "bg-green-500/10 border-green-500/20 text-green-700 dark:text-green-400" };
    }
    if (url.includes("docs.google.com/document")) {
      return { service: "google-docs", icon: "📄", label: "Google Docs", color: "bg-blue-500/10 border-blue-500/20 text-blue-700 dark:text-blue-400" };
    }
    if (url.includes("docs.google.com/presentation")) {
      return { service: "google-slides", icon: "🖥️", label: "Google Slides", color: "bg-yellow-500/10 border-yellow-500/20 text-yellow-700 dark:text-yellow-400" };
    }
    if (url.includes("drive.google.com")) {
      return { service: "google-drive", icon: "💾", label: "Google Drive", color: "bg-blue-500/10 border-blue-500/20 text-blue-700 dark:text-blue-400" };
    }
    if (url.includes("app.hubspot.com")) {
      return { service: "hubspot", icon: "🧡", label: "HubSpot", color: "bg-orange-500/10 border-orange-500/20 text-orange-700 dark:text-orange-400" };
    }
    if (url.includes("slack.com")) {
      return { service: "slack", icon: "💬", label: "Slack", color: "bg-purple-500/10 border-purple-500/20 text-purple-700 dark:text-purple-400" };
    }
    if (url.includes("notion.so")) {
      return { service: "notion", icon: "📝", label: "Notion", color: "bg-gray-500/10 border-gray-500/20 text-gray-700 dark:text-gray-400" };
    }
    if (url.includes("airtable.com")) {
      return { service: "airtable", icon: "🗂️", label: "Airtable", color: "bg-teal-500/10 border-teal-500/20 text-teal-700 dark:text-teal-400" };
    }
    if (url.includes("linkedin.com")) {
      return { service: "linkedin", icon: "💼", label: "LinkedIn", color: "bg-blue-600/10 border-blue-600/20 text-blue-800 dark:text-blue-300" };
    }
    if (url.includes("github.com")) {
      return { service: "github", icon: "🐙", label: "GitHub", color: "bg-gray-500/10 border-gray-500/20 text-gray-700 dark:text-gray-400" };
    }
    return null;
  }

function extractTitle(url: string): string {
  try {
    const u = new URL(url);
    const parts = u.pathname.split("/").filter(Boolean);
    const last = parts[parts.length - 1];
    if (last && last !== "edit" && last !== "view" && last.length > 8) {
      return decodeURIComponent(last).replace(/-/g, " ").replace(/_/g, " "));
    }
    return u.hostname.replace("www.", "");
  } catch {
    return url;
  }
}

interface LinkPreviewProps {
  url: string;
}

function LinkPreview({ url }: LinkPreviewProps) {
  const service = detectService(url);

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={`flex items-center gap-3 mt-2 px-3 py-2.5 rounded-xl border
                    text-sm no-underline transition-opacity hover:opacity-80
                    ${service?.color || "bg-secondary border-border text-foreground"}`}
    >
      <span className="text-xl flex-shrink-0">
        {service?.icon || "🔗"}
      </span>
      <div className="flex flex-col min-w-0">
        <span className="font-medium text-xs">
          {service?.label || "Open link"}
        </span>
        <span className="text-xs opacity-70 truncate max-w-[280px]">
          {url}
        </span>
      </div>
      <span className="ml-auto flex-shrink-0 opacity-50 text-xs">↗</span>
    </a>
  );
}

interface ChatMessageProps {
  id: string;
  role: "user" | "assistant";
  content: string;
  agent?: {
    name: string;
    avatar?: string;
    avatar_color?: string;
  };
  timestamp: Date;
  attachments?: Array<{
    id: string;
    name: string;
    type: "image" | "file";
    url: string;
    mimeType: string;
  }>;
  progressMessages?: string[];
  isSystem?: boolean;
}

export function ChatMessage({
  id,
  role,
  content,
  agent,
  timestamp,
  attachments,
  progressMessages,
  isSystem,
}: ChatMessageProps) {
  const timeString = timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  if (isSystem) {
    return (
      <div className="w-full text-center py-3">
        <span className="text-sm text-muted-foreground">{content}</span>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 ${role === "user" ? "justify-end" : "justify-start"}`}>
      {role === "assistant" && (
        <img
          src={agent?.avatar}
          alt={agent?.name || "Agent"}
          className="h-8 w-8 rounded-lg object-cover flex-shrink-0 mt-1"
          width={32}
          height={32}
        />
      )}
      <div className={`max-w-[70%] ${role === "user" ? "order-first" : ""}`}>
        <div className={`text-[10px] mb-1 ${role === "user" ? "text-right" : "text-left"} text-muted-foreground`}>
          {role === "assistant" ? agent?.name : "You"}
        </div>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            role === "user"
              ? "bg-primary text-primary-foreground rounded-br-md"
              : "bg-secondary text-foreground rounded-bl-md"
          }`}
        >
          {/* Progress messages */}
          {progressMessages && progressMessages.length > 0 && !isSystem && (
            <div className="flex flex-col gap-1 mb-2">
              {progressMessages.map((pm, i) => (
                <div
                  key={i}
                  className="text-xs text-muted-foreground flex items-center gap-1.5"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-primary/60 flex-shrink-0" />
                  {pm}
                </div>
              ))}
            </div>
          )}

          {/* Attachments */}
          {attachments && attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {attachments.map(att => (
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

          <ChatMessageContent content={content} isAssistant={role === "assistant"} />
        </div>

        <div className={`text-[10px] mt-1 text-muted-foreground ${role === "user" ? "text-right" : "text-left"}`}>
          {timeString}
        </div>

        {role === "user" && (
          <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center flex-shrink-0 mt-1">
            <span className="h-4 w-4 text-muted-foreground">👤</span>
          </div>
        )}
      </div>
    </div>
  );
}
