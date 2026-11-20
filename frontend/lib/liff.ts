// LIFF identity. With NEXT_PUBLIC_LIFF_ID set this uses the real LINE login / group context.
// Without it (plain browser demo) a random dev user id is created once and kept in localStorage.
export interface Identity {
  userId: string;
  displayName?: string;
  idToken?: string;
  groupId?: string;
  inLiff: boolean;
}

const LIFF_ID = process.env.NEXT_PUBLIC_LIFF_ID || "";
let cached: Promise<Identity> | null = null;

function devIdentity(): Identity {
  const key = "joeat:devUserId";
  let id = window.localStorage.getItem(key);
  if (!id) {
    id = "dev-" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
    window.localStorage.setItem(key, id);
  }
  return { userId: id, inLiff: false };
}

export function getIdentity(): Promise<Identity> {
  if (cached) return cached;
  cached = (async () => {
    if (!LIFF_ID) return devIdentity();
    const liff = (await import("@line/liff")).default;
    await liff.init({ liffId: LIFF_ID });
    if (!liff.isLoggedIn()) {
      liff.login();                                   // redirects; the promise never settles on purpose
      return new Promise<Identity>(() => undefined);
    }
    const profile = await liff.getProfile();
    const ctx = liff.getContext();
    return { userId: profile.userId, displayName: profile.displayName, idToken: liff.getIDToken() || undefined, groupId: ctx?.groupId || ctx?.roomId, inLiff: true };
  })();
  return cached;
}

export async function shareText(text: string): Promise<boolean> {
  if (!LIFF_ID) return false;
  const liff = (await import("@line/liff")).default;
  if (liff.isApiAvailable("shareTargetPicker")) {
    await liff.shareTargetPicker([{ type: "text", text }]);
    return true;
  }
  return false;
}
