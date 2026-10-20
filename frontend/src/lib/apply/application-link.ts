type ApplicationLink = { token: string | null; invalid: boolean };
let captured: ApplicationLink | null = null;

/** Runs before monitoring/hydration; the secret never travels in a request URL or storage. */
export function captureApplicationLink(): boolean {
  if (typeof window === "undefined" || window.location.pathname !== "/apply") return true;
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  if (!fragment.has("application_access_token")) return true;
  const values = fragment.getAll("application_access_token");
  try {
    window.history.replaceState(
      window.history.state,
      "",
      window.location.pathname + window.location.search,
    );
  } catch {
    captured = { token: null, invalid: true };
    return false;
  }
  const token = values.length === 1 ? values[0] : undefined;
  const valid = Boolean(
    token && token.length <= 8192 && !/[\u0000-\u0020\u007f-\u009f]/u.test(token),
  );
  captured = { token: valid ? token! : null, invalid: !valid };
  return true;
}

export function takeApplicationLink(): ApplicationLink | null {
  captureApplicationLink();
  const link = captured;
  captured = null;
  return link;
}
