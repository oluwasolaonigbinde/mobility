import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = process.env.SESSION_COOKIE_NAME ?? "mobility_session";

/**
 * Fast-path redirects only. Real authentication/authorization is enforced
 * by the FastAPI backend on every proxied call, and role checks happen in
 * the server layouts (`requireRole`). This just keeps signed-out users off
 * app routes (and signed-in users off /login) without a full render.
 */
export default function proxy(request: NextRequest) {
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const { pathname } = request.nextUrl;

  const isAppRoute =
    pathname.startsWith("/advertiser") ||
    pathname.startsWith("/driver") ||
    pathname.startsWith("/admin");

  if (isAppRoute && !hasSession) {
    const login = new URL("/login", request.url);
    login.searchParams.set("from", pathname);
    return NextResponse.redirect(login);
  }

  if (pathname === "/login" && hasSession) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/advertiser/:path*", "/driver/:path*", "/admin/:path*", "/login"],
};
