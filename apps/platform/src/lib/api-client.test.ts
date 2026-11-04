import { toResult } from "./api-client";

vi.mock("server-only", () => ({}));
vi.mock("./supabase/server", () => ({ getAccessToken: async () => null }));

describe("toResult", () => {
  it("returns data on success", async () => {
    const result = await toResult<{ a: number }>(Response.json({ a: 1 }));
    expect(result).toEqual({ ok: true, data: { a: 1 } });
  });

  it.each([
    [401, "unauthenticated"],
    [403, "forbidden"],
    [404, "not_found"],
    [500, "unavailable"],
    [503, "unavailable"],
  ])("maps HTTP %i to %s", async (status, expected) => {
    expect(await toResult(new Response(null, { status }))).toEqual({ ok: false, status: expected });
  });
});

describe("apiGet", () => {
  it("does not call the API without a session", async () => {
    const { apiGet } = await import("./api-client");
    const fetchImpl = vi.fn();
    expect(await apiGet("/me", fetchImpl)).toEqual({ ok: false, status: "unauthenticated" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
