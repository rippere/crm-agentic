import { NextRequest } from "next/server";

const FASTAPI = process.env.NEXT_PUBLIC_FASTAPI_URL ?? "http://localhost:8000";

// Proxy SSE stream from FastAPI to the browser.
// Token is passed as a query param because EventSource cannot send custom headers.
export async function GET(request: NextRequest) {
  const workspaceId = request.nextUrl.searchParams.get("workspaceId");
  const token = request.nextUrl.searchParams.get("token");

  if (!workspaceId) {
    return new Response("Missing workspaceId", { status: 400 });
  }
  if (!token) {
    return new Response("Missing token", { status: 401 });
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
