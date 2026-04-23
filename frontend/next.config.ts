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

const nextConfig: NextConfig = {
  images: {
    remotePatterns,
  },
};

export default nextConfig;
