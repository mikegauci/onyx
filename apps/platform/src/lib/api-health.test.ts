import { getApiHealth } from "./api-health";

const BASE = "http://api.test";

function fakeFetch(response: Response | Error): typeof fetch {
  return vi.fn(async () => {
    if (response instanceof Error) throw response;
    return response;
  }) as unknown as typeof fetch;
}

describe("getApiHealth", () => {
  it("returns ok with service and version on a healthy response", async () => {
    const fetchImpl = fakeFetch(
      Response.json({ status: "ok", service: "onyx-api", version: "0.1.0" }),
    );

    await expect(getApiHealth(BASE, fetchImpl)).resolves.toEqual({
      state: "ok",
      service: "onyx-api",
      version: "0.1.0",
    });
    expect(fetchImpl).toHaveBeenCalledWith(new URL("/health", BASE), expect.anything());
  });

  it("returns unreachable on a non-2xx status", async () => {
    const result = await getApiHealth(BASE, fakeFetch(new Response("down", { status: 503 })));

    expect(result).toEqual({ state: "unreachable", reason: "HTTP 503" });
  });

  it("returns unreachable on a malformed body", async () => {
    const result = await getApiHealth(BASE, fakeFetch(Response.json({ nope: true })));

    expect(result).toEqual({ state: "unreachable", reason: "Unexpected response" });
  });

  it("returns unreachable when the network call fails", async () => {
    const result = await getApiHealth(BASE, fakeFetch(new TypeError("fetch failed")));

    expect(result).toEqual({ state: "unreachable", reason: "No response" });
  });
});
