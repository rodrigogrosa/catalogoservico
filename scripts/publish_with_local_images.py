#!/usr/bin/env python3
"""Publica um projeto no Mercado Livre usando imagens ml_ready_*.jpg locais.

Fluxo:
  1. Autentica no backend
  2. Lê os arquivos ml_ready_*.jpg da storage local
  3. Faz upload de cada imagem via POST /stores/{store_id}/upload-to-ml
  4. Publica o projeto com os picture IDs pré-enviados

Uso:
    python scripts/publish_with_local_images.py --project deadpool-keych-ams-version_v001
    python scripts/publish_with_local_images.py --project deadpool-keych-ams-version_v001 --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = "https://app.euachei3d.com.br/api/v1"
STORE_ID = "1b2536a86e4044b5a1accafb926128a5"
USERNAME = "rodrigogrosa"
PASSWORD = "Violao2021@"
PRICE_BRL = 80.0
STOCK = 10

# Storage local onde ficam os projetos
LOCAL_STORAGE = Path.home() / "Downloads/Projetos3d/SnapMaker3d"


def login() -> str:
    body = json.dumps({"username": USERNAME, "password": PASSWORD}).encode()
    req = Request(f"{BASE_URL}/auth/login", data=body, method="POST",
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["access_token"]


def find_ml_ready_images(project_id: str) -> list[Path]:
    """Localiza arquivos ml_ready_*.jpg na storage local para o projeto."""
    # Extrai o nome base do projeto (sem versão) para encontrar a pasta
    # Ex: deadpool-keych-ams-version_v001 → deadpool-keych-ams-version
    parts = project_id.rsplit("_v", 1)
    project_slug = parts[0] if len(parts) == 2 else project_id

    # Tenta caminhos possíveis
    candidates = [
        LOCAL_STORAGE / project_slug / project_id / "previews",
        LOCAL_STORAGE / project_id / "previews",
        LOCAL_STORAGE / project_slug / "previews",
    ]
    preview_dir: Path | None = None
    for path in candidates:
        if path.exists():
            preview_dir = path
            break

    if preview_dir is None:
        print(f"  ⚠️  Pasta de previews não encontrada para {project_id}")
        print(f"     Tentativas: {[str(c) for c in candidates]}")
        return []

    ml_files = sorted(preview_dir.glob("ml_ready_*.jpg"))
    if not ml_files:
        print(f"  ⚠️  Nenhum ml_ready_*.jpg encontrado em {preview_dir}")
    return ml_files[:8]  # ML aceita no máximo 8 imagens por anúncio


def upload_image(token: str, image_path: Path, dry_run: bool) -> str | None:
    """Faz upload de uma imagem para o ML via backend. Retorna o picture ID."""
    if dry_run:
        print(f"    [DRY-RUN] uploadaria {image_path.name}")
        return f"dry_run_{image_path.stem}"

    url = f"{BASE_URL}/stores/{STORE_ID}/upload-to-ml"
    with image_path.open("rb") as f:
        file_data = f.read()

    boundary = "----SnapMakerScript" + str(int(time.time()))
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{image_path.name}"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("id")
    except HTTPError as exc:
        body_bytes = exc.read()
        print(f"    ❌ Erro ao enviar {image_path.name}: HTTP {exc.code} — {body_bytes.decode(errors='replace')[:200]}")
        return None


def publish_project(token: str, project_id: str, picture_ids: list[str], dry_run: bool) -> None:
    if dry_run:
        print(f"  [DRY-RUN] publicaria {project_id} com picture_ids={picture_ids}")
        return

    url = f"{BASE_URL}/stores/{STORE_ID}/publish/{project_id}"
    payload = {
        "mode": "publish",
        "stock": STOCK,
        "price_override_brl": PRICE_BRL,
        "pre_uploaded_picture_ids": picture_ids,
    }
    body = json.dumps(payload).encode()
    req = Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
        status = result.get("status")
        item_id = result.get("published_item_id", "")
        permalink = result.get("published_permalink", "")
        if status == "published":
            print(f"  ✅ Publicado! item_id={item_id}")
            if permalink:
                print(f"     Link: {permalink}")
        else:
            blockers = result.get("blockers", [])
            print(f"  ⚠️  Status: {status}")
            for b in blockers:
                print(f"     ⛔ {b}")
    except HTTPError as exc:
        body_bytes = exc.read()
        print(f"  ❌ Erro ao publicar: HTTP {exc.code} — {body_bytes.decode(errors='replace')[:400]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica projeto no ML com imagens locais ml_ready_*.jpg")
    parser.add_argument("--project", required=True, help="ID do projeto (ex: deadpool-keych-ams-version_v001)")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem publicar")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"Projeto: {args.project}")
    print(f"Modo: {'DRY-RUN' if args.dry_run else 'PRODUÇÃO'}")
    print("="*60)

    # 1. Login
    print("\n1. Autenticando...")
    try:
        token = login()
        print("   ✅ Token obtido")
    except Exception as exc:
        print(f"   ❌ Falha no login: {exc}")
        sys.exit(1)

    # 2. Localizar imagens locais
    print(f"\n2. Localizando ml_ready_*.jpg para {args.project}...")
    ml_files = find_ml_ready_images(args.project)
    if not ml_files:
        print("   ❌ Nenhuma imagem ml_ready encontrada. Não é possível publicar.")
        sys.exit(1)
    print(f"   ✅ {len(ml_files)} imagens encontradas:")
    for f in ml_files:
        size_kb = f.stat().st_size // 1024
        print(f"      {f.name} ({size_kb}KB)")

    # 3. Upload das imagens para ML
    print(f"\n3. Enviando {len(ml_files)} imagens para Mercado Livre...")
    picture_ids: list[str] = []
    for i, img in enumerate(ml_files, 1):
        print(f"   [{i}/{len(ml_files)}] {img.name}...")
        pid = upload_image(token, img, args.dry_run)
        if pid:
            picture_ids.append(pid)
            print(f"        ✅ picture_id={pid}")
        else:
            print(f"        ⚠️  Ignorando — upload falhou")
        if not args.dry_run:
            time.sleep(0.5)  # evita rate-limit

    if not picture_ids:
        print("\n❌ Nenhuma imagem enviada com sucesso. Abortando publicação.")
        sys.exit(1)

    print(f"\n   ✅ {len(picture_ids)}/{len(ml_files)} imagens enviadas com sucesso")

    # 4. Publicar
    print(f"\n4. Publicando {args.project}...")
    publish_project(token, args.project, picture_ids, args.dry_run)
    print("\nConcluído.")


if __name__ == "__main__":
    main()
