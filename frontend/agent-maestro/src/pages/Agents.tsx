import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Bot, Plus, Search, MoreVertical, Pencil, Trash2, Check, Loader2, Brain, Clock, PlusCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { EmptyState } from "@/components/EmptyState";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useToast } from "@/hooks/use-toast";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { AVATARS, AVATAR_MAP } from "@/lib/avatars";
import { useAgentAvatar, invalidateAgentAvatar, slugToSrc } from "@/lib/agentAvatar";
import ocinAvatar from "@/assets/avatars/ocin-avatar.png";
import { ScrollArea } from "@/components/ui/scroll-area";
import { apiGetAgents, apiCreateAgent, apiUpdateAgent, apiDeleteAgent, apiGetApiKeys, apiGetProviderModels, apiToggleAgent, apiGetAgentMemory, apiSetAgentMemory, apiDeleteAgentMemory } from "@/lib/api";

// Backend returns avatar as a slug string (e.g., "avatar-07")
interface Agent {
  id: string;
  name: string;
  description: string;
  avatar: string;
  user_id: string;
  role: string;
  provider: string;
  model_id: string;
  temperature: number;
  system_prompt: string;
  is_active: boolean;
  tools: string[];
}

const ALL_PROVIDERS = ["OpenAI", "Anthropic", "Google", "Ollama", "OpenRouter", "Mistral", "Grok", "Qwen", "DeepSeek", "Z.ai"];
const roles: Agent["role"][] = ["coordinator", "worker", "standalone"];

const OCIN_ID = "ocin";

// Backend stores avatar as slug, we use slugToSrc to resolve to PNG
const emptyAgent = {
  id: "",
  name: "",
  description: "",
  avatar: "avatar-01",
  role: "standalone",
  provider: "",
  model_id: "",
  temperature: 0.5,
  system_prompt: "",
  is_active: true,
  tools: [],
  user_id: "",
};

// Helper function to format relative time
function formatRelativeTime(timestamp: string): string {
  const now = new Date();
  const then = new Date(timestamp);
  const diffMs = now.getTime() - then.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return `${diffSecs}s ago`;
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

// Helper function to generate a slug from text
function generateSlug(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s]/g, '')
    .replace(/\s+/g, '-')
    .substring(0, 50);
}

