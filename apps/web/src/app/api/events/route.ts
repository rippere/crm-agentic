import { NextRequest } from "next/server";
import { cookies } from "next/headers";
import { createServerClient } from "@/lib/supabase";

const FASTAPI = process.env.NEXT_PUBLIC_FASTAPI_URL ?? "http://localhost:8000";

// Proxy SSE stream from FastAPI to the browser.
//
// The browser's EventSource is same-origin, so its Supabase auth cookies ride
// along automatically — we read the session server-side here instead of taking
// an access token from the URL query string (which would leak the bearer token
// into server logs, the browser history, and Referer headers).
export async function GET(request: NextRequest) {
  const workspaceId = request.nextUrl.searchParams.get("workspaceId");

  if (!workspaceId) {
    return new Response("Missing workspaceId", { status: 400 });
  }

  const cookieStore = await cookies();
  const supabase = createServerClient(cookieStore);
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const token = session?.access_token;
  if (!token) {
    return new Response("Unauthorized", { status: 401 });
  }

  const upstream = await fetch(`${FASTAPI}/workspaces/${workspaceId}/events`, {
    headers: { Authorization: `Bearer ${token}` },
    // @ts-expect-error — Node 18 fetch supports duplex streaming
    duplex: "half",
  });

  if (!upstream.ok || !upstream.body) {
    return new Response("Upstream error", { status: 502 });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}
