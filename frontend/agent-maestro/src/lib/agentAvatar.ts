import { useEffect, useState } from "react";
import { AVATAR_MAP, AVATARS } from "./avatars";
import { apiGetAgent } from "./api";

// In-memory cache: agent_id → avatar slug (e.g. "avatar-07")
// Populated on first fetch, reused across all pages for session.
const avatarSlugCache = new Map<string, string>();

// In-flight requests: agent_id → promise resolving to slug.
// Prevents duplicate network calls when the same agent is requested
// concurrently from multiple components on the same page.
const inFlight = new Map<string, Promise<string>>();

const FALLBACK_SLUG = "avatar-01";

/**
 * Resolve a slug to a PNG src. Synchronous, pure lookup.
 */
export function slugToSrc(slug: string | undefined | null): string {
  if (!slug) return AVATARS[0];
  return AVATAR_MAP[slug] || AVATARS[0];
}

/**
 * Fetch an agent's avatar slug from the backend, with caching and
 * request deduplication. Returns slug string (e.g. "avatar-07").
 *
 * This is single source of truth — Chat, Approvals, and Agents
 * pages should all go through this.
 */
export async function getAgentAvatarSlug(agentId: string | undefined | null): Promise<string> {
  if (!agentId) return FALLBACK_SLUG;

  // Cache hit
  const cached = avatarSlugCache.get(agentId);
  if (cached) return cached;

  // In-flight dedup
  const existing = inFlight.get(agentId);
  if (existing) return existing;

  // Fresh fetch
  const promise = (async () => {
    try {
      const agent = await apiGetAgent(agentId);
      const slug = (agent as any)?.avatar || FALLBACK_SLUG;
      avatarSlugCache.set(agentId, slug);
      return slug;
    } catch (err) {
      console.warn(`Failed to fetch avatar for agent ${agentId}:`, err);
      return FALLBACK_SLUG;
    } finally {
      inFlight.delete(agentId);
    }
  })();

  inFlight.set(agentId, promise);
  return promise;
}

/**
 * Convenience: fetch slug and resolve to PNG src in one call.
 */
export async function getAgentAvatarSrc(agentId: string | undefined | null): Promise<string> {
  const slug = await getAgentAvatarSlug(agentId);
  return slugToSrc(slug);
}

/**
 * React hook: resolves an agent_id to a PNG src.
 * Returns fallback avatar during initial load, then swaps to
 * the real one when the fetch resolves.
 *
 * Usage:
 *   const avatarSrc = useAgentAvatar(agent.id);
 *   return <img src={avatarSrc} alt="" />;
 */
export function useAgentAvatar(agentId: string | undefined | null): string {
  const [src, setSrc] = useState<string>(() => {
    if (!agentId) return AVATARS[0];
    const cached = avatarSlugCache.get(agentId);
    return cached ? slugToSrc(cached) : AVATARS[0];
  });

  useEffect(() => {
    if (!agentId) {
      setSrc(AVATARS[0]);
      return;
    }
    let cancelled = false;
    getAgentAvatarSrc(agentId).then((resolved) => {
      if (!cancelled) setSrc(resolved);
    });
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  return src;
}

/**
 * Invalidate cache for a specific agent (call after editing an
 * agent's avatar) or all agents (call on logout).
 */
export function invalidateAgentAvatar(agentId?: string) {
  if (agentId) {
    avatarSlugCache.delete(agentId);
    inFlight.delete(agentId);
  } else {
    avatarSlugCache.clear();
    inFlight.clear();
  }
}
