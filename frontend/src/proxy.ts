import { NextResponse, type NextRequest } from "next/server";
import { sessionCookieOptions } from "@/lib/auth/cookie-options";
import { tokenNeedsRefresh } from "@/lib/auth/token";

const SESSION_COOKIE = process.env.SESSION_COOKIE_NAME ?? "mobility_session";

/**
 * Fast-path redirects only. Real authentication/authorization is enforced
 * by the FastAPI backend on every proxied call, and role checks happen in
 * the server layouts (`requireRole`). This just keeps signed-out users off
 * app routes without a full render. The login page validates an existing
 * cookie through `/me`; redirecting here based only on cookie presence would
 * trap revoked sessions in a `/login` ↔ `/` loop.
 */
interface RefreshResponse {
  access_token: string;
  expires_in: number;
}

async function responseWithRefresh(request: NextRequest, response: NextResponse) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token || request.method !== "GET" || !tokenNeedsRefresh(token, 30 * 60)) {
    return response;
  }
  try {
    const refreshed = await fetch(
      `${process.env.API_BASE_URL ?? "http://localhost:8000"}/api/v1/auth/refresh`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      },
    );
    if (!refreshed.ok) {
      if (refreshed.status === 401 || refreshed.status === 403) {
        response.cookies.delete(SESSION_COOKIE);
      }
      return response;
    }
    const data = (await refreshed.json()) as RefreshResponse;
    response.cookies.set(SESSION_COOKIE, data.access_token, sessionCookieOptions(data.expires_in));
  } catch {
    // A provider/network loss keeps the still-valid cookie. Backend guards
    // remain authoritative and the tracker treats keepalive loss as degraded.
  }
  return response;
}

export default async function proxy(request: NextRequest) {
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const { pathname } = request.nextUrl;

  // The PWA manifest must stay public: browsers fetch it WITHOUT cookies
  // (credentials mode "omit"), so an auth redirect breaks installability.
  // It contains no user data — app name, icons, colors only.
  if (pathname === "/driver/manifest.webmanifest") {
    return NextResponse.next();
  }

  const isAppRoute =
    pathname.startsWith("/advertiser") ||
    pathname.startsWith("/driver") ||
    pathname.startsWith("/admin") ||
    pathname === "/change-password";

  if (isAppRoute && !hasSession) {
    const login = new URL("/login", request.url);
    login.searchParams.set("from", pathname);
    return responseWithRefresh(request, NextResponse.redirect(login));
  }

  return responseWithRefresh(request, NextResponse.next());
}

export const config = {
  matcher: ["/advertiser/:path*", "/driver/:path*", "/admin/:path*", "/change-password", "/login"],
};
