import { NextResponse } from "next/server";

// Public service-discovery endpoint for external health monitors.
//
// External checkers (e.g. the crm-self-healer cron routine) should hit this on
// the STABLE custom domain (https://www.riphere.com/api/health-targets) and read
// the canonical, currently-deployed service URLs from here instead of hardcoding
// them. The API URL is derived from the live deployment's env, so a
// Railway-generated subdomain can change without rotting the monitoring config.
export const dynamic = "force-dynamic";

export function GET() {
  const api = (process.env.NEXT_PUBLIC_FASTAPI_URL ?? "").replace(/\/+$/, "");
  return NextResponse.json({
    service: "novacrm",
    web: "https://www.riphere.com",
    api, // e.g. https://api-production-c080.up.railway.app
    api_health: api ? `${api}/health` : "",
  });
}
