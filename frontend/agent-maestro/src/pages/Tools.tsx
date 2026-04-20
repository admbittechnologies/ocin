import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Wrench, FileText, Globe, Clock, Pause, X, Bot, Loader2 } from "lucide-react";
import composioLogo from "@/assets/logos/composio.png";
import apifyLogo from "@/assets/logos/apify.png";
import matonLogo from "@/assets/logos/maton.png";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { apiGetTools, apiCreateTool, apiConnectTool, apiDisconnectTool, type Tool as ApiTool } from "@/lib/api";

interface Tool {
  id: string;
  name: string;
  icon?: React.ElementType;
  logo?: string;
  description: string;
  builtin: boolean;
  connected: boolean;
  configured?: boolean;
  source?: string;
  usedBy?: string[];
  type?: "composio" | "apify" | "maton";
}

const BUILTIN_TOOLS: Omit<Tool, "id" | "connected" | "agents">[] = [
  { name: "File", icon: FileText, description: "Read/write files", builtin: true },
  { name: "HTTP", icon: Globe, description: "Make HTTP requests", builtin: true },
  { name: "DateTime", icon: Clock, description: "Date and time utilities", builtin: true },
  { name: "Wait", icon: Pause, description: "Pause execution", builtin: true },
];

const EXTERNAL_TOOLS: Omit<Tool, "id" | "connected" | "agents" | "usedBy">[] = [
  { name: "Composio", logo: composioLogo, description: "Connect Gmail, Slack, Notion, GitHub and more via OAuth", builtin: false, type: "composio" },
  { name: "Apify", logo: apifyLogo, description: "Web scraping actors and automation", builtin: false, type: "apify" },
  { name: "Maton.ai", logo: matonLogo, description: "AI automation workflows", builtin: false, type: "maton" },
];

function isValidUUID(str: string): boolean {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return uuidRegex.test(str);
}

