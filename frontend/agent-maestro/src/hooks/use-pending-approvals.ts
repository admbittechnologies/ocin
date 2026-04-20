import { useState, useEffect } from "react";
import { apiGetPendingApprovalsCount } from "@/lib/api";

export function usePendingApprovals() {
  const [count, setCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    const fetchCount = async () => {
      try {
        setLoading(true);
        const data = await apiGetPendingApprovalsCount();
        setCount(data.count);
      } catch (error) {
        console.error("Failed to fetch pending approvals count:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchCount();

    const interval = setInterval(fetchCount, 30000); // Poll every 30 seconds

    return () => {
      clearInterval(interval);
    };
  }, []);

  return { count, loading, refetch: () => fetchCount() };
}
