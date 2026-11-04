/** Paths that require a signed-in user. The API still authorises every request. */
export function isProtectedPath(pathname: string): boolean {
  return (
    pathname === "/workspaces" ||
    pathname.startsWith("/workspaces/") ||
    pathname === "/w" ||
    pathname.startsWith("/w/")
  );
}

/** Login URL that returns the user to where they were going. */
export function loginRedirect(pathname: string, search: string, origin: string): URL {
  const url = new URL("/login", origin);
  url.searchParams.set("next", `${pathname}${search}`);
  return url;
}
