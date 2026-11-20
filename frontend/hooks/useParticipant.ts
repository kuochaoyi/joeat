"use client";
import { useEffect, useState } from "react";

import { joinSession } from "@/lib/api";
import { getIdentity } from "@/lib/liff";
import { getStoredParticipant, storeParticipant } from "@/lib/storage";
import type { Participant } from "@/lib/types";

/** Joins the session (idempotent on the server) and returns this browser's participant. */
export function useParticipant(sessionId: string) {
  const [participant, setParticipant] = useState<Participant | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await getIdentity();
        const p = await joinSession(sessionId, { line_user_id: me.userId, label: me.displayName?.slice(0, 20), id_token: me.idToken });
        storeParticipant(sessionId, p.participant_id);
        if (!cancelled) setParticipant(p);
      } catch (e) {
        const stored = getStoredParticipant(sessionId);
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
        if (stored && !cancelled) setParticipant({ participant_id: stored, session_id: sessionId, label: null, constraints_submitted: false, preferences_submitted: false, is_host: false });
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  return { participant, error, setParticipant };
}
