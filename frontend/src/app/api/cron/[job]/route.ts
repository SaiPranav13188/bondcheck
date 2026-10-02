// Vercel Cron entry point (see vercel.json): forwards to the FastAPI cron endpoints, which run
// the Monitor and Alert agents. Vercel sends `Authorization: Bearer $CRON_SECRET`.
const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const JOBS: Record<string, string> = { monitor: "/cron/monitor", alerts: "/cron/alerts" };

export async function GET(request: Request, { params }: { params: Promise<{ job: string }> }) {
  const { job } = await params;
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  const path = JOBS[job];
  if (!path) return Response.json({ error: "unknown job" }, { status: 404 });
  const res = await fetch(`${API_URL}${path}`, { method: "POST", headers: { authorization: `Bearer ${secret}` } });
  return Response.json(await res.json(), { status: res.status });
}
