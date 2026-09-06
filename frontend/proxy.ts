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
  if (pathname === "/login" && hasSession) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/workspace/:path*", "/admin/:path*", "/portal", "/login"] };
