import { useState, useEffect, useMemo } from "react";
import { motion } from "framer-motion";
import { Textarea } from "@/components/ui/textarea";
import { Calendar, Plus, Pencil, Trash2, Copy, Webhook, Loader2, Clock, Bot, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/EmptyState";
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
import {
  apiGetSchedules,
  apiCreateSchedule,
  apiUpdateSchedule,
  apiDeleteSchedule,
  apiToggleSchedule,
  apiGetAgents,
} from "@/lib/api";

type TriggerType = "cron" | "webhook" | "event";

// Backend-shape schedule (snake_case) — matches ScheduleOut in the API.
interface ApiSchedule {
  id: string;
  user_id: string;
  agent_id: string;
  agent_name?: string | null;
  label: string;
  cron_expression: string;
  trigger_type: string;
  payload: Record<string, any>;
  is_active: boolean;
  last_run_at?: string | null;
  next_run_at?: string | null;
  // Legacy camelCase fallbacks (in case a response still uses them)
  agentId?: string;
  agentName?: string;
  triggerType?: string;
  isActive?: boolean;
  nextRunAt?: string | null;
  lastRunAt?: string | null;
  cronExpression?: string;
}

interface EditingState {
  id?: string;
  label: string;
  agent_id: string;
  trigger_type: TriggerType;
}

export default function Schedules() {
  const [schedules, setSchedules] = useState<ApiSchedule[]>([]);
  const [agents, setAgents] = useState<{ id: string; name: string }[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [editing, setEditing] = useState<EditingState>({
    label: "",
    agent_id: "",
    trigger_type: "cron",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [schedulesData, agentsData] = await Promise.all([
        apiGetSchedules(),
        apiGetAgents(),
      ]);
      setSchedules((schedulesData ?? []) as ApiSchedule[]);
      setAgents((agentsData ?? []).map((a: any) => ({ id: a.id, name: a.name })));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load schedules";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  // Fallback lookup map from fetched agents list — used if the backend doesn't
  // populate agent_name in the response yet.
  const agentNameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const a of agents) m.set(a.id, a.name);
    return m;
  }, [agents]);

  const getAgentName = (s: ApiSchedule): string => {
    return (
      s.agent_name ||
      s.agentName ||
      agentNameById.get(s.agent_id || s.agentId || "") ||
      "—"
    );
  };

  const getAgentId = (s: ApiSchedule): string => s.agent_id || s.agentId || "";

  const getTriggerType = (s: ApiSchedule): string =>
    s.trigger_type || s.triggerType || "cron";

  const getIsActive = (s: ApiSchedule): boolean =>
    s.is_active !== undefined ? s.is_active : (s.isActive ?? false);

  const getNextRunAt = (s: ApiSchedule): string | null =>
    s.next_run_at ?? s.nextRunAt ?? null;

  const getLastRunAt = (s: ApiSchedule): string | null =>
    s.last_run_at ?? s.lastRunAt ?? null;

  const getExtractedInput = (s: ApiSchedule): string | null => {
    const payload = s.payload || {};
    const input = payload.input;
    if (typeof input === "string" && input.trim().length > 0) return input;
    return null;
  };

  // Formats an ISO date as "in 2 min" for future times and "2 min ago" for past times.
  const formatRelative = (iso: string | null): string => {
    if (!iso) return "—";
    const date = new Date(iso);
    if (isNaN(date.getTime())) return "—";
    const now = new Date();
    const diffMs = date.getTime() - now.getTime(); // positive => future
    const absMs = Math.abs(diffMs);
    const mins = Math.floor(absMs / 60_000);
    const hours = Math.floor(absMs / 3_600_000);
    const days = Math.floor(absMs / 86_400_000);

    const direction = diffMs >= 0 ? "in " : "";
    const suffix = diffMs >= 0 ? "" : " ago";

    if (mins < 1) return diffMs >= 0 ? "soon" : "just now";
    if (mins < 60) return `${direction}${mins} min${suffix}`;
    if (hours < 24) return `${direction}${hours}h${suffix}`;
    if (days < 7) return `${direction}${days}d${suffix}`;
    return date.toLocaleDateString();
  };

  const openCreate = () => {
    setEditing({ label: "", agent_id: "", trigger_type: "cron" });
    setFormOpen(true);
  };

  const openEdit = (s: ApiSchedule) => {
    setEditing({
      id: s.id,
      label: s.label,
      agent_id: getAgentId(s),
      trigger_type: (getTriggerType(s) as TriggerType) || "cron",
    });
    setFormOpen(true);
  };

  const handleSave = async () => {
    if (!editing.label.trim()) {
      toast({
        title: "Error",
        description: "Schedule description is required",
        variant: "destructive",
      });
      return;
    }
    if (!editing.agent_id) {
      toast({
        title: "Error",
        description: "Please select an agent",
        variant: "destructive",
      });
      return;
    }

    try {
      setSaving(true);
      const payload = {
        label: editing.label,
        agent_id: editing.agent_id,
        trigger_type: editing.trigger_type,
      };

      if (editing.id) {
        await apiUpdateSchedule(editing.id, payload);
        toast({ title: "Schedule updated" });
      } else {
        await apiCreateSchedule(payload);
        toast({ title: "Schedule created" });
      }
      setFormOpen(false);
      setEditing({ label: "", agent_id: "", trigger_type: "cron" });
      await loadData();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save schedule";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await apiDeleteSchedule(deleteId);
      toast({ title: "Schedule deleted" });
      setDeleteId(null);
      await loadData();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete schedule";
      toast({ title: "Error", description: message, variant: "destructive" });
    }
  };

  const handleToggle = async (s: ApiSchedule, newActive: boolean) => {
    try {
      await apiToggleSchedule(s.id, newActive);
      // Optimistic update of the local list, then reload to refresh next_run_at
      setSchedules((prev) =>
        prev.map((x) => (x.id === s.id ? { ...x, is_active: newActive, isActive: newActive } : x))
      );
      await loadData();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to toggle schedule";
      toast({ title: "Error", description: message, variant: "destructive" });
    }
  };

  if (loading) {
    return (
      <div className="flex-1 min-h-0 flex items-center justify-center p-6 lg:p-8">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-6 p-6 lg:p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Schedules</h1>
          <p className="text-muted-foreground text-sm mt-1">Automate when your agents run</p>
        </div>
        <Button className="gradient-primary text-primary-foreground" onClick={openCreate}>
          <Plus className="h-4 w-4 mr-2" /> Create schedule
        </Button>
      </div>

      {schedules.length === 0 ? (
        <EmptyState
          icon={Calendar}
          title="No schedules yet"
          description="Create a schedule to automate your agents."
          actionLabel="Create schedule"
          onAction={openCreate}
        />
      ) : (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          {schedules.map((s) => {
            const active = getIsActive(s);
            const agentName = getAgentName(s);
            const extractedInput = getExtractedInput(s);
            const triggerType = getTriggerType(s);
            const nextRunRelative = formatRelative(getNextRunAt(s));
            const lastRunRelative = formatRelative(getLastRunAt(s));

            return (
              <motion.div
                key={s.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-xl border border-border bg-card shadow-card hover:border-primary/30 transition-colors overflow-hidden"
              >
                <div className="p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1 min-w-0 pr-3">
                      <h3 className="text-sm font-semibold text-foreground break-words">{s.label}</h3>
                      <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                        <Bot className="h-3.5 w-3.5" />
                        <span className="font-medium">{agentName}</span>
                      </div>
                    </div>
                    <Switch
                      checked={active}
                      onCheckedChange={(checked) => handleToggle(s, checked)}
                    />
                  </div>

                  <div className="space-y-2 mb-4">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Clock className="h-3.5 w-3.5" />
                      <span>Next: <span className="text-foreground font-medium">{nextRunRelative}</span></span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Clock className="h-3.5 w-3.5" />
                      <span>Last: <span className="text-foreground font-medium">{lastRunRelative}</span></span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Zap className="h-3.5 w-3.5" />
                      <code className="font-mono bg-muted px-1.5 py-0.5 rounded text-[11px]">
                        {s.cron_expression || s.cronExpression || "Webhook"}
                      </code>
                    </div>
                  </div>

                  {extractedInput && (
                    <div className="text-xs text-muted-foreground mb-3">
                      <span className="uppercase tracking-wider text-[10px] mr-2">
                        Agent input:
                      </span>
                      <span className="italic text-foreground">"{extractedInput}"</span>
                    </div>
                  )}

                  {triggerType === "webhook" && (
                    <div className="flex items-center gap-2 mb-3">
                      <Webhook className="h-3.5 w-3.5 text-primary" />
                      <code className="text-[11px] font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded flex-1 truncate">
                        /api/v1/webhooks/{s.id}
                      </code>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-muted-foreground"
                        onClick={() => {
                          navigator.clipboard.writeText(`/api/v1/webhooks/${s.id}`);
                          toast({ title: "Copied!" });
                        }}
                      >
                        <Copy className="h-3 w-3" />
                      </Button>
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-3 border-t border-border">
                    <span
                      className={`inline-flex items-center rounded-md px-2 py-1 text-[11px] font-medium ${
                        active
                          ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
                          : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                      }`}
                    >
                      {active ? "Active" : "Paused"}
                    </span>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-foreground"
                        onClick={() => openEdit(s)}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        onClick={() => setDeleteId(s.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </motion.div>
      )}

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle className="text-foreground">
              {editing.id ? "Edit Schedule" : "Create Schedule"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Description (plain language)</Label>
              <Textarea
                value={editing.label}
                onChange={(e) =>
                  setEditing((prev) => ({ ...prev, label: e.target.value }))
                }
                className="bg-secondary border-border min-h-[100px] text-sm"
                placeholder={
                  "Describe WHEN and WHAT. Examples:\n" +
                  "  Every morning at 9, summarize my unread emails\n" +
                  '  Every 5 minutes, say "ping" in the output\n' +
                  "  Every Monday at 8am, generate a weekly report"
                }
              />
              <p className="text-[11px] text-muted-foreground">
                Include both the timing (every minute, daily at 9am...) and the task the agent
                should perform each time it runs.
              </p>
            </div>
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Agent</Label>
              <Select
                value={editing.agent_id}
                onValueChange={(v) => setEditing((prev) => ({ ...prev, agent_id: v }))}
              >
                <SelectTrigger className="bg-secondary border-border">
                  <SelectValue placeholder="Select agent" />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  {agents.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Trigger type</Label>
              <Select
                value={editing.trigger_type}
                onValueChange={(v) =>
                  setEditing((prev) => ({ ...prev, trigger_type: v as TriggerType }))
                }
              >
                <SelectTrigger className="bg-secondary border-border">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  <SelectItem value="cron">Recurring (cron)</SelectItem>
                  <SelectItem value="webhook">Webhook</SelectItem>
                  <SelectItem value="event">Event</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {editing.trigger_type === "webhook" && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-muted">
                <Webhook className="h-4 w-4 text-primary" />
                <span className="text-xs text-muted-foreground">
                  Webhook URL will be generated after creation
                </span>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setFormOpen(false)}
              className="border-border text-foreground"
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving}
              className="gradient-primary text-primary-foreground"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteId} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent className="bg-card border-border">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-foreground">Delete schedule?</AlertDialogTitle>
            <AlertDialogDescription className="text-muted-foreground">
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-border text-foreground">
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
