import { useState, useEffect, useMemo } from "react";
import { motion } from "framer-motion";
import { Bot, Play, Calendar, Wrench, Plus, Zap, ArrowRight, Loader2, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { useNavigate } from "react-router-dom";
import { apiGetDashboardStats, apiGetRecentRuns, apiGetTools, apiGetAgents, type Run, type Agent as ApiAgent } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { AVATAR_MAP } from "@/lib/avatars";
import { useAgentAvatar } from "@/lib/agentAvatar";

interface DashboardStats {
  active_agents: number;
  runs_today: number;
  schedules_active: number;
  tools_connected: number;
}

interface RecentRun {
  id: string;
  agent: string;
  agent_id?: string;
  status: Run["status"];
  started: string;
  duration: string;
  schedule_id?: string | null;
  schedule_name?: string | null;
}

const container = { hidden: {}, show: { transition: { staggerChildren: 0.05 } } };
const item = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } };

const statsConfig = [
  { key: "active_agents", label: "Active Agents", icon: Bot, changeLabel: "agents" },
  { key: "runs_today", label: "Runs Today", icon: Play, changeLabel: "runs" },
  { key: "schedules_active", label: "Schedules Active", icon: Calendar, changeLabel: "schedules" },
  { key: "tools_connected", label: "Tools Connected", icon: Wrench, changeLabel: "tools" },
] as const;

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentRuns, setRecentRuns] = useState<RecentRun[]>([]);
  const [agents, setAgents] = useState<ApiAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { toast } = useToast();

  // Fetch agents for avatar lookup
  useEffect(() => {
    apiGetAgents()
      .then((data) => setAgents(data ?? []))
      .catch((err) => {
        console.error("Failed to fetch agents:", err);
        setAgents([]);
      });
  }, []);

  // Build agent avatar lookup map keyed by agent id - use slugToSrc for direct resolution
  const agentAvatarById = useMemo(() => {
    const map = new Map<string, string>();
    for (const agent of agents) {
      map.set(agent.id, AVATAR_MAP[agent.avatar] || AVATAR_MAP["avatar-01"]);
    }
    return map;
  }, [agents]);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const [statsData, runsData, toolsData] = await Promise.all([
          apiGetDashboardStats(),
          apiGetRecentRuns(10),
          apiGetTools(),
        ]);

        // Calculate tools_connected: only count external tools (composio, apify, maton) that are configured
        // Exclude API keys (source: "api_key") - these are LLM provider keys, not tools
        const externalTools = (toolsData ?? []).filter(
          (t: any) => !t.builtin && (t.connected || t.configured) && t.source !== "api_key"
        );
        const toolsConnectedCount = externalTools.length;

        // Debug: Log what tools the API is returning
        console.log("🔧 API Tools Data:", JSON.stringify(toolsData, null, 2));
        console.log("🔧 External connected tools:", externalTools.map(t => ({
          name: t.name,
          source: t.source,
          builtin: t.builtin,
          connected: t.connected,
          configured: t.configured
        })));
        console.log("🔧 Final tools_connected count:", toolsConnectedCount);

        setStats({
          ...statsData,
          tools_connected: toolsConnectedCount,
        });
        setRecentRuns(runsData as RecentRun[]);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load dashboard data";
        toast({ title: "Error", description: message, variant: "destructive" });
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [toast]);

  if (loading) {
    return (
      <div className="flex-1 min-h-0 flex items-center justify-center p-6 lg:p-8">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const statsCards = stats ? statsConfig.map((config) => {
    const value = stats[config.key] ?? 0;
    return {
      label: config.label,
      value: value.toString(),
      icon: config.icon,
      change: `${value} ${config.changeLabel}`,
    };
  }) : [];

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-8 p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Dashboard</h1>
        <p className="text-muted-foreground text-sm mt-1">Overview of your OCIN workspace</p>
      </div>

      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
      >
        {statsCards.map((s, i) => (
          <motion.div
            key={s.label}
            variants={item}
            className="rounded-xl border border-border bg-card p-5 shadow-card hover:border-primary/30 transition-colors"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-muted-foreground">{s.label}</span>
              <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <s.icon className="h-4 w-4 text-primary" />
              </div>
            </div>
            <p className="text-3xl font-bold text-foreground font-mono">{s.value}</p>
            <p className="text-xs text-muted-foreground mt-1">{s.change}</p>
          </motion.div>
        ))}
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 rounded-xl border border-border bg-card shadow-card">
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <h2 className="text-foreground font-semibold text-sm">Recent Runs</h2>
            <Button variant="ghost" size="sm" className="text-primary text-xs" onClick={() => navigate("/runs")}>
              View all <ArrowRight className="h-3 w-3 ml-1" />
            </Button>
          </div>
          <div className="divide-y divide-border">
            {recentRuns.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground text-sm">No runs yet</div>
            ) : (
              recentRuns.map((run) => (
                <div
                  key={run.id}
                  className="flex items-center justify-between px-5 py-3 hover:bg-accent/50 transition-colors cursor-pointer"
                  onClick={() => navigate("/runs", { state: { selectedRunId: run.id } })}
                >
                  <div className="flex items-center gap-3">
                    {run.agent_id ? (
                      <img
                        src={agentAvatarById.get(run.agent_id) || ""}
                        alt={run.agent}
                        className="h-7 w-7 rounded-md object-cover"
                        loading="lazy"
                        width={28}
                        height={28}
                      />
                    ) : (
                      <div className="h-7 w-7 rounded-md bg-secondary flex items-center justify-center">
                        <Bot className="h-3.5 w-3.5 text-muted-foreground" />
                      </div>
                    )}
                    <div>
                      <p className="text-sm text-foreground">{run.agent}</p>
                      <p className="text-xs text-muted-foreground">
                        {run.schedule_id && run.schedule_name ? (
                          <span className="flex items-center gap-1">
                            <Calendar className="h-3 w-3" />
                            {run.schedule_name}
                            <ExternalLink className="h-3 w-3 ml-1" />
                          </span>
                        ) : (
                          run.started
                        )}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground font-mono">{run.duration}</span>
                    <StatusBadge status={run.status} />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card p-5 shadow-card">
            <h2 className="text-foreground font-semibold text-sm mb-4">Quick Actions</h2>
            <div className="space-y-2">
              <Button
                className="w-full justify-start gradient-primary text-primary-foreground"
                onClick={() => navigate("/agents")}
              >
                <Plus className="h-4 w-4 mr-2" /> Create agent
              </Button>
              <Button
                variant="outline"
                className="w-full justify-start border-border text-foreground hover:bg-accent"
                onClick={() => navigate("/runs")}
              >
                <Zap className="h-4 w-4 mr-2" /> Run agent now
              </Button>
              <Button
                variant="outline"
                className="w-full justify-start border-border text-foreground hover:bg-accent"
                onClick={() => navigate("/schedules")}
              >
                <Calendar className="h-4 w-4 mr-2" /> Add schedule
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
