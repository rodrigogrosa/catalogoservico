#!/usr/bin/env python3
"""Publica todos os projetos concluídos na loja EuAchei3D (Mercado Livre).

Uso:
    python scripts/publish_all.py
    python scripts/publish_all.py --dry-run   # apenas simula, sem publicar
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from typing import Any

BASE_URL = "https://app.euachei3d.com.br/api/v1"
STORE_ID = "1b2536a86e4044b5a1accafb926128a5"
USERNAME = "rodrigogrosa"
PASSWORD = "Violao2021@"  # noqa: S105
PRICE_BRL = 80.0
STOCK = 10
CATEGORY_ID = "MLB439316"   # Chaveiros — categoria correta


def request(path: str, *, method: str = "GET", token: str = "", body: dict | None = None) -> tuple[int, Any]:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        return exc.code, body_text


def login() -> str:
    status, payload = request("/auth/login", method="POST", body={"username": USERNAME, "password": PASSWORD})
    if status != 200:
        sys.exit(f"❌ Login falhou ({status}): {payload}")
    token = payload.get("access_token", "")
    print(f"✅ Login OK (token={token[:20]}...)")
    return token


def fix_store_category(token: str, dry_run: bool) -> None:
    """Garante que category_id da loja aponta para MLB439316 (Chaveiros)."""
    print(f"\n🔧 Atualizando category_id da loja → {CATEGORY_ID}")
    if dry_run:
        print("   [dry-run] ignorado")
        return
    status, resp = request(
        f"/stores/{STORE_ID}",
        method="PUT",
        token=token,
        body={"settings": {"category_id": CATEGORY_ID}},
    )
    if status == 200:
        saved_cat = (resp.get("settings") or {}).get("category_id", "?")
        print(f"   ✅ category_id salvo: {saved_cat}")
    else:
        print(f"   ⚠️  Não foi possível atualizar category_id ({status}): {resp}")


def list_projects(token: str) -> list[dict]:
    status, payload = request("/projects?limit=200", token=token)
    if status != 200:
        sys.exit(f"❌ Falha ao listar projetos ({status}): {payload}")
    items = payload.get("items", [])
    print(f"\n📦 {len(items)} projeto(s) encontrado(s)")
    return items


def publish_project(token: str, project_id: str, name: str, dry_run: bool) -> dict:
    if dry_run:
        print(f"   [dry-run] POST /stores/{STORE_ID}/publish/{project_id}")
        return {"status": "dry_run"}
    status, resp = request(
        f"/stores/{STORE_ID}/publish/{project_id}",
        method="POST",
        token=token,
        body={"mode": "publish", "price_override_brl": PRICE_BRL, "stock": STOCK},
    )
    return {"http_status": status, "response": resp}


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica todos os projetos no Mercado Livre")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem publicar de verdade")
    args = parser.parse_args()

    print("=" * 60)
    print("🚀 PUBLISH ALL — EuAchei3D / Mercado Livre")
    print(f"   Preço: R$ {PRICE_BRL:.2f} | Estoque mínimo: {STOCK} unidades")
    print(f"   Categoria: {CATEGORY_ID} (Chaveiros)")
    if args.dry_run:
        print("   ⚠️  MODO DRY-RUN — nenhum produto será publicado de verdade")
    print("=" * 60)

    token = login()
    fix_store_category(token, dry_run=args.dry_run)
    projects = list_projects(token)

    ok, skipped, failed = 0, 0, 0
    results = []

    print()
    for project in projects:
        pid = project.get("id", "?")
        name = project.get("name") or pid
        status = project.get("status", "?")

        if status not in ("completed", "uploaded"):
            print(f"⏭️  SKIP  {name} (status={status})")
            skipped += 1
            continue

        print(f"📤 Publicando: {name} ({pid}) ...", end=" ", flush=True)
        result = publish_project(token, pid, name, dry_run=args.dry_run)
        http_status = result.get("http_status", 0)
        resp = result.get("response", {})

        if args.dry_run:
            print("✅ dry-run")
            ok += 1
        elif http_status in (200, 201):
            ml_id = resp.get("marketplace_item_id") or resp.get("id") or ""
            print(f"✅ OK (ML id: {ml_id})")
            ok += 1
        else:
            error_detail = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)[:200]
            print(f"❌ ERRO {http_status}: {error_detail}")
            failed += 1

        results.append({"project_id": pid, "name": name, "http_status": http_status, "response": resp})
        time.sleep(1.2)   # respeitar rate limit do ML

    print("\n" + "=" * 60)
    print(f"✅ Publicados: {ok}  |  ⏭️  Pulados: {skipped}  |  ❌ Erros: {failed}")
    print("=" * 60)

    if failed:
        print("\nDetalhes dos erros:")
        for r in results:
            if r.get("http_status") not in (200, 201, 0):
                print(f"  • {r['name']}: HTTP {r['http_status']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