export default function Tools() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [connectDialog, setConnectDialog] = useState<Tool | null>(null);
  const [removeId, setRemoveId] = useState<string | null>(null);
  const [apiToken, setApiToken] = useState("");
  const [actorId, setActorId] = useState("");
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    loadTools();
  }, []);

  const loadTools = async () => {
    try {
      setLoading(true);
      const data = await apiGetTools();

      // Combine with built-in and external tool definitions
      const toolMap = new Map<string, ApiTool>();

      // Add external tools from API
      data.forEach(t => toolMap.set(t.id, t));

      // Create tool list with combined data
      const combinedTools: Tool[] = [];

      // Built-in tools (always available)
      BUILTIN_TOOLS.forEach(t => {
        combinedTools.push({
          id: t.name.toLowerCase(),
          ...t,
          connected: true, // Built-in tools are always connected
        });
      });

      // External tools
      EXTERNAL_TOOLS.forEach(t => {
        const apiTool = data.find(at => at.name.toLowerCase() === t.name.toLowerCase());
        // Use the actual UUID from API if the tool exists, otherwise use name as fallback
        const toolId = apiTool?.id || t.name.toLowerCase();
        combinedTools.push({
          id: toolId,
          ...t,
          connected: apiTool?.connected || apiTool?.configured || false,
          configured: apiTool?.configured || false,
          usedBy: apiTool?.usedBy || [],
        });
      });

      setTools(combinedTools);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load tools";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async () => {
    if (!connectDialog) return;
    if ((connectDialog.type === "apify" || connectDialog.type === "maton") && !apiToken.trim()) {
      toast({ title: "Error", description: "API token is required", variant: "destructive" });
      return;
    }

    try {
      setConnecting(true);

      // If tool ID is not a UUID, create the tool first
      let toolId = connectDialog.id;
      if (!isValidUUID(toolId) && connectDialog.type) {
        const newTool = await apiCreateTool(connectDialog.name, connectDialog.type);
        toolId = newTool.id;
      }

      const credentials: Record<string, string> = { api_token: apiToken };
      if (connectDialog.type === "apify" && actorId) {
        credentials.actor_id = actorId;
      }

      await apiConnectTool(toolId, credentials);
      toast({ title: `${connectDialog.name} connected!` });
      setConnectDialog(null);
      setApiToken("");
      setActorId("");
      await loadTools();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to connect tool";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setConnecting(false);
    }
  };

  const handleRemove = async () => {
    if (!removeId) return;
    try {
      await apiDisconnectTool(removeId);
      toast({ title: "Tool disconnected" });
      setRemoveId(null);
      await loadTools();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to disconnect tool";
      toast({ title: "Error", description: message, variant: "destructive" });
    }
  };

  const removeTool = tools.find(t => t.id === removeId);

  if (loading) {
    return (
      <div className="flex-1 min-h-0 flex items-center justify-center p-6 lg:p-8">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const connected = tools.filter(t => t.connected);
  const available = tools.filter(t => !t.connected);

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-8 p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Tools</h1>
        <p className="text-muted-foreground text-sm mt-1">Manage tools available to your agents</p>
      </div>

      <div>
        <h2 className="text-foreground font-semibold text-sm mb-4 flex items-center gap-2">
          <Wrench className="h-4 w-4 text-primary" /> Connected ({connected.length})
        </h2>
        {connected.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground text-sm">No tools connected yet</div>
        ) : (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {connected.map(tool => (
              <div key={tool.id} className="rounded-xl border border-border bg-card p-5 shadow-card">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    {tool.logo ? (
                      <img src={tool.logo} alt={tool.name} className="h-9 w-9 rounded-lg object-cover" loading="lazy" width={36} height={36} />
                    ) : (
                      <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center">
                        {tool.icon && <tool.icon className="h-4 w-4 text-primary" />}
                      </div>
                    )}
                    <div>
                      <h3 className="text-foreground font-medium text-sm">{tool.name}</h3>
                      {tool.builtin && <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Built-in</span>}
                    </div>
                  </div>
                  {!tool.builtin && (
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => setRemoveId(tool.id)}>
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mb-3">{tool.description}</p>
                {tool.usedBy && tool.usedBy.length > 0 && (
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Bot className="h-3 w-3" />
                    <span>Used by: {tool.usedBy.join(", ")}</span>
                  </div>
                )}
              </div>
            ))}
          </motion.div>
        )}
      </div>

      {available.length > 0 && (
        <div>
          <h2 className="text-foreground font-semibold text-sm mb-4">Available</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {available.map(tool => (
              <div key={tool.id} className="rounded-xl border border-border bg-card/50 p-5">
                <div className="flex items-center gap-3 mb-3">
                  {tool.logo ? (
                    <img src={tool.logo} alt={tool.name} className="h-9 w-9 rounded-lg object-cover" loading="lazy" width={36} height={36} />
                  ) : (
                    <div className="h-9 w-9 rounded-lg bg-muted flex items-center justify-center">
                      {tool.icon && <tool.icon className="h-4 w-4 text-muted-foreground" />}
                    </div>
                  )}
                  <div>
                    <h3 className="text-foreground font-medium text-sm">{tool.name}</h3>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mb-4">{tool.description}</p>
                <Button size="sm" variant="outline" className="border-border text-foreground" onClick={() => setConnectDialog(tool)}>
                  Connect
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      <Dialog open={!!connectDialog} onOpenChange={open => !open && setConnectDialog(null)}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle className="text-foreground">Connect {connectDialog?.name}</DialogTitle>
          </DialogHeader>
          {connectDialog?.type === "composio" ? (
            <p className="text-muted-foreground text-sm">This will open an OAuth flow to connect your apps. Click connect to proceed.</p>
          ) : (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label className="text-foreground text-sm">API Token</Label>
                <Input value={apiToken} onChange={e => setApiToken(e.target.value)} className="bg-secondary border-border font-mono text-sm" placeholder="Paste your API token" />
              </div>
              {connectDialog?.type === "apify" && (
                <div className="space-y-2">
                  <Label className="text-foreground text-sm">Actor ID</Label>
                  <Input value={actorId} onChange={e => setActorId(e.target.value)} className="bg-secondary border-border font-mono text-sm" placeholder="apify/web-scraper" />
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConnectDialog(null)} className="border-border text-foreground">Cancel</Button>
            <Button onClick={handleConnect} disabled={connecting} className="gradient-primary text-primary-foreground">
              {connecting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Connect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!removeId} onOpenChange={open => !open && setRemoveId(null)}>
        <AlertDialogContent className="bg-card border-border">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-foreground">Remove {removeTool?.name}?</AlertDialogTitle>
            <AlertDialogDescription className="text-muted-foreground">
              {removeTool?.usedBy && removeTool.usedBy.length > 0
                ? `This tool is used by: ${removeTool.usedBy.join(", ")}. Those agents will lose access.`
                : "This tool is not currently used by any agents."
              }
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-border text-foreground">Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleRemove} className="bg-destructive text-destructive-foreground">Remove</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
