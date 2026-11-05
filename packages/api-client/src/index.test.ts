import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { REQUEST_ID_HEADER, apiErrorOf, createApiClient } from "./index";

const packageDir = fileURLToPath(new URL("..", import.meta.url));

describe("generated schema", () => {
  it("matches openapi.json (run `make api-client` if this fails)", () => {
    const out = join(mkdtempSync(join(tmpdir(), "onyx-api-client-")), "schema.ts");
    execFileSync(
      join(packageDir, "node_modules", ".bin", "openapi-typescript"),
      ["openapi.json", "--output", out],
      { cwd: packageDir, stdio: "pipe" },
    );
    expect(readFileSync(out, "utf8")).toBe(readFileSync(join(packageDir, "src/schema.ts"), "utf8"));
  });
});

describe("createApiClient", () => {
  it("sends the bearer token and request id to versioned paths", async () => {
    const fetchMock = vi.fn<typeof fetch>(
      async () =>
        new Response(JSON.stringify({ user: {}, workspaces: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    const client = createApiClient({
      baseUrl: "https://api.example.test",
      accessToken: "tok",
      requestId: "req-1",
      fetch: fetchMock,
    });

    const { data } = await client.GET("/v1/me");

    expect(data).toEqual({ user: {}, workspaces: [] });
    const request = fetchMock.mock.calls[0]![0] as Request;
    expect(request.url).toBe("https://api.example.test/v1/me");
    expect(request.headers.get("Authorization")).toBe("Bearer tok");
    expect(request.headers.get(REQUEST_ID_HEADER)).toBe("req-1");
  });

  it("returns the standard error body on failure", async () => {
    const body = { error: { code: "permission_denied", message: "No.", request_id: "r" } };
    const client = createApiClient({
      baseUrl: "https://api.example.test",
      fetch: async () =>
        new Response(JSON.stringify(body), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        }),
    });

    const { error, response } = await client.PATCH("/v1/w/{slug}", {
      params: { path: { slug: "lumen" } },
      body: { name: "x" },
    });

    expect(response.status).toBe(403);
    expect(apiErrorOf(error)?.code).toBe("permission_denied");
  });
});

describe("apiErrorOf", () => {
  it.each([null, "x", {}, { error: null }, { error: { code: 1 } }])("rejects %j", (value) => {
    expect(apiErrorOf(value)).toBeUndefined();
  });
});
