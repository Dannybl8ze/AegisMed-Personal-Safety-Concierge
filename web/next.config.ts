import type { NextConfig } from "next";

// `NEXT_OUTPUT=export` builds plain static files (used by the Docker image,
// where FastAPI serves them next to the API).
const isStaticExport = process.env.NEXT_OUTPUT === "export";

// Local development only: forward /api/* to the FastAPI server. On Vercel the
// platform routes /api/* to the API service before Next.js sees the request.
const apiProxyTarget = process.env.API_PROXY_TARGET;

const nextConfig: NextConfig = {
  // Cache Components (and its partial prerendering) cannot be used in export mode.
  ...(isStaticExport ? { output: "export" as const } : { cacheComponents: true, partialPrefetching: true }),
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  ...(!isStaticExport && apiProxyTarget
    ? {
        async rewrites() {
          return [{ source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` }];
        },
      }
    : {}),
};

export default nextConfig;
