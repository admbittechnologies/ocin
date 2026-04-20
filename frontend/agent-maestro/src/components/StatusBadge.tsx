import { cn } from "@/lib/utils";
import { Loader2, Clock } from "lucide-react";

type RunStatus = "pending" | "running" | "success" | "failed" | "awaiting_approval";
type ApprovalStatus = "pending" | "approved" | "rejected" | "expired";
type Status = RunStatus | ApprovalStatus;

const statusConfig: Record<Status, { label: string; className: string; icon?: React.ReactNode }> = {
  // Run statuses
  pending: { label: "Pending", className: "bg-muted text-muted-foreground" },
  running: { label: "Running", className: "bg-info/10 text-info", icon: <Loader2 className="h-3 w-3 animate-spin" /> },
  success: { label: "Success", className: "bg-success/10 text-success" },
  failed: { label: "Failed", className: "bg-destructive/10 text-destructive" },
  awaiting_approval: { label: "Awaiting Approval", className: "bg-warning/10 text-warning", icon: <Clock className="h-3 w-3" /> },

  // Approval statuses
  approved: { label: "Approved", className: "bg-success/10 text-success" },
  rejected: { label: "Rejected", className: "bg-destructive/10 text-destructive" },
  expired: { label: "Expired", className: "bg-muted text-muted-foreground" },

  // Fallback for unknown statuses
  unknown: { label: "Unknown", className: "bg-muted text-muted-foreground" },
};

export function StatusBadge({ status }: { status: Status }) {
  const config = statusConfig[status] ?? statusConfig.unknown;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium", config.className)}>
      {config.icon}
      {config.label}
    </span>
  );
}
