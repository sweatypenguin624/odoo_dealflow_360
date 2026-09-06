import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Server-side route protection: no session cookie -> login. The backend is
// the real authority; this only keeps unauthenticated users off the app
// shell (the CSRF cookie is the non-httpOnly companion of the session).
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has("df_csrf") || request.cookies.has("df_access");
  const isProtected = pathname.startsWith("/workspace") || pathname.startsWith("/admin") || pathname === "/portal";
  if (isProtected && !hasSession) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", pathname);
    return NextResponse.redirect(login);
  }
  // /login is deliberately NOT redirected here. df_csrf outlives the session
  // cookie by days, so "has a cookie" is not "is signed in": bouncing /login to
  // / on that evidence loops forever against the client guards, which send an
  // unauthenticated visitor straight back to /login. The login page itself
  // redirects when it sees a session that is genuinely live.
  return NextResponse.next();
}

export const config = { matcher: ["/workspace/:path*", "/admin/:path*", "/portal"] };
