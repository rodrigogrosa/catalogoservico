/**
 * BFF route: /api/catalog
 *
 * Acts as an aggregation / caching layer between the Next.js frontend and
 * the FastAPI backend.  Keeps the backend token server-side and adds a
 * short-lived server cache so repeat renders don't hit the backend.
 *
 * Query params forwarded to backend:
 *   page      – 1-based page number (default 1)
 *   per_page  – items per page (default 20, max 200)
 *   status    – filter by project status
 *   search    – fuzzy name search
 */
import { type NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function backendOrigin(): string {
  return process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
}

/** Read the auth token from either the Authorization header or the cookie. */
async function getToken(req: NextRequest): Promise<string | null> {
  const authHeader = req.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    return authHeader.slice(7);
  }
  const cookieStore = await cookies();
  return cookieStore.get("auth_token")?.value ?? null;
}

// ---------------------------------------------------------------------------
// GET /api/catalog
// ---------------------------------------------------------------------------

export async function GET(req: NextRequest) {
  const token = await getToken(req);
  if (!token) {
    return NextResponse.json({ detail: "Autenticação obrigatória." }, { status: 401 });
  }

  // Forward pagination / filter params.
  const { searchParams } = req.nextUrl;
  const page = searchParams.get("page") ?? "1";
  const perPage = searchParams.get("per_page") ?? "20";
  const status = searchParams.get("status");
  const search = searchParams.get("search");

  const params = new URLSearchParams({ page, per_page: perPage });
  if (status) params.set("status", status);
  if (search) params.set("search", search);

  const upstream = `${backendOrigin()}/projects?${params.toString()}`;

  try {
    const res = await fetch(upstream, {
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      // Next.js cache: revalidate every 15 s — stale-while-revalidate semantics.
      // This means the BFF serves a cached response immediately and refreshes
      // in the background, so the catalog page never blocks on a slow NFS scan.
      next: { revalidate: 15 },
    });

    if (!res.ok) {
      const body = await res.text();
      return NextResponse.json({ detail: body }, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data, {
      status: 200,
      headers: {
        // Expose cache metadata to the client for debugging.
        "X-BFF-Cache": "15s",
      },
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { detail: `Erro ao contatar o backend: ${message}` },
      { status: 502 },
    );
  }
}
