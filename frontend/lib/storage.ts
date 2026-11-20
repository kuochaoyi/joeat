// The participant id for a session is kept in this browser (the id acts as the capability for the MVP; no full auth yet).
const key = (sessionId: string) => `joeat:participant:${sessionId}`;

export const getStoredParticipant = (sessionId: string): string | null =>
  typeof window === "undefined" ? null : window.localStorage.getItem(key(sessionId));

export const storeParticipant = (sessionId: string, participantId: string) => window.localStorage.setItem(key(sessionId), participantId);