// Subcomponent for agent list items - uses useAgentAvatar hook for proper caching
function AgentListItem({ agent, onEdit, onDelete, onToggleActive }: {
  agent: Agent;
  onEdit: (agent: Agent) => void;
  onDelete: (id: string) => void;
  onToggleActive: (id: string, active: boolean) => void;
}) {
  const avatarSrc = useAgentAvatar(agent.id);

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card hover:border-primary/20 transition-all">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <img src={avatarSrc} alt={agent.name} className="h-10 w-10 rounded-lg object-cover" loading="lazy" width={40} height={40} />
          <div>
            <h3 className="text-foreground font-medium text-sm">{agent.name}</h3>
            <span className="text-xs text-muted-foreground capitalize">{agent.role} · {agent.provider}</span>
          </div>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground">
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="bg-card border-border">
            <DropdownMenuItem onClick={() => onEdit(agent)}>
              <Pencil className="h-4 w-4 mr-2" /> Edit
            </DropdownMenuItem>
            {agent.id !== OCIN_ID && (
              <DropdownMenuItem onClick={() => onDelete(agent.id)} className="text-destructive">
                <Trash2 className="h-4 w-4 mr-2" /> Delete
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <p className="text-xs text-muted-foreground mb-4 line-clamp-2">{agent.description}</p>
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono text-muted-foreground">{agent.model_id}</span>
        <Switch
          checked={agent.is_active}
          onCheckedChange={async checked => {
            try {
              await apiToggleAgent(agent.id, checked);
              onToggleActive(agent.id, checked);
            } catch (error) {
              const message = error instanceof Error ? error.message : "Failed to update agent";
              toast({ title: "Error", description: message, variant: "destructive" });
            }
          }}
        />
      </div>
    </div>
  );
}

export default function Agents() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [search, setSearch] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [editingAgent, setEditingAgent] = useState<Agent & { id?: string }>(emptyAgent);
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [providerModels, setProviderModels] = useState<Record<string, string[]>>({});
  const [loadingModels, setLoadingModels] = useState<Record<string, boolean>>({});

  // Memory management state
  const [advancedOpen, setAdvancedOpen] = useState<Record<string, boolean>>({});
  const [memoryFacts, setMemoryFacts] = useState<Array<{ key: string; value: string; updated_at: string }>>([]);
  const [memorySearch, setMemorySearch] = useState("");
  const [addFactOpen, setAddFactOpen] = useState(false);
  const [editingFact, setEditingFact] = useState<{ key: string; value: string } | null>(null);
  const [deletingFact, setDeletingFact] = useState<string | null>(null);
  const [loadingMemory, setLoadingMemory] = useState(false);

  const configuredProviders = ALL_PROVIDERS.filter(p => {
    const key = apiKeys[p];
    return key && key.length > 0 && !key.startsWith("...");
  });

  const filtered = agents.filter(a => a.name.toLowerCase().includes(search.toLowerCase()));

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [agentsData, keysData] = await Promise.all([
        apiGetAgents(),
        apiGetApiKeys(),
      ]);
      console.log("Loaded agents:", agentsData);
      console.log("Loaded API keys:", keysData);
      setAgents(agentsData);
      setApiKeys(keysData);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load data";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleProviderChange = async (provider: string) => {
    setEditingAgent(prev => ({ ...prev, provider, model_id: "" }));
    setProviderModels(prev => ({ ...prev, [provider]: [] }));

    if (!provider) return;

    try {
      setLoadingModels(prev => ({ ...prev, [provider]: true }));
      const data = await apiGetProviderModels(provider);
      setProviderModels(prev => ({ ...prev, [provider]: data.models }));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load models";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setLoadingModels(prev => ({ ...prev, [provider]: false }));
    }
  };

  const handleSave = async () => {
    if (!editingAgent.name.trim()) {
      toast({ title: "Error", description: "Agent name is required", variant: "destructive" });
      return;
    }
    if (!editingAgent.provider) {
      toast({ title: "Error", description: "Provider is required", variant: "destructive" });
      return;
    }
    if (!editingAgent.model_id) {
      toast({ title: "Error", description: "Model ID is required", variant: "destructive" });
      return;
    }

    try {
      if (editingAgent.id) {
        await apiUpdateAgent(editingAgent.id, {
          name: editingAgent.name,
          description: editingAgent.description,
          avatar: editingAgent.avatar,
          role: editingAgent.role,
          model_provider: editingAgent.provider,
          model_id: editingAgent.model_id,
          temperature: editingAgent.temperature,
          system_prompt: editingAgent.system_prompt,
          tools: editingAgent.tools,
        });
        toast({ title: "Agent updated" });
        // Invalidate avatar cache after editing
        invalidateAgentAvatar(editingAgent.id);
      } else {
        await apiCreateAgent({
          name: editingAgent.name,
          description: editingAgent.description,
          avatar: editingAgent.avatar,
          role: editingAgent.role,
          model_provider: editingAgent.provider,
          model_id: editingAgent.model_id,
          temperature: editingAgent.temperature,
          system_prompt: editingAgent.system_prompt,
          tools: editingAgent.tools,
        });
        toast({ title: "Agent created" });
      }
      await loadData();
      setFormOpen(false);
      setEditingAgent(emptyAgent);
      setProviderModels({});
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save agent";
      toast({ title: "Error", description: message, variant: "destructive" });
    }
  };

  const handleDelete = async () => {
    if (!deleteId) return;

    try {
      await apiDeleteAgent(deleteId);
      toast({ title: "Agent deleted" });
      await loadData();
      setDeleteId(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete agent";
      toast({ title: "Error", description: message, variant: "destructive" });
    }
  };

  const handleEdit = (agent: Agent) => {
    setEditingAgent({
      ...agent,
      model_id: agent.model_id || "",
      system_prompt: agent.system_prompt || "",
      temperature: agent.temperature ?? 0.5,
    });
    setFormOpen(true);
    if (agent.provider && !providerModels[agent.provider]) {
      handleProviderChange(agent.provider);
    }

    // Load advanced toggle state from localStorage
    const savedToggle = localStorage.getItem(`ocin_agent_advanced_${agent.id}`);
    setAdvancedOpen(prev => ({ ...prev, [agent.id]: savedToggle === 'true' }));
  };

  const handleAdvancedToggle = (agentId: string, isOpen: boolean) => {
    setAdvancedOpen(prev => ({ ...prev, [agentId]: isOpen }));
    localStorage.setItem(`ocin_agent_advanced_${agentId}`, isOpen.toString());
    if (isOpen && editingAgent.id) {
      loadAgentMemory(editingAgent.id);
    }
  };

  const loadAgentMemory = async (agentId: string) => {
    if (!agentId) return;
    try {
      setLoadingMemory(true);
      const facts = await apiGetAgentMemory(agentId);
      setMemoryFacts(facts);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load agent memory";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setLoadingMemory(false);
    }
  };

  const handleAddFact = async (value: string) => {
    if (!editingAgent.id || !value.trim()) return;
    try {
      const key = generateSlug(value);
      await apiSetAgentMemory(editingAgent.id, key, value);
      await loadAgentMemory(editingAgent.id);
      setAddFactOpen(false);
      toast({ title: "Fact saved" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save fact";
      toast({ title: "Error", description: message, variant: "destructive" });
    }
  };

  const handleEditFact = async (value: string) => {
    if (!editingFact) return;
    try {
      await apiSetAgentMemory(editingAgent.id, editingFact.key, value);
      await loadAgentMemory(editingAgent.id);
      setEditingFact(null);
      toast({ title: "Fact updated" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update fact";
      toast({ title: "Error", description: message, variant: "destructive" });
    }
  };

  const handleDeleteFact = async () => {
    if (!editingAgent.id || !deletingFact) return;
    try {
      await apiDeleteAgentMemory(editingAgent.id, deletingFact);
      await loadAgentMemory(editingAgent.id);
      setDeletingFact(null);
      toast({ title: "Fact removed" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete fact";
      toast({ title: "Error", description: message, variant: "destructive" });
    }
  };

  const filteredMemoryFacts = memoryFacts.filter(fact =>
    fact.value.toLowerCase().includes(memorySearch.toLowerCase())
  );

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-6 p-6 lg:p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Agents</h1>
          <p className="text-muted-foreground text-sm mt-1">Manage your AI agents</p>
        </div>
        <Button className="gradient-primary text-primary-foreground" onClick={() => { setEditingAgent(emptyAgent); setFormOpen(true); }}>
          <Plus className="h-4 w-4 mr-2" /> Create agent
        </Button>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input placeholder="Search agents..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9 bg-secondary border-border" />
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState icon={Bot} title="No agents yet" description="Create your first AI agent to get started." actionLabel="Create agent" onAction={() => { setEditingAgent(emptyAgent); setFormOpen(true); }} />
      ) : (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(agent => (
            <AgentListItem
              key={agent.id}
              agent={agent}
              onEdit={handleEdit}
              onDelete={setDeleteId}
              onToggleActive={(id, active) => setAgents(prev => prev.map(a => a.id === id ? { ...a, is_active: active } : a))}
            />
          ))}
        </motion.div>
      )}

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="bg-card border-border max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-foreground">{editingAgent.id ? "Edit Agent" : "Create Agent"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Name</Label>
              <Input value={editingAgent.name} onChange={e => setEditingAgent(prev => ({ ...prev, name: e.target.value }))} className="bg-secondary border-border" placeholder="My Agent" />
            </div>
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Description</Label>
              <Input value={editingAgent.description} onChange={e => setEditingAgent(prev => ({ ...prev, description: e.target.value }))} className="bg-secondary border-border" placeholder="What does this agent do?" />
            </div>
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Avatar</Label>
              <ScrollArea className="h-[180px] rounded-lg border border-border bg-secondary/50 p-3">
                <div className="grid grid-cols-6 gap-2">
                  {AVATARS.map((src, i) => {
                    const slug = `avatar-${String(i + 1).padStart(2, '0')}`;
                    return (
                      <button
                        key={slug}
                        type="button"
                        onClick={() => setEditingAgent(prev => ({ ...prev, avatar: slug }))}
                        className={`relative h-14 w-14 rounded-lg border-2 overflow-hidden transition-all hover:scale-105 ${
                          editingAgent.avatar === slug
                            ? "border-primary ring-1 ring-primary/40"
                            : "border-transparent hover:border-border"
                        }`}
                      >
                        <img src={src} alt={`Avatar ${i + 1}`} className="h-full w-full object-cover" loading="lazy" width={56} height={56} />
                        {editingAgent.avatar === slug && (
                          <div className="absolute inset-0 bg-primary/20 flex items-center justify-center">
                            <Check className="h-4 w-4 text-primary" />
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </ScrollArea>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-foreground text-sm">Role</Label>
                <Select value={editingAgent.role} onValueChange={v => setEditingAgent(prev => ({ ...prev, role: v as Agent["role"] }))}>
                  <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    {roles.map(r => <SelectItem key={r} value={r} className="capitalize">{r}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-foreground text-sm">Provider</Label>
                {configuredProviders.length === 0 ? (
                  <div className="text-xs text-muted-foreground italic">Add API keys in Settings first</div>
                ) : (
                  <Select value={editingAgent.provider} onValueChange={handleProviderChange} disabled={configuredProviders.length === 0}>
                    <SelectTrigger className="bg-secondary border-border">
                      {loadingModels[editingAgent.provider] ? <Loader2 className="h-4 w-4 animate-spin" /> : <SelectValue placeholder="Select provider" />}
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      {configuredProviders.map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Model</Label>
              {loadingModels[editingAgent.provider] ? (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" /> Loading models...
                </div>
              ) : providerModels[editingAgent.provider] && providerModels[editingAgent.provider].length > 0 ? (
                <Select value={editingAgent.model_id} onValueChange={v => setEditingAgent(prev => ({ ...prev, model_id: v }))}>
                  <SelectTrigger className="bg-secondary border-border font-mono text-sm"><SelectValue placeholder="Select model" /></SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    {providerModels[editingAgent.provider].map(m => <SelectItem key={m} value={m} className="font-mono text-xs">{m}</SelectItem>)}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  value={editingAgent.model_id}
                  onChange={e => setEditingAgent(prev => ({ ...prev, model_id: e.target.value }))}
                  className="bg-secondary border-border font-mono text-sm"
                  placeholder={editingAgent.provider ? "Enter model ID" : "Select a provider first"}
                  disabled={!editingAgent.provider}
                />
              )}
            </div>
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Temperature: {editingAgent.temperature.toFixed(1)}</Label>
              <Slider value={[editingAgent.temperature]} onValueChange={v => setEditingAgent(prev => ({ ...prev, temperature: v[0] }))} min={0} max={1} step={0.1} className="py-2" />
            </div>
            <div className="space-y-2">
              <Label className="text-foreground text-sm">System Prompt</Label>
              <Textarea value={editingAgent.system_prompt} onChange={e => setEditingAgent(prev => ({ ...prev, system_prompt: e.target.value }))} className="bg-secondary border-border min-h-[100px] font-mono text-sm" placeholder="You are a helpful assistant..." />
            </div>
          </div>

          {editingAgent.id && (
            <>
              <div className="flex items-center justify-between pt-4 border-t border-border/50">
                <Label className="text-foreground text-sm font-medium">Show advanced options</Label>
                <Switch
                  checked={advancedOpen[editingAgent.id] || false}
                  onCheckedChange={checked => handleAdvancedToggle(editingAgent.id, checked)}
                  className="data-[state=checked]:bg-primary"
                />
              </div>

              {advancedOpen[editingAgent.id] && (
                <div className="space-y-4 pt-4 border-t border-border/50">
                  <div>
                    <h3 className="text-foreground font-semibold text-lg flex items-center gap-2">
                      <Brain className="h-5 w-5" />
                      What this agent knows about you
                    </h3>
                    <p className="text-muted-foreground text-sm mt-1">Facts this agent has learned from your conversations.</p>
                  </div>

                  <div className="flex items-center justify-between gap-3">
                    {memoryFacts.length >= 5 && (
                      <div className="relative max-w-sm flex-1">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                          placeholder="Search facts..."
                          value={memorySearch}
                          onChange={e => setMemorySearch(e.target.value)}
                          className="pl-9 bg-secondary border-border"
                        />
                      </div>
                    )}
                    <Button size="sm" onClick={() => setAddFactOpen(true)} className="gradient-primary text-primary-foreground">
                      <PlusCircle className="h-4 w-4 mr-2" /> Add a fact
                    </Button>
                  </div>

                  <ScrollArea className="max-h-[300px] overflow-y-auto rounded-lg border border-border bg-secondary/30">
                    {loadingMemory ? (
                      <div className="flex items-center justify-center py-8">
                        <Loader2 className="h-6 w-6 animate-spin text-primary" />
                      </div>
                    ) : filteredMemoryFacts.length === 0 ? (
                      <EmptyState
                        icon={Brain}
                        title="Nothing yet"
                        description="This agent hasn't learned anything yet. As you chat, facts will appear here. You can also add them manually."
                      />
                    ) : (
                      <div className="space-y-3 p-4">
                        {filteredMemoryFacts.map(fact => (
                          <div key={fact.key} className="group rounded-lg border border-border bg-card/50 p-4 hover:border-primary/30 transition-all">
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex-1 min-w-0">
                                <p className="text-foreground text-sm break-words">{fact.value}</p>
                                <div className="flex items-center gap-2 mt-2">
                                  <span className="text-xs text-muted-foreground font-mono">{fact.key}</span>
                                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                                    <Clock className="h-3 w-3" />
                                    {formatRelativeTime(fact.updated_at)}
                                  </span>
                                </div>
                              </div>
                              <div className="flex items-center gap-1">
                                <Button
                                  size="icon"
                                  variant="ghost"
                                  onClick={() => setEditingFact({ key: fact.key, value: fact.value })}
                                  className="h-8 w-8 text-muted-foreground hover:text-foreground"
                                >
                                  <Pencil className="h-4 w-4" />
                                </Button>
                                <Button
                                  size="icon"
                                  variant="ghost"
                                  onClick={() => setDeletingFact(fact.key)}
                                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </ScrollArea>
                </div>
              )}
            </>
          )}

          <DialogFooter>
            <Button variant="pointline" onClick={() => setFormOpen(false)} className="border-border text-foreground">Cancel</Button>
            <Button onClick={handleSave} className="gradient-primary text-primary-foreground">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteId} onOpenChange={open => !open && setDeleteId(null)}>
        <AlertDialogContent className="bg-card border-border">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-foreground">Delete agent?</AlertDialogTitle>
            <AlertDialogDescription className="text-muted-foreground">This action cannot be undone. The agent and its configuration will be permanently deleted.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-border text-foreground">Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={addFactOpen} onOpenChange={setAddFactOpen}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle className="text-foreground">Add a fact</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-foreground text-sm">What should this agent remember?</Label>
              <Textarea
                id="add-fact-textarea"
                placeholder="e.g. I prefer responses in Spanish"
                className="bg-secondary border-border min-h-[100px] resize-none"
                autoFocus
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    const textarea = document.getElementById('add-fact-textarea') as HTMLTextAreaElement;
                    if (textarea) handleAddFact(textarea.value);
                  }
                }}
              />
              <p className="text-xs text-muted-foreground mt-1">
                Reference key will be auto-generated from first few words
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="pointline" onClick={() => setAddFactOpen(false)} className="border-border text-foreground">Cancel</Button>
            <Button
              onClick={() => {
                const textarea = document.getElementById('add-fact-textarea') as HTMLTextAreaElement;
                if (textarea) handleAddFact(textarea.value);
              }}
              className="gradient-primary text-primary-foreground"
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!editingFact} onOpenChange={open => !open && setEditingFact(null)}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle className="text-foreground">Edit fact</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Reference key</Label>
              <div className="text-xs text-muted-foreground font-mono bg-secondary/50 rounded px-2 py-1 inline-block">
                {editingFact?.key}
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Value</Label>
              <Textarea
                value={editingFact?.value || ""}
                onChange={e => setEditingFact(prev => prev ? { ...prev, value: e.target.value } : null)}
                className="bg-secondary border-border min-h-[100px] resize-none"
                autoFocus
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="pointline" onClick={() => setEditingFact(null)} className="border-border text-foreground">Cancel</Button>
            <Button
              onClick={() => editingFact && handleEditFact(editingFact.value)}
              className="gradient-primary text-primary-foreground"
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deletingFact} onOpenChange={open => !open && setDeletingFact(null)}>
        <AlertDialogContent className="bg-card border-border">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-foreground">Remove this fact?</AlertDialogTitle>
            <AlertDialogDescription className="text-muted-foreground">
              This agent will no longer remember this.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-border text-foreground">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteFact}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
