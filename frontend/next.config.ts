import type { NextConfig } from "next";

function parseRemoteOrigin(origin: string | undefined) {
  if (!origin) {
    return null;
  }

  try {
    const url = new URL(origin);
    return {
      protocol: url.protocol.replace(":", "") as "http" | "https",
      hostname: url.hostname,
      port: url.port || undefined,
    };
  } catch {
    return null;
  }
}

const backendOrigin = parseRemoteOrigin(process.env.NEXT_PUBLIC_BACKEND_ORIGIN);
const backendOriginRaw = process.env.NEXT_PUBLIC_BACKEND_ORIGIN;
const remotePatterns: Array<{
  protocol: "http" | "https";
  hostname: string;
  port?: string;
}> = [
  {
    protocol: "http",
    hostname: "localhost",
    port: "8000",
  },
  {
    protocol: "http",
    hostname: "127.0.0.1",
    port: "8000",
  },
];

if (backendOrigin) {
  remotePatterns.push(backendOrigin);
}

// Cobertura automática para qualquer URL *.code.run (Northflank)
remotePatterns.push({ protocol: "https", hostname: "*.code.run" });
// Domínio de produção fixo
remotePatterns.push({ protocol: "https", hostname: "api.euachei3d.com.br" });

// Backend origin para CSP (permite conectar ao backend em produção)
// Também inclui *.code.run para cobrir o padrão de URL do Northflank quando
// NEXT_PUBLIC_BACKEND_ORIGIN não está disponível em build-time.
const backendCspOrigin = backendOriginRaw ?? "";
const northflankCspOrigin = "https://*.code.run";
const prodCspOrigin = "https://api.euachei3d.com.br";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      `connect-src 'self' ${backendCspOrigin} ${northflankCspOrigin} ${prodCspOrigin} https://pollinations.ai https://text.pollinations.ai https://image.pollinations.ai https://api-inference.huggingface.co`,
      "img-src 'self' data: blob: https:",
      "media-src 'self' blob:",
      // WebGL / Three.js require worker-src blob:
      "worker-src 'self' blob:",
      // Three.js e @react-three usam eval em alguns modos de dev
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline'",
      "font-src 'self'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ]
      .filter(Boolean)
      .join("; "),
  },
];

const nextConfig: NextConfig = {
  experimental: {
    middlewareClientMaxBodySize: "200mb",
    serverActions: {
      bodySizeLimit: "200mb",
    },
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
  async rewrites() {
    if (!backendOriginRaw) {
      return [];
    }

    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendOriginRaw}/api/v1/:path*`,
      },
      {
        source: "/storage/:path*",
        destination: `${backendOriginRaw}/storage/:path*`,
      },
    ];
  },
  images: {
    remotePatterns,
  },
};

export default nextConfig;
