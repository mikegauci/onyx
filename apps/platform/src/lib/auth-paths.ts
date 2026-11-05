/** Paths that require a signed-in user. The API still authorises every request. */
const PROTECTED_PREFIXES = ["/workspaces", "/w", "/admin", "/invitations"];

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/** Login URL that returns the user to where they were going. */
export function loginRedirect(pathname: string, search: string, origin: string): URL {
  const url = new URL("/login", origin);
  url.searchParams.set("next", `${pathname}${search}`);
  return url;
}
