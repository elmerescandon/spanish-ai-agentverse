import type { NextConfig } from "next";

const FASTAPI_URL = process.env.FASTAPI_URL || "http://127.0.0.1:8000";

// Rewrites to FastAPI time out after 30 s by default; the first upload of
// a protocol (parse) and its completeness check each take minutes.
const API_PROXY_TIMEOUT_MS = 20 * 60 * 1000;

const nextConfig: NextConfig = {
  cacheComponents: true,
  experimental: {
    proxyTimeout: API_PROXY_TIMEOUT_MS,
  },
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${FASTAPI_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
