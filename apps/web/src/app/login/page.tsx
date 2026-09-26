"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createBrowserClient } from "@/lib/supabase";
import { Zap } from "lucide-react";

const OAUTH_PENDING_KEY = "novacrm_oauth_pending";

function MicrosoftLogo() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 21 21">
      <rect x="1" y="1" width="9" height="9" fill="#F25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
      <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
      <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
    </svg>
  );
}

function LoginInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(() =>
    searchParams.get("error") === "confirm"
      ? "That confirmation link was already used or has expired. If you already confirmed, just sign in below; otherwise sign up again to get a new link."
      : null,
  );
  const [message, setMessage] = useState<string | null>(() =>
    searchParams.get("confirmed") === "1"
      ? "Email confirmed! Sign in to continue."
      : null,
  );

  // /auth/callback sends every provider error to ?error=confirm. If we just
  // bounced out to Microsoft, the failure was the OAuth hop, not an email link.
  // Read in an effect (not the state initializer) so SSR and hydration agree.
  useEffect(() => {
    let viaOAuth = false;
    try {
      viaOAuth = sessionStorage.getItem(OAUTH_PENDING_KEY) === "1";
      sessionStorage.removeItem(OAUTH_PENDING_KEY);
    } catch {
      return; // storage blocked — keep the email-link message
    }
    if (viaOAuth && searchParams.get("error") === "confirm") {
      setError("Microsoft sign-in didn't complete. Try again, or use email and password below.");
    }
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);

    const supabase = createBrowserClient();

    if (mode === "login") {
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      if (signInError) {
        setError("Invalid email or password. Please try again.");
        setLoading(false);
        return;
      }
      router.push("/dashboard");
    } else {
      const { error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          // Confirmation email link redirects here; the callback exchanges the
          // code for a session and forwards into the app.
          emailRedirectTo: `${window.location.origin}/auth/callback`,
        },
      });
      if (signUpError) {
        setError(signUpError.message);
        setLoading(false);
        return;
      }
      setMessage("Account created! Check your email to confirm, then sign in.");
      setMode("login");
    }

    setLoading(false);
  };

  const handleMicrosoft = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      sessionStorage.setItem(OAUTH_PENDING_KEY, "1");
    } catch {
      // non-fatal: only affects which error message a failed hop shows
    }
    const supabase = createBrowserClient();
    // Supabase's "azure" provider covers both work/school (Microsoft 365) and
    // personal (outlook.com / hotmail / live) accounts. The "email" scope is
    // required or Azure omits the address and Supabase rejects the sign-in.
    // Same /auth/callback as email confirmation: it exchanges the PKCE code.
    const { error: oauthError } = await supabase.auth.signInWithOAuth({
      provider: "azure",
      options: {
        scopes: "email",
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });
    if (oauthError) {
      setError(oauthError.message);
      setLoading(false);
    }
    // On success the browser is navigating away to Microsoft; keep loading state.
  };

  return (
    <div className="min-h-[100dvh] bg-[#09090B] flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-10 justify-center">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600">
            <Zap className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-base font-semibold text-zinc-100 leading-none">NovaCRM</p>
            <p className="text-[10px] text-zinc-500 mt-0.5 font-mono">Agentic Intelligence</p>
          </div>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 sm:p-8">
          <h1 className="text-xl font-semibold text-zinc-100 mb-1">
            {mode === "login" ? "Sign in to your workspace" : "Create your account"}
          </h1>
          <p className="text-sm text-zinc-500 mb-6">
            {mode === "login"
              ? "Enter your credentials to continue."
              : "Get started with a free account."}
          </p>

          {error && (
            <div className="mb-4 rounded-lg bg-rose-500/10 border border-rose-500/20 px-4 py-3 text-sm text-rose-400">
              {error}
            </div>
          )}
          {message && (
            <div className="mb-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-4 py-3 text-sm text-emerald-400">
              {message}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                autoComplete="email"
                inputMode="email"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-3 text-base sm:text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                minLength={6}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-3 text-base sm:text-sm text-zinc-100 placeholder-zinc-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition cursor-pointer"
            >
              {loading ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <div className="my-5 flex items-center gap-3">
            <div className="h-px flex-1 bg-zinc-800" />
            <span className="text-[11px] uppercase tracking-wide text-zinc-600">or</span>
            <div className="h-px flex-1 bg-zinc-800" />
          </div>

          <button
            type="button"
            onClick={handleMicrosoft}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2.5 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-3 text-sm font-medium text-zinc-200 hover:border-zinc-600 hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed transition cursor-pointer"
          >
            <MicrosoftLogo />
            Continue with Microsoft
          </button>
          <p className="mt-2 text-center text-[11px] text-zinc-600">
            Outlook, Hotmail, Live, or Microsoft 365 work accounts
          </p>

          <p className="mt-5 text-center text-xs text-zinc-500">
            {mode === "login" ? (
              <>
                No account?{" "}
                <button
                  onClick={() => { setMode("signup"); setError(null); }}
                  className="text-indigo-400 hover:text-indigo-300 transition"
                >
                  Sign up
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  onClick={() => { setMode("login"); setError(null); }}
                  className="text-indigo-400 hover:text-indigo-300 transition"
                >
                  Sign in
                </button>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}

// Next.js 16 requires useSearchParams() inside a Suspense boundary.
export default function LoginPage() {
  return (
    <Suspense>
      <LoginInner />
    </Suspense>
  );
}
