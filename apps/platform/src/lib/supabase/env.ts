import { InvalidEnvError, publicUrl } from "../public-url";

export type SupabaseEnv = { url: string; publishableKey: string };

/**
 * Supabase Auth settings. Both values are public (the publishable key is designed for
 * browsers). Deployed builds must set them; local builds without them disable sign-in.
 */
export function supabaseEnv(env: NodeJS.ProcessEnv = process.env): SupabaseEnv | null {
  const deployed = env.VERCEL_ENV === "preview" || env.VERCEL_ENV === "production";
  const rawUrl = env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!rawUrl && !key && !deployed) return null;
  if (!rawUrl || !key) {
    throw new InvalidEnvError(
      "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY must both be set.",
    );
  }
  if (key.startsWith("sb_secret_")) {
    throw new InvalidEnvError("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY must not be a secret key.");
  }
  const url = publicUrl("NEXT_PUBLIC_SUPABASE_URL", rawUrl, "", env.VERCEL_ENV);
  return { url, publishableKey: key };
}
