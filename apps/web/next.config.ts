import type { NextConfig } from "next";

const apiUrl = process.env.API_URL ?? "http://api:8000";

const nextConfig: NextConfig = {
  // The browser only ever talks to this server; /api is passed on to the API.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
  // Compressing would hold back the pieces of a streamed answer.
  compress: false,
  experimental: {
    // An answer may stream for minutes.
    proxyTimeout: 10 * 60 * 1000,
  },
  env: {
    NEXT_PUBLIC_MAX_UPLOAD_MB: process.env.MAX_UPLOAD_MB ?? "50",
  },
};

export default nextConfig;
