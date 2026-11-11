import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Container builds (Dockerfile, Kubernetes) ship a minimal self-contained server; Vercel ignores this.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
};

export default nextConfig;
