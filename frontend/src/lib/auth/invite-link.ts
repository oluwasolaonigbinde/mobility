let token: string | null = null;

/** Capture the fragment before monitoring starts; keep it only in page memory. */
export function captureAdvertiserInviteLink(): boolean {
  if (typeof window === "undefined" || window.location.pathname !== "/advertiser-invite")
    return true;
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  if (!fragment.has("token")) {
    token ??= "";
    return true;
  }
  const values = fragment.getAll("token");
  try {
    window.history.replaceState(
      window.history.state,
      "",
      window.location.pathname + window.location.search,
    );
  } catch {
    token = "";
    return false;
  }
  const value = values.length === 1 ? values[0] : undefined;
  token = value && value.length <= 512 && !/[\u0000-\u0020\u007f-\u009f]/u.test(value) ? value : "";
  return true;
}

export function inviteTokenSnapshot() {
  return token;
}
export function inviteServerSnapshot() {
  return null;
}
export function subscribeInviteLink(changed: () => void) {
  const update = () => {
    captureAdvertiserInviteLink();
    changed();
  };
  update();
  window.addEventListener("hashchange", update);
  return () => window.removeEventListener("hashchange", update);
}
