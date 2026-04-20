import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { CheckCircle2, ShieldCheck, Clock, X, Loader2, ChevronRight, Play, Calendar } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { apiGetApprovals, apiGetApproval, apiApproveApproval, apiRejectApproval, apiGetPendingApprovalsCount, type Approval } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { useNavigate } from "react-router-dom";
import { useAgentAvatar } from "@/lib/agentAvatar";

const container = { hidden: {}, show: { transition: { staggerChildren: 0.05 } } };
const item = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } };

// Subcomponent for approval cards - uses useAgentAvatar hook for proper caching
function ApprovalCard({ approval, onApprove, onReject, filter }: {
  approval: Approval;
  onApprove: () => void;
  onReject: () => void;
}) {
  const avatarSrc = useAgentAvatar(approval.agent_id);

  return (
    <motion.div
      variants={item}
      className="rounded-xl border border-border bg-card p-5 shadow-card hover:border-primary/30 transition-colors"
    >
      <div className="flex items-start gap-4">
        <img
          src={avatarSrc}
          alt={approval.agent_name}
          className="h-12 w-12 rounded-full object-cover border-2 border-border"
        />
        <div className="flex-1 min-w-0">
          {/* Header: title, agent info, status */}
          <div className="flex items-start justify-between gap-2 mb-3">
            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-semibold text-foreground">{approval.title}</h3>
              <p className="text-sm text-muted-foreground">
                {approval.agent_name} · {approval.kind}
              </p>
            </div>
            <StatusBadge status={approval.status} />
          </div>

          {/* Approve/Reject buttons for pending approvals */}
          {filter === "pending" && (
            <div className="flex gap-2 pt-2 border-t border-border mt-3">
              <Button
                variant="outline"
                size="sm"
                onClick={onApprove}
                className="border-border text-foreground hover:bg-primary hover:text-primary-foreground flex-1"
              >
                <CheckCircle2 className="h-4 w-4 mr-2" />
                Approve
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={onReject}
                className="border-destructive text-destructive hover:bg-destructive hover:text-destructive-foreground flex-1"
              >
                <X className="h-4 w-4 mr-2" />
                Reject
              </Button>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default function Approvals() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [filter, setFilter] = useState<"pending" | "approved" | "rejected">("pending");
  const [selectedApproval, setSelectedApproval] = useState<Approval | null>(null);
  const [approveDialog, setApproveDialog] = useState(false);
  const [rejectDialog, setRejectDialog] = useState(false);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const { toast } = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    loadApprovals();
  }, [filter]);

  const loadApprovals = async () => {
    try {
      setLoading(true);
      const data = await apiGetApprovals(filter);
      setApprovals(data);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load approvals";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (dateStr: string): string => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  const handleApprove = async () => {
    if (!selectedApproval) return;
    try {
      setSubmitting(true);
      const updated = await apiApproveApproval(selectedApproval.id, note);
      toast({ title: "Approval approved" });
      setApproveDialog(false);
      setNote("");
      await loadApprovals();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to approve";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!selectedApproval) return;
    try {
      setSubmitting(true);
      const updated = await apiRejectApproval(selectedApproval.id, note);
      toast({ title: "Approval rejected" });
      setRejectDialog(false);
      setNote("");
      await loadApprovals();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to reject";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setSubmitting(false);
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
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Approvals</h1>
        <p className="text-muted-foreground text-sm mt-1">Review and approve pending actions from your agents</p>
      </div>

      <div className="flex gap-2">
        {["pending", "approved", "rejected"].map(status => (
          <Button
            key={status}
            variant={filter === status ? "default" : "ghost"}
            size="sm"
            onClick={() => setFilter(status as "pending" | "approved" | "rejected")}
            className={`capitalize ${filter === status ? "bg-primary text-primary-foreground" : "hover:bg-accent"}`}
          >
            {status}
          </Button>
        ))}
      </div>

      {approvals.length === 0 ? (
        <EmptyState
          icon={filter === "pending" ? CheckCircle2 : ShieldCheck}
          title={`No ${filter} approvals`}
          description={
            filter === "pending"
              ? "Your agents will request approval here when they need your confirmation to proceed."
              : "No approvals match this filter."
          }
        />
      ) : (
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="space-y-4"
        >
          {approvals.map((approval) => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              filter={filter}
              onApprove={() => {
                setSelectedApproval(approval);
                setApproveDialog(true);
              }}
              onReject={() => {
                setSelectedApproval(approval);
                setRejectDialog(true);
              }}
            />
          ))}
        </motion.div>
      )}

      <Dialog open={!!selectedApproval && approveDialog} onOpenChange={setApproveDialog}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle className="text-foreground">Approve this action?</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Agent "{selectedApproval?.agent_name}" wants to:
            </p>
            <p className="text-sm font-medium text-foreground mt-2">{selectedApproval?.title}</p>
            <div className="text-xs text-muted-foreground font-mono bg-muted rounded p-3 mt-3">
              <pre className="whitespace-pre-wrap break-all">{JSON.stringify(selectedApproval?.payload, null, 2)}</pre>
            </div>
            <label className="text-xs text-muted-foreground">Add a note (optional)</label>
            <Textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="Your reasoning or context..."
              className="bg-secondary border-border text-sm resize-none min-h-[80px]"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApproveDialog(false)} className="border-border text-foreground">
              Cancel
            </Button>
            <Button onClick={handleApprove} disabled={submitting} className="gradient-primary text-primary-foreground">
              {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Approve
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!selectedApproval && rejectDialog} onOpenChange={setRejectDialog}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle className="text-foreground">Reject this action?</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Agent "{selectedApproval?.agent_name}" wants to:
            </p>
            <p className="text-sm font-medium text-foreground mt-2">{selectedApproval?.title}</p>
            <div className="text-xs text-muted-foreground font-mono bg-muted rounded p-3 mt-3">
              <pre className="whitespace-pre-wrap break-all">{JSON.stringify(selectedApproval?.payload, null, 2)}</pre>
            </div>
            <label className="text-xs text-muted-foreground">Add a note (optional)</label>
            <Textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="Your reasoning or context..."
              className="bg-secondary border-border text-sm resize-none min-h-[80px]"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectDialog(false)} className="border-border text-foreground">
              Cancel
            </Button>
            <Button onClick={handleReject} disabled={submitting} className="bg-destructive text-destructive-foreground">
              {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
