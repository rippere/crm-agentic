import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";
import type { EmailOtpType } from "@supabase/supabase-js";

// Handles Supabase auth redirects (email confirmation, magic links, recovery).
// Exchanges the code/token for a session, sets auth cookies, then forwards the
// user into the app. Falls back to /login when a session can't be established
// in this browser (e.g. the link was opened on a different device — the email
// is still confirmed server-side by Supabase before redirecting here).
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const authError = searchParams.get("error") ?? searchParams.get("error_code");

  // Only allow same-site relative redirect targets.
  const rawNext = searchParams.get("next") ?? "/dashboard";
  const next = rawNext.startsWith("/") && !rawNext.startsWith("//") ? rawNext : "/dashboard";

  // Behind Railway's proxy the request URL is the internal origin — rebuild
  // the public origin from forwarded headers so redirects stay on riphere.com.
  const forwardedHost = request.headers.get("x-forwarded-host");
  const forwardedProto = request.headers.get("x-forwarded-proto") ?? "https";
  const base =
    process.env.NODE_ENV === "development" || !forwardedHost
      ? origin
      : `${forwardedProto}://${forwardedHost}`;

  // Supabase redirected here with an explicit error (expired/invalid link).
  if (authError) {
    return NextResponse.redirect(`${base}/login?error=confirm`);
  }

  const cookieStore = await cookies();
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet: Array<{ name: string; value: string; options?: Record<string, unknown> }>) {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options as Parameters<typeof cookieStore.set>[2]),
          );
        },
      },
    },
  );

  // PKCE flow: same browser that signed up holds the code verifier cookie.
  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(`${base}${next}`);
  }

  // OTP/token-hash flow: works regardless of which browser opens the link.
  if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
    if (!error) return NextResponse.redirect(`${base}${next}`);
  }

  // Couldn't establish a session here, but the email was confirmed by
  // Supabase's /verify before redirecting — let them sign in normally.
  return NextResponse.redirect(`${base}/login?confirmed=1`);
}
