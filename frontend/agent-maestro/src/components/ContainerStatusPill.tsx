import { useState, useEffect } from "react";

type Status = "online" | "starting" | "offline";

export function ContainerStatusPill() {
  const [status, setStatus] = useState<Status>("starting");

  useEffect(() => {
    const timer = setTimeout(() => setStatus("online"), 2000);
    return () => clearTimeout(timer);
  }, []);

  const config: Record<Status, { label: string; dotClass: string; bgClass: string }> = {
    online: {
      label: "Online",
      dotClass: "bg-success",
      bgClass: "bg-success/10 text-success",
    },
    starting: {
      label: "Starting",
      dotClass: "bg-warning animate-pulse-glow",
      bgClass: "bg-warning/10 text-warning",
    },
    offline: {
      label: "Offline",
      dotClass: "bg-destructive",
      bgClass: "bg-destructive/10 text-destructive",
    },
  };

  const c = config[status];

  return (
    <button
      onClick={() => setStatus(status === "online" ? "offline" : status === "offline" ? "starting" : "online")}
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium transition-colors ${c.bgClass}`}
    >
      <span className={`h-2 w-2 rounded-full ${c.dotClass}`} />
      {c.label}
    </button>
  );
}
