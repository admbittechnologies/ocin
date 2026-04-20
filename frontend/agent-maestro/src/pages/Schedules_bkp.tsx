import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Textarea } from "@/components/ui/textarea";
import { Calendar, Plus, Pencil, Trash2, Copy, Webhook, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { useToast } from "@/hooks/use-toast";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { apiGetSchedules, apiCreateSchedule, apiUpdateSchedule, apiDeleteSchedule, apiToggleSchedule, apiGetAgents, type Agent as ApiAgent } from "@/lib/api";

interface Schedule {
  id: string;
  label: string;
  agentId: string;
  agentName: string;
  triggerType: "recurring" | "webhook" | "event";
  nextRun?: string;
  lastRun?: string;
  active: boolean;
  webhookUrl?: string;
}

export default function Schedules() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [agents, setAgents] = useState<{ id: string; name: string }[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [editing, setEditing] = useState<Partial<Schedule> & { label: string; agentName: string; triggerType: Schedule["triggerType"] }>({ label: "", agentName: "", triggerType: "recurring" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [schedulesData, agentsData] = await Promise.all([
        apiGetSchedules(),
        apiGetAgents(),
      ]);

      const mappedSchedules: Schedule[] = schedulesData.map(s => ({
        id: s.id,
        label: s.label,
        agentId: s.agentId || "",
        agentName: s.agentName || "",
        triggerType: (s.triggerType as Schedule["triggerType"]) || "recurring",
        nextRun: formatTime(s.nextRun),
        lastRun: formatTime(s.lastRun),
        active: s.active,
        webhookUrl: s.webhookUrl,
      }));

      const mappedAgents = agentsData.map(a => ({ id: a.id, name: a.name }));

      setSchedules(mappedSchedules);
      setAgents(mappedAgents);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load schedules";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (dateStr?: string): string => {
    if (!dateStr) return "—";
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `In ${diffMins} min`;
    if (diffHours < 24) return `In ${diffHours}h`;
    if (diffDays < 7) return `In ${diffDays}d`;
    return date.toLocaleDateString();
  };

  const handleSave = async () => {
    if (!editing.label.trim()) {
      toast({ title: "Error", description: "Schedule label is required", variant: "destructive" });
      return;
    }
    if (!editing.agentId) {
      toast({ title: "Error", description: "Please select an agent", variant: "destructive" });
      return;
    }

    try {
      setSaving(true);
      const payload = {
        label: editing.label,
        agent_id: editing.agentId,
        trigger_type: editing.triggerType,
      };

      if (editing.id) {
        await apiUpdateSchedule(editing.id, payload);
        toast({ title: "Schedule updated" });
      } else {
        await apiCreateSchedule(payload);
        toast({ title: "Schedule created" });
      }
      setFormOpen(false);
      setEditing({ label: "", agentName: "", triggerType: "recurring" });
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

  const handleToggle = async (id: string, active: boolean) => {
    try {
      await apiToggleSchedule(id, active);
      setSchedules(prev => prev.map(s => s.id === id ? { ...s, active } : s));
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
        <Button className="gradient-primary text-primary-foreground" onClick={() => { setEditing({ label: "", agentId: "", agentName: "", triggerType: "recurring" }); setFormOpen(true); }}>
          <Plus className="h-4 w-4 mr-2" /> Create schedule
        </Button>
      </div>

      {schedules.length === 0 ? (
        <EmptyState icon={Calendar} title="No schedules yet" description="Create a schedule to automate your agents." actionLabel="Create schedule" onAction={() => setFormOpen(true)} />
      ) : (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="rounded-xl border border-border bg-card shadow-card overflow-hidden">
          <div className="divide-y divide-border">
            {schedules.map(s => (
              <div key={s.id} className="flex items-center justify-between px-5 py-4 hover:bg-accent/30 transition-colors">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-foreground font-medium truncate">{s.label}</p>
                  <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                    <span>{s.agentName}</span>
                    <span>·</span>
                    <span>Next: {s.nextRun}</span>
                    <span>·</span>
                    <span>Last: {s.lastRun}</span>
                  </div>
                  {s.webhookUrl && (
                    <div className="flex items-center gap-2 mt-2">
                      <code className="text-[11px] font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded truncate max-w-[300px]">{s.webhookUrl}</code>
                      <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground" onClick={() => { navigator.clipboard.writeText(s.webhookUrl!); toast({ title: "Copied!" }); }}>
                        <Copy className="h-3 w-3" />
                      </Button>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-3 ml-4">
                  <StatusBadge status={s.active ? "success" : "pending"} />
                  <Switch checked={s.active} onCheckedChange={checked => handleToggle(s.id, checked)} />
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" onClick={() => { setEditing(s); setFormOpen(true); }}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={() => setDeleteId(s.id)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle className="text-foreground">{editing.id ? "Edit Schedule" : "Create Schedule"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Description (plain language)</Label>
              <Textarea value={editing.label} onChange={e => setEditing(prev => ({ ...prev, label: e.target.value }))} className="bg-secondary border-border min-h-[100px] text-sm" placeholder="Check my emails every morning at 9&#10;&#10;You can write detailed instructions here..." />
            </div>
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Agent</Label>
              <Select value={editing.agentId} onValueChange={v => setEditing(prev => ({ ...prev, agentId: v, agentName: agents.find(a => a.id === v)?.name || "" }))}>
                <SelectTrigger className="bg-secondary border-border"><SelectValue placeholder="Select agent" /></SelectTrigger>
                <SelectContent className="bg-card border-border">
                  {agents.map(a => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-foreground text-sm">Trigger type</Label>
              <Select value={editing.triggerType} onValueChange={v => setEditing(prev => ({ ...prev, triggerType: v as Schedule["triggerType"] }))}>
                <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-card border-border">
                  <SelectItem value="recurring">Recurring</SelectItem>
                  <SelectItem value="webhook">Webhook</SelectItem>
                  <SelectItem value="event">Event</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {editing.triggerType === "webhook" && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-muted">
                <Webhook className="h-4 w-4 text-primary" />
                <span className="text-xs text-muted-foreground">Webhook URL will be generated after creation</span>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)} className="border-border text-foreground">Cancel</Button>
            <Button onClick={handleSave} disabled={saving} className="gradient-primary text-primary-foreground">
              {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteId} onOpenChange={open => !open && setDeleteId(null)}>
        <AlertDialogContent className="bg-card border-border">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-foreground">Delete schedule?</AlertDialogTitle>
            <AlertDialogDescription className="text-muted-foreground">This action cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-border text-foreground">Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
