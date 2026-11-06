import { mutateApi, toResult, withApi } from "./api-client";

vi.mock("server-only", () => ({}));
const token = vi.hoisted(() => ({ value: null as string | null }));
vi.mock("./supabase/server", () => ({ getAccessToken: async () => token.value }));
vi.mock("./env", () => ({ platformEnv: () => ({ apiUrl: "https://api.example.test" }) }));

afterEach(() => {
  token.value = null;
});

describe("toResult", () => {
  it("returns data on success", () => {
    const result = toResult({ data: { a: 1 }, response: new Response(null, { status: 200 }) });
    expect(result).toEqual({ ok: true, data: { a: 1 } });
  });

  it.each([
    [401, "unauthenticated"],
    [403, "forbidden"],
    [404, "not_found"],
    [500, "unavailable"],
    [503, "unavailable"],
  ])("maps HTTP %i to %s", (status, expected) => {
    expect(toResult({ response: new Response(null, { status }) })).toEqual({
      ok: false,
      status: expected,
    });
  });

  it("keeps the API's request id for support", () => {
    const error = { error: { code: "permission_denied", message: "No.", request_id: "abc" } };
    expect(toResult({ error, response: new Response(null, { status: 403 }) }, "mine")).toEqual({
      ok: false,
      status: "forbidden",
      requestId: "abc",
    });
  });
});

describe("withApi", () => {
  it("does not call the API without a session", async () => {
    const fetchImpl = vi.fn<typeof fetch>();
    const result = await withApi((api) => api.GET("/v1/me"), fetchImpl);
    expect(result).toEqual({ ok: false, status: "unauthenticated" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("calls the versioned API with the token and a request id", async () => {
    token.value = "tok";
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      Response.json({ user: { id: "u", email: "e", display_name: "d" }, workspaces: [] }),
    );
    const result = await withApi((api) => api.GET("/v1/me"), fetchImpl);
    expect(result.ok).toBe(true);
    const request = fetchImpl.mock.calls[0]![0] as Request;
    expect(request.url).toBe("https://api.example.test/v1/me");
    expect(request.headers.get("Authorization")).toBe("Bearer tok");
    expect(request.headers.get("X-Request-ID")).toMatch(/^[0-9a-f]{32}$/);
  });

  it("reports network failures as unavailable", async () => {
    token.value = "tok";
    const fetchImpl = vi.fn<typeof fetch>(async () => {
      throw new TypeError("network");
    });
    const result = await withApi((api) => api.GET("/v1/me"), fetchImpl);
    expect(result).toMatchObject({ ok: false, status: "unavailable" });
  });
});

describe("mutateApi", () => {
  it("treats 204 No Content as success", async () => {
    token.value = "tok";
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(null, { status: 204 }));
    const result = await mutateApi(
      (api) =>
        api.DELETE("/v1/w/{slug}/assistant/policies/{topic}", {
          params: { path: { slug: "lumen", topic: "delivery" } },
        }),
      fetchImpl,
    );
    expect(result).toEqual({ ok: true, data: undefined });
  });

  it("keeps the API error body on failure", async () => {
    token.value = "tok";
    const body = { error: { code: "conflict", message: "Reopen it first.", request_id: "r1" } };
    const fetchImpl = vi.fn<typeof fetch>(
      async () =>
        new Response(JSON.stringify(body), {
          status: 409,
          headers: { "content-type": "application/json" },
        }),
    );
    const result = await mutateApi(
      (api) =>
        api.POST("/v1/w/{slug}/assistant/conversations/{conversation_id}/runs", {
          params: { path: { slug: "lumen", conversation_id: "c1" } },
        }),
      fetchImpl,
    );
    expect(result).toMatchObject({ ok: false, status: 409, requestId: "r1" });
  });
});
