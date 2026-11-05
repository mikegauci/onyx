// Test-only stand-in for Supabase Auth, used by the Playwright suite and nowhere else.
//
// It publishes an ES256 JWKS at the same path Supabase uses, so the API and the dashboard
// verify tokens exactly as they verify real Supabase tokens: no auth bypass exists in app code.
// It listens on 127.0.0.1 only and mints sessions for the fake seeded users.
import { createHash } from "node:crypto";
import { createServer } from "node:http";

import { SignJWT, exportJWK, generateKeyPair } from "jose";

const PORT = Number(process.env.FAKE_AUTH_PORT ?? 54399);
const ORIGIN = `http://127.0.0.1:${PORT}`;
const ISSUER = `${ORIGIN}/auth/v1`;
const KID = "e2e-key-1";
// Must match SEED_NAMESPACE in apps/api/app/core/db/seed.py.
const SEED_NAMESPACE = "6f1c2a52-0b7e-4f7d-9a51-3c1f0e0d5a01";

const { privateKey, publicKey } = await generateKeyPair("ES256");
const jwk = { ...(await exportJWK(publicKey)), kid: KID, alg: "ES256", use: "sig" };

export function uuidv5(name, namespace = SEED_NAMESPACE) {
  const ns = Buffer.from(namespace.replaceAll("-", ""), "hex");
  const hash = createHash("sha1")
    .update(Buffer.concat([ns, Buffer.from(name)]))
    .digest();
  hash[6] = (hash[6] & 0x0f) | 0x50;
  hash[8] = (hash[8] & 0x3f) | 0x80;
  const hex = hash.subarray(0, 16).toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function session(email) {
  const sub = uuidv5(`auth:${email}`);
  const now = Math.floor(Date.now() / 1000);
  const accessToken = await new SignJWT({
    email,
    role: "authenticated",
    aal: "aal1",
    is_anonymous: false,
    session_id: crypto.randomUUID(),
  })
    .setProtectedHeader({ alg: "ES256", kid: KID, typ: "JWT" })
    .setIssuer(ISSUER)
    .setAudience("authenticated")
    .setSubject(sub)
    .setIssuedAt(now)
    .setExpirationTime(now + 3600)
    .sign(privateKey);
  return {
    access_token: accessToken,
    token_type: "bearer",
    expires_in: 3600,
    expires_at: now + 3600,
    refresh_token: `e2e-refresh-${sub}`,
    user: {
      id: sub,
      aud: "authenticated",
      role: "authenticated",
      email,
      app_metadata: { provider: "email" },
      user_metadata: {},
      created_at: new Date(0).toISOString(),
    },
  };
}

function send(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(body === undefined ? "" : JSON.stringify(body));
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", ORIGIN);
  if (req.method === "GET" && url.pathname === "/auth/v1/.well-known/jwks.json") {
    return send(res, 200, { keys: [jwk] });
  }
  if (req.method === "GET" && url.pathname === "/__e2e/session") {
    const email = url.searchParams.get("email");
    if (!email?.endsWith(".example.test")) return send(res, 400, { error: "fake users only" });
    return send(res, 200, await session(email));
  }
  if (req.method === "POST" && url.pathname === "/auth/v1/logout") return send(res, 204);
  if (url.pathname === "/health") return send(res, 200, { ok: true });
  return send(res, 404, { error: "not found" });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`fake auth listening on ${ORIGIN}`);
});
