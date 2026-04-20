import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { motion } from "framer-motion";
import { Play, ChevronRight, ArrowLeft, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { apiGetRuns, apiGetRun, apiStreamRun, apiGetAgents, type Run as ApiRun, type Agent as ApiAgent } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

type RunStatus = "pending" | "running" | "success" | "failed" | "awaiting_approval";

interface ToolCall {
  name: string;
  input: string;
  output: string;
  duration: string;
}

interface Run {
  id: string;
  agent: string;
  trigger: string;
  status: RunStatus;
  started_at: string;
  duration: string;
  cost: string;
  input?: string;
  output?: string;
  error?: string;
  tokens?: number;
  toolCalls?: ToolCall[];
}

const container = { hidden: {}, show: { transition: { staggerChildren: 0.05 } } };
const item = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } };

const TRIGGER_LABELS: Record<string, string> = {
  "schedule": "Schedule",
  "manual": "Manual",
  "event": "Event",
  "webhook": "Webhook",
};

export default function Runs() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [streamView, setStreamView] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [agents, setAgents] = useState<Agent[]>([]);
  const { toast } = useToast();
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    loadRuns();
    return () => {
      if (cleanupRef.current) {
        cleanupRef.current();
      }
    };
  }, []);

  // Fetch agents for lookup
  useEffect(() => {
    const fetchAgents = async () => {
      try {
        const data = await apiGetAgents();
        const mappedAgents: Agent[] = data.map((a: ApiAgent) => ({
          id: a.id,
          name: a.name,
          avatar_color: a.avatar_color || "#6366f1",
        }));
        setAgents(mappedAgents);
      } catch (err) {
        console.error("Failed to fetch agents:", err);
        setAgents([]);
      }
    };
    fetchAgents();
  }, []);

  // Build agent name lookup map
  const agentNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const agent of agents) {
      map.set(agent.id, agent.name);
    }
    return map;
  }, [agents]);

  const loadRuns = async () => {
    try {
      setLoading(true);
      const data = await apiGetRuns();
      const mappedRuns: Run[] = data.map((r: ApiRun) => ({
        id: r.id,
        agent: r.agent,
        trigger: r.schedule_id ? "Schedule" : "Manual",
        status: r.status as RunStatus,
        started_at: r.started_at ? formatTime(r.started_at) : "—",
        duration: r.duration,
        cost: r.cost,
        input: r.input,
        output: r.output,
        error: r.error,
        tokens: r.tokens,
        toolCalls: r.toolCalls?.map(tc => ({
          name: tc.name,
          input: typeof tc.input === 'string' ? tc.input : JSON.stringify(tc.input),
          output: typeof tc.output === 'string' ? tc.output : JSON.stringify(tc.output),
          duration: tc.duration,
        })) || [],
      }));
      setRuns(mappedRuns);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load runs";
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

  const handleViewRun = async (run: Run) => {
    setSelectedRun(run);

    if (run.status === "running") {
      setStreamView(true);
      setStreamText("");
      setStreaming(true);

      // Start streaming
      const cleanup = apiStreamRun(
        run.id,
        (data) => {
          // Handle streaming chunks
          if (typeof data === 'string') {
            setStreamText(prev => prev + data);
          } else if (typeof data === 'object' && data !== null) {
            const dataObj = data as Record<string, unknown>;
            if (dataObj.content) {
              setStreamText(prev => prev + (dataObj.content as string));
            }
          }
        },
        () => {
          setStreaming(false);
          loadRuns(); // Refresh run data after completion
        }
      );
      cleanupRef.current = cleanup;
    } else {
      setStreamView(false);

      // Load full run details
      try {
        const detail = await apiGetRun(run.id);
        if (detail) {
          setSelectedRun({
            ...run,
            input: detail.input,
            output: detail.output,
            error: detail.error,
            tokens: detail.tokens,
            toolCalls: detail.toolCalls?.map(tc => ({
              name: tc.name,
              input: typeof tc.input === 'string' ? tc.input : JSON.stringify(tc.input),
              output: typeof tc.output === 'string' ? tc.output : JSON.stringify(tc.output),
              duration: tc.duration,
            })) || [],
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
  };

  if (loading) {
    return (
      <div className="flex-1 min-h-0 flex items-center justify-center p-6 lg:p-8">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (selectedRun) {
    return (
      <div className="flex-1 min-h-0 flex flex-col gap-6 p-6 lg:p-8">
        <Button variant="ghost" onClick={handleBack} className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4 mr-2" /> Back to runs
        </Button>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">{selectedRun.agent}</h1>
            <p className="text-muted-foreground text-sm mt-1">Triggered by {selectedRun.trigger} · {selectedRun.started_at || "—"}</p>
          </div>
          <StatusBadge status={selectedRun.status} />
        </div>

        {streamView || selectedRun.status === "running" ? (
          <div className="rounded-xl border border-border bg-[hsl(228,12%,6%)] p-5 font-mono text-sm text-success min-h-[300px]">
            <div className="flex items-center gap-2 text-muted-foreground mb-3 text-xs">
              {streaming ? <><Loader2 className="h-3 w-3 animate-spin mr-1" /> Live output</> : "Output"}
            </div>
            <pre className="whitespace-pre-wrap">{streamText || selectedRun.output || "Waiting for output..."}</pre>
          </div>
        ) : (
          <div className="space-y-4">
            {selectedRun.input && (
              <div className="rounded-xl border border-border bg-card p-5">
                <h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Input</h3>
                <p className="text-foreground text-sm whitespace-pre-wrap">{selectedRun.input}</p>
              </div>
            )}
            {selectedRun.output && (
              <div className="rounded-xl border border-border bg-card p-5">
                <h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Output</h3>
                <p className="text-foreground text-sm whitespace-pre-wrap">{selectedRun.output}</p>
              </div>
            )}
            {selectedRun.error && (
              <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-5">
                <h3 className="text-xs text-destructive uppercase tracking-wider mb-2">Error</h3>
                <p className="text-destructive text-sm font-mono">{selectedRun.error}</p>
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
                          <pre className="text-xs font-mono text-foreground bg-muted rounded p-2 mt-1 overflow-x-auto">{tc.input}</pre>
                        </div>
                        <div>
                          <span className="text-[10px] text-muted-foreground uppercase">Output</span>
                          <pre className="text-xs font-mono text-foreground bg-muted rounded p-2 mt-1 overflow-x-auto">{tc.output}</pre>
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  ))}
                </Accordion>
              </div>
            )}
            <div className="flex gap-4 text-xs text-muted-foreground">
              {selectedRun.tokens && <span>Tokens: <span className="text-foreground font-mono">{selectedRun.tokens.toLocaleString()}</span></span>}
              <span>Cost: <span className="text-foreground font-mono">{selectedRun.cost}</span></span>
              <span>Duration: <span className="text-foreground font-mono">{selectedRun.duration}</span></span>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-6 p-6 lg:p-8 overflow-hidden">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Runs</h1>
        <p className="text-muted-foreground text-sm mt-1">View execution history for all agents</p>
      </div>

      {runs.length === 0 ? (
        <EmptyState icon={Play} title="No runs yet" description="Trigger your first agent run to see results here." />
      ) : (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="rounded-xl border border-border bg-card shadow-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
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
                {runs.map(run => (
                  <tr key={run.id} className="hover:bg-accent/30 transition-colors cursor-pointer" onClick={() => handleViewRun(run)}>
                    <td className="px-5 py-3 text-sm text-foreground">{agentNameById.get(run.agent) ?? "—"}</td>
                    <td className="px-5 py-3 text-sm text-muted-foreground">{run.trigger}</td>
                    <td className="px-5 py-3"><StatusBadge status={run.status} /></td>
                    <td className="px-5 py-3 text-sm text-muted-foreground">{run.started_at || "—"}</td>
                    <td className="px-5 py-3 text-sm text-muted-foreground font-mono">{run.duration}</td>
                    <td className="px-5 py-3 text-sm text-muted-foreground font-mono">{run.cost}</td>
                    <td className="px-5 py-3"><ChevronRight className="h-4 w-4 text-muted-foreground" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}
    </div>
  );
}
