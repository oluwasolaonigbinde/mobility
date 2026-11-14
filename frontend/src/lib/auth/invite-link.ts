import { useSyncExternalStore } from "react";

export type FragmentTokenLink = {
  capture(): boolean;
  snapshot(): string | null;
  serverSnapshot(): null;
  subscribe(changed: () => void): () => void;
};

/**
 * A one-time `#token=` link for one page (D130/D149). The fragment is captured before
 * monitoring starts and kept only in page memory: `null` until read, `""` when incomplete.
 */
function fragmentTokenLink(pathname: string): FragmentTokenLink {
  let token: string | null = null;

  function capture(): boolean {
    if (typeof window === "undefined" || window.location.pathname !== pathname) return true;
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
    token = value && value.length <= 512 && !/[\u0000- \u007f-\u009f]/u.test(value) ? value : "";
    return true;
  }

  return {
    capture,
    snapshot: () => token,
    serverSnapshot: () => null,
    subscribe(changed) {
      const update = () => {
        capture();
        changed();
      };
      update();
      window.addEventListener("hashchange", update);
      return () => window.removeEventListener("hashchange", update);
    },
  };
}

export const advertiserInviteLink = fragmentTokenLink("/advertiser-invite");
export const passwordResetLink = fragmentTokenLink("/reset-password");
export const driverAccountSetupLink = fragmentTokenLink("/driver-account-setup");

/** The page's token: `null` while the server render or hydration is pending, then the capture. */
export function useFragmentToken(link: FragmentTokenLink): string | null {
  return useSyncExternalStore(link.subscribe, link.snapshot, link.serverSnapshot);
}
