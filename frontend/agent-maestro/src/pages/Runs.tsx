import { useState, useEffect, useRef, useMemo } from "react";
import { motion } from "framer-motion";
import { Play, ChevronRight, ArrowLeft, Loader2, Filter, Calendar, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { apiGetRuns, apiGetRun, apiStreamRun, apiGetAgents, type Run as ApiRun, type Agent as ApiAgent } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { useLocation } from "react-router-dom";

type RunStatus = "pending" | "running" | "success" | "failed" | "awaiting_approval";
type TriggerFilter = "all" | "scheduled" | "manual";

interface ToolCall {
  name: string;
  input: string;
  output: string;
  duration: string;
}

// Shape used internally by this page. Mapped from the backend ApiRun.
interface Run {
  id: string;
  agent_id: string;
  trigger: "Schedule" | "Manual";
  schedule_id?: string | null;
  schedule_label?: string | null;  // API returns schedule_label, not schedule_name
  status: RunStatus;
  started_at: string | null;   // ISO string or null
  finished_at: string | null;  // ISO string or null
  duration_ms: number | null;
  cost_usd: number | null;
  input?: string;
  output?: string;
  error?: string;
  tokens?: number;
  toolCalls?: ToolCall[];
  is_archived?: boolean;  // API returns is_archived, not is_archived
}

export default function Runs() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [streamView, setStreamView] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [agents, setAgents] = useState<ApiAgent[]>([]);
  const [triggerFilter, setTriggerFilter] = useState<TriggerFilter>("all");
  const { toast } = useToast();
  const cleanupRef = useRef<(() => void) | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const location = useLocation();

  // Check if there's a selectedRunId passed from Dashboard navigation
  useEffect(() => {
    if (location.state?.selectedRunId && runs.length > 0) {
      const run = runs.find(r => r.id === location.state.selectedRunId);
      if (run) {
        setSelectedRun(run);
      }
    }
  }, [location.state, runs]);

  useEffect(() => {
    loadRuns();
    return () => {
      if (cleanupRef.current) {
        cleanupRef.current();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch agents once for the id → name lookup
  useEffect(() => {
    apiGetAgents()
      .then((data) => setAgents(data ?? []))
      .catch((err) => {
        console.error("Failed to fetch agents:", err);
        setAgents([]);
      });
  }, []);

  // Build agent name lookup map keyed by agent id
  const agentNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const agent of agents) {
      map.set(agent.id, agent.name);
    }
    return map;
  }, [agents]);

  // Filter runs based on trigger type
  const filteredRuns = useMemo(() => {
    if (triggerFilter === "all") return runs;
    if (triggerFilter === "scheduled") return runs.filter(r => r.schedule_id !== null);
    if (triggerFilter === "manual") return runs.filter(r => r.schedule_id === null);
    return runs;
  }, [runs, triggerFilter]);

  const loadRuns = async () => {
    try {
      setLoading(true);
      const data = await apiGetRuns();
      const mapped: Run[] = (data ?? []).map((r: ApiRun) => {
        // duration ms: prefer explicit started→finished window, otherwise null
        const started = r.started_at ? new Date(r.started_at).getTime() : null;
        const finished = r.finished_at ? new Date(r.finished_at).getTime() : null;
        const durationMs = started && finished ? Math.max(0, finished - started) : null;

        return {
          id: r.id,
          agent_id: r.agent_id,
          trigger: r.schedule_id ? "Schedule" : "Manual",
          schedule_id: r.schedule_id ?? null,
          schedule_label: r.schedule_label ?? null,
          status: r.status as RunStatus,
          started_at: r.started_at ?? null,
          finished_at: r.finished_at ?? null,
          duration_ms: durationMs,
          cost_usd: r.cost_usd ?? null,
          input: r.input,
          output: r.output ?? undefined,
          error: r.error ?? undefined,
          tokens: r.tokens_used ?? undefined,
          toolCalls: Array.isArray(r.tool_calls)
            ? r.tool_calls.map((tc: any) => ({
                name: tc.tool ?? tc.name ?? "tool",
                input: typeof tc.input === "string" ? tc.input : JSON.stringify(tc.input ?? {}),
                output: typeof tc.output === "string" ? tc.output : JSON.stringify(tc.output ?? {}),
                duration: tc.duration_ms ? `${tc.duration_ms}ms` : "",
              }))
            : [],
          is_archived: r.is_archived ?? false,
        };
      });
      setRuns(mapped);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load runs";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  /** Format an ISO date as a short relative time like "2 min ago". */
  const formatRelative = (iso: string | null): string => {
    if (!iso) return "—";
    const date = new Date(iso);
    if (isNaN(date.getTime())) return "—";
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    if (diffMs < 0) return "Just now";
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  /** Prefer started_at, fall back to finished_at for display. */
  const displayTimestamp = (run: Run): string => {
    return formatRelative(run.started_at ?? run.finished_at);
  };

  const formatDuration = (ms: number | null): string => {
    if (ms == null) return "—";
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
    const mins = Math.floor(ms / 60_000);
    const secs = Math.floor((ms % 60_000) / 1000);
    return `${mins}m ${secs}s`;
  };

  const formatCost = (cost: number | null): string => {
    if (cost == null) return "—";
    if (cost === 0) return "$0.00";
    if (cost < 0.01) return "<$0.01";
    return `$${cost.toFixed(2)}`;
  };

  const handleViewRun = async (run: Run) => {
    setSelectedRun(run);

    if (run.status === "running") {
      setStreamView(true);
      setStreamText("");
      setStreaming(true);

      const cleanup = apiStreamRun(
        run.id,
        (data) => {
          if (typeof data === "string") {
            setStreamText((prev) => prev + data);
          } else if (typeof data === "object" && data !== null) {
            const dataObj = data as Record<string, unknown>;
            if (dataObj.content) {
              setStreamText((prev) => prev + (dataObj.content as string));
            }
          }
        },
        () => {
          setStreaming(false);
          loadRuns();
        }
      );
      cleanupRef.current = cleanup;
    } else {
      setStreamView(false);

      try {
        const detail = await apiGetRun(run.id);
        if (detail) {
          setSelectedRun({
            ...run,
            input: detail.input,
            output: detail.output ?? undefined,
            error: detail.error ?? undefined,
            tokens: (detail as any).tokens_used ?? run.tokens,
            toolCalls: Array.isArray((detail as any).tool_calls)
              ? (detail as any).tool_calls.map((tc: any) => ({
                  name: tc.tool ?? tc.name ?? "tool",
                  input: typeof tc.input === "string" ? tc.input : JSON.stringify(tc.input ?? {}),
                  output: typeof tc.output === "string" ? tc.output : JSON.stringify(tc.output ?? {}),
                  duration: tc.duration_ms ? `${tc.duration_ms}ms` : "",
                }))
              : [],
          });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load run details";
        toast({ title: "Error", description: message, variant: "destructive" });
      }
    }
  };

  const handleBack = () => {
    setSelectedRun(null);
    setStreamView(false);
    setStreamText("");
    setStreaming(false);
    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }
    if (pollingRef.current) {
      clearTimeout(pollingRef.current);
      pollingRef.current = null;
    }
  };

  // Poll for updates when viewing a run that's still running
  useEffect(() => {
    if (!selectedRun || (selectedRun.status !== "running" && selectedRun.status !== "pending")) {
      return;
    }

    const pollInterval = setInterval(async () => {
      try {
        const updatedRun = await apiGetRun(selectedRun.id);
        if (updatedRun) {
          setSelectedRun(prev => ({
            ...prev,
            status: updatedRun.status as RunStatus,
            input: updatedRun.input ?? prev.input,
            output: updatedRun.output ?? prev.output,
            error: updatedRun.error ?? prev.error,
            tokens: updatedRun.tokens_used ?? prev.tokens,
            toolCalls: Array.isArray((updatedRun as any).tool_calls)
              ? (updatedRun as any).tool_calls.map((tc: any) => ({
                  name: tc.tool ?? tc.name ?? "tool",
                  input: typeof tc.input === "string" ? tc.input : JSON.stringify(tc.input ?? {}),
                  output: typeof tc.output === "string" ? tc.output : JSON.stringify(tc.output ?? {}),
                  duration: tc.duration_ms ? `${tc.duration_ms}ms` : "",
                }))
              : [],
            is_archived: updatedRun.is_archived ?? prev.is_archived,
          }));

          // Stop polling if run completes or fails
          if (updatedRun.status === "success" || updatedRun.status === "failed") {
            clearInterval(pollInterval);
            pollingRef.current = null;
          }
        }
      } catch (error) {
        console.error("Polling error:", error);
      }
    }, 2000); // Poll every 2 seconds

    pollingRef.current = pollInterval;

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [selectedRun?.id, selectedRun?.status]);

  if (loading) {
    return (
      <div className="flex-1 min-h-0 flex items-center justify-center p-6 lg:p-8">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (selectedRun) {
    const agentName = agentNameById.get(selectedRun.agent_id) ?? "Unknown agent";

    // Format run duration in seconds
    const runDurationSeconds = selectedRun.started_at && selectedRun.finished_at
      ? Math.floor((new Date(selectedRun.finished_at).getTime() - new Date(selectedRun.started_at).getTime()) / 1000)
      : null;

    return (
      <div className="flex-1 min-h-0 flex flex-col gap-6 p-6 lg:p-8 overflow-y-auto">
        <Button variant="ghost" onClick={handleBack} className="text-muted-foreground hover:text-foreground self-start">
          <ArrowLeft className="h-4 w-4 mr-2" /> Back to runs
        </Button>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">{agentName}</h1>
            <p className="text-muted-foreground text-sm mt-1">
              {selectedRun.schedule_label ? (
                <span className="flex items-center gap-2">
                  <Calendar className="h-3.5 w-3.5 text-primary" />
                  <span>Triggered by schedule: {selectedRun.schedule_label}</span>
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <Zap className="h-3.5 w-3.5" />
                  <span>Manual trigger</span>
                </span>
              )}
              <span className="mx-2">·</span>
              {displayTimestamp(selectedRun)}
            </p>
          </div>
          <StatusBadge status={selectedRun.status} />
        </div>

        {selectedRun.status === "running" || selectedRun.status === "pending" ? (
          <div className="rounded-xl border border-border bg-[hsl(228,12%,6%)] p-5 font-mono text-sm text-success min-h-[300px]">
            <div className="flex items-center gap-2 text-muted-foreground mb-3 text-xs">
              <Loader2 className="h-3 w-3 animate-spin mr-1" />
              Agent is working...
            </div>
            <pre className="whitespace-pre-wrap">
              {selectedRun.input && (
                <div className="mb-4">
                  <h4 className="text-sm font-semibold text-foreground mb-2">Input:</h4>
                  <p className="text-muted-foreground text-sm">{selectedRun.input}</p>
                </div>
              )}
              {selectedRun.output ? (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-2">Output:</h4>
                  <p className="text-success text-sm whitespace-pre-wrap">{selectedRun.output}</p>
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">Waiting for output...</p>
              )}
            </pre>
          </div>
        ) : selectedRun.is_archived ? (
          <div className="rounded-xl border border-border bg-muted/30 p-5">
            <h3 className="text-sm font-semibold text-foreground mb-2">Output Archived</h3>
            <p className="text-muted-foreground text-sm">
              This run's output has been archived (older than 30 days). Metadata is still available below.
            </p>
          </div>
        ) : selectedRun.status === "success" ? (
          <div className="space-y-4">
            {selectedRun.output && (
              <div className="rounded-xl border border-border bg-card p-5">
                <h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Output</h3>
                <p className="text-foreground text-sm whitespace-pre-wrap">
                  {selectedRun.output}
                </p>
              </div>
            )}
            {selectedRun.toolCalls && selectedRun.toolCalls.length > 0 && (
              <div className="rounded-xl border border-border bg-card p-5">
                <h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-3">Tool Calls</h3>
                <Accordion type="multiple" className="space-y-2">
                  {selectedRun.toolCalls.map((tc, i) => (
                    <AccordionItem key={i} value={`tc-${i}`} className="border border-border rounded-lg px-4">
                      <AccordionTrigger className="text-sm text-foreground py-3 hover:no-underline">
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-primary">{tc.name}</span>
                          <span className="text-xs text-muted-foreground">{tc.duration}</span>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className="pb-3 space-y-2">
                        <div>
                          <span className="text-[10px] text-muted-foreground uppercase">Input</span>
                          <pre className="text-xs font-mono text-foreground bg-muted rounded p-2 mt-1 overflow-x-auto">
                            {tc.input?.length > 2000 ? `${tc.input.substring(0, 2000)}...` : tc.input}
                          </pre>
                          <button
                            className="text-xs text-primary hover:underline mt-1"
                            onClick={() => alert(tc.input)}
                          >
                            Show more
                          </button>
                        </div>
                        <div>
                          <span className="text-[10px] text-muted-foreground uppercase">Output</span>
                          <pre className="text-xs font-mono text-foreground bg-muted rounded p-2 mt-1 overflow-x-auto">
                            {tc.output?.length > 2000 ? `${tc.output.substring(0, 2000)}...` : tc.output}
                          </pre>
                          {tc.output?.length > 2000 && (
                            <button
                              className="text-xs text-primary hover:underline mt-1"
                              onClick={() => alert(tc.output)}
                            >
                              Show more
                            </button>
                          )}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  ))}
                </Accordion>
              </div>
            )}
            <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
              {selectedRun.tokens != null && (
                <span>
                  Tokens: <span className="text-foreground font-mono">{selectedRun.tokens.toLocaleString()}</span>
                </span>
              )}
              <span>
                Cost: <span className="text-foreground font-mono">{formatCost(selectedRun.cost_usd)}</span>
              </span>
              <span>
                Duration: <span className="text-foreground font-mono">{runDurationSeconds ? `${runDurationSeconds}s` : "—"}</span>
              </span>
              <span>
                Agent: <span className="text-foreground font-mono">{agentName}</span>
              </span>
            </div>
          </div>
        ) : selectedRun.status === "failed" ? (
          <div className="space-y-4">
            {selectedRun.input && (
              <div className="rounded-xl border border-border bg-card p-5">
                <h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Input</h3>
                <p className="text-foreground text-sm whitespace-pre-wrap">{selectedRun.input}</p>
              </div>
            )}
            {selectedRun.error && (
              <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-5">
                <h3 className="text-xs text-destructive uppercase tracking-wider mb-2">Error</h3>
                <p className="text-destructive text-sm font-mono">{selectedRun.error}</p>
              </div>
            )}
            <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
              {selectedRun.tokens != null && (
                <span>
                  Tokens: <span className="text-foreground font-mono">{selectedRun.tokens.toLocaleString()}</span>
                </span>
              )}
              <span>
                Cost: <span className="text-foreground font-mono">{formatCost(selectedRun.cost_usd)}</span>
              </span>
              <span>
                Duration: <span className="text-foreground font-mono">{runDurationSeconds ? `${runDurationSeconds}s` : "—"}</span>
              </span>
              <span>
                Agent: <span className="text-foreground font-mono">{agentName}</span>
              </span>
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-6 p-6 lg:p-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Runs</h1>
          <p className="text-muted-foreground text-sm mt-1">View execution history for all agents</p>
        </div>
        {runs.length > 0 && (
          <div className="flex items-center gap-2 bg-card border border-border rounded-lg p-1">
            <Button
              variant={triggerFilter === "all" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setTriggerFilter("all")}
              className="text-xs"
            >
              All ({runs.length})
            </Button>
            <Button
              variant={triggerFilter === "scheduled" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setTriggerFilter("scheduled")}
              className="text-xs"
            >
              <Calendar className="h-3 w-3 mr-1" />
              Scheduled ({runs.filter(r => r.schedule_id !== null).length})
            </Button>
            <Button
              variant={triggerFilter === "manual" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setTriggerFilter("manual")}
              className="text-xs"
            >
              <Zap className="h-3 w-3 mr-1" />
              Manual ({runs.filter(r => r.schedule_id === null).length})
            </Button>
          </div>
        )}
      </div>

      {runs.length === 0 ? (
        <EmptyState icon={Play} title="No runs yet" description="Trigger your first agent run to see results here." />
      ) : (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex-1 min-h-0 rounded-xl border border-border bg-card shadow-card overflow-y-auto"
        >
          <table className="w-full">
            <thead className="sticky top-0 bg-card z-10">
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="text-left px-5 py-3 font-medium">Agent</th>
                <th className="text-left px-5 py-3 font-medium">Trigger</th>
                <th className="text-left px-5 py-3 font-medium">Status</th>
                <th className="text-left px-5 py-3 font-medium">Started</th>
                <th className="text-left px-5 py-3 font-medium">Duration</th>
                <th className="text-left px-5 py-3 font-medium">Cost</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredRuns.map((run) => (
                <tr
                  key={run.id}
                  className="hover:bg-accent/30 transition-colors cursor-pointer"
                  onClick={() => handleViewRun(run)}
                >
                  <td className="px-5 py-3 text-sm text-foreground">
                    {agentNameById.get(run.agent_id) ?? "—"}
                  </td>
                  <td className="px-5 py-3">
                    {run.schedule_label ? (
                      <div className="flex items-center gap-1.5 text-sm text-foreground">
                        <Calendar className="h-3.5 w-3.5 text-primary" />
                        <span>Triggered by schedule: {run.schedule_label}</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                        <Zap className="h-3.5 w-3.5" />
                        <span>Manual trigger</span>
                      </div>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <StatusBadge status={run.status} />
                  </td>
                  <td className="px-5 py-3 text-sm text-muted-foreground">{displayTimestamp(run)}</td>
                  <td className="px-5 py-3 text-sm text-muted-foreground font-mono">
                    {formatDuration(run.duration_ms)}
                  </td>
                  <td className="px-5 py-3 text-sm text-muted-foreground font-mono">{formatCost(run.cost_usd)}</td>
                  <td className="px-5 py-3">
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>
      )}
    </div>
  );
}
