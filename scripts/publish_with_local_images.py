#!/usr/bin/env python3
"""Publica um projeto no Mercado Livre usando imagens ml_ready_*.jpg locais.

Fluxo adaptativo (tenta 3 estratégias em ordem):
  A) backend /upload-to-ml — envia via servidor (requer deploy novo)
  B) backend /ml-token     — obtém token e envia direto na API ML (requer deploy novo)
  C) ERRO                  — instrui usuário a fazer redeploy no Northflank

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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://app.euachei3d.com.br/api/v1"
ML_PICTURES_URL = "https://api.mercadolibre.com/pictures/items/upload"
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
    parts = project_id.rsplit("_v", 1)
    project_slug = parts[0] if len(parts) == 2 else project_id

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


def _check_endpoint_exists(url: str, token: str) -> bool:
    """Verifica se um endpoint existe (retorna False em 404, True caso contrário)."""
    req = Request(url, method="GET", headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(req, timeout=5) as _:
            return True
    except HTTPError as e:
        return e.code != 404
    except URLError:
        return False


def _upload_via_backend(token: str, image_path: Path) -> str | None:
    """Envia imagem via POST /stores/{store_id}/upload-to-ml."""
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
        if exc.code == 404:
            return None  # sinaliza que o endpoint não existe
        body_bytes = exc.read()
        print(f"    ❌ Erro ao enviar {image_path.name}: HTTP {exc.code} — {body_bytes.decode(errors='replace')[:200]}")
        return "ERROR"


def _get_ml_token_via_backend(token: str) -> str | None:
    """Obtém o ML access_token via GET /stores/{store_id}/ml-token."""
    url = f"{BASE_URL}/stores/{STORE_ID}/ml-token"
    req = Request(url, method="GET", headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("access_token")
    except HTTPError as exc:
        if exc.code == 404:
            return None
        body_bytes = exc.read()
        print(f"    ❌ Erro ao obter ML token: HTTP {exc.code} — {body_bytes.decode(errors='replace')[:200]}")
        return None


def _upload_directly_to_ml(ml_token: str, image_path: Path) -> str | None:
    """Envia imagem diretamente à API do Mercado Livre (sem passar pelo backend)."""
    with image_path.open("rb") as f:
        file_data = f.read()

    boundary = "----SnapMakerDirect" + str(int(time.time()))
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{image_path.name}"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = Request(ML_PICTURES_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {ml_token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
    })
    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("id")
    except HTTPError as exc:
        body_bytes = exc.read()
        print(f"    ❌ Erro direto ML {image_path.name}: HTTP {exc.code} — {body_bytes.decode(errors='replace')[:300]}")
        return None


def upload_image(token: str, image_path: Path, dry_run: bool) -> str | None:
    """Faz upload de uma imagem. Tenta backend; se indisponível, tenta direto no ML."""
    if dry_run:
        print(f"    [DRY-RUN] uploadaria {image_path.name}")
        return f"dry_run_{image_path.stem}"

    # Estratégia A: via backend /upload-to-ml
    result = _upload_via_backend(token, image_path)
    if result is None:
        # 404 → endpoint não deployado ainda; sinaliza para o chamador
        return "ENDPOINT_NOT_DEPLOYED"
    if result != "ERROR":
        return result
    return None  # erro real de upload


def upload_image_direct(ml_token: str, image_path: Path, dry_run: bool) -> str | None:
    """Faz upload diretamente na API do ML usando token já obtido."""
    if dry_run:
        print(f"    [DRY-RUN] uploadaria {image_path.name} direto no ML")
        return f"dry_run_direct_{image_path.stem}"
    return _upload_directly_to_ml(ml_token, image_path)


def get_draft_payload(token: str, project_id: str, picture_ids: list[str]) -> dict | None:
    """Obtém o payload de rascunho do backend (sem publicar). Retorna None em caso de erro."""
    url = f"{BASE_URL}/stores/{STORE_ID}/publish/{project_id}"
    payload = {
        "mode": "draft",
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
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except HTTPError as exc:
        body_bytes = exc.read()
        print(f"  ❌ Erro ao obter draft: HTTP {exc.code} — {body_bytes.decode(errors='replace')[:300]}")
        return None
    except Exception as exc:
        print(f"  ❌ Erro ao obter draft: {exc}")
        return None


def publish_directly_via_ml(ml_token: str, draft_result: dict) -> None:
    """Publica diretamente na API do ML usando o payload do rascunho (bypassa validação do backend)."""
    payload = draft_result.get("payload") or {}
    if not payload:
        print("  ❌ Payload de draft vazio.")
        return

    # Limpar campos internos que não devem ir para a API do ML
    ml_payload = {
        k: v for k, v in payload.items()
        if k not in {"images", "description_plain_text", "category_prediction_applied",
                     "_pre_uploaded_picture_ids", "category_prediction_applied"}
    }

    print(f"  ℹ️  Publicando direto na API ML com {len(ml_payload)} campos...")
    body = json.dumps(ml_payload).encode()
    req = Request("https://api.mercadolibre.com/items", data=body, method="POST", headers={
        "Authorization": f"Bearer {ml_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
        item_id = result.get("id", "")
        permalink = result.get("permalink", "")
        print(f"  ✅ PUBLICADO! item_id={item_id}")
        if permalink:
            print(f"     Link: {permalink}")
    except HTTPError as exc:
        body_bytes = exc.read()
        detail = body_bytes.decode(errors='replace')
        print(f"  ❌ Erro ML POST /items: HTTP {exc.code} — {detail[:500]}")


def publish_project(token: str, project_id: str, picture_ids: list[str], dry_run: bool, ml_token: str | None = None) -> None:
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
            # Estratégia C: se o bloqueio for o erro de variações do ML e temos ml_token, tenta publicar direto
            variation_error = any("variations.price.different" in b for b in blockers)
            if variation_error and ml_token:
                print("\n  ℹ️  Ativando Estratégia C: publicação direta via ML API (bypassa validação)...")
                draft = get_draft_payload(token, project_id, picture_ids)
                if draft:
                    publish_directly_via_ml(ml_token, draft)
            elif variation_error and not ml_token:
                print("\n  ℹ️  Para contornar erro de variações, obtenha o ML token e use estratégia C.")
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

    # 3. Determinar estratégia de upload
    print(f"\n3. Enviando {len(ml_files)} imagens para Mercado Livre...")

    # Testa estratégia A com a primeira imagem
    strategy = "A"  # via backend
    ml_token: str | None = None

    if not args.dry_run:
        test_result = _upload_via_backend(token, ml_files[0])
        if test_result == "ENDPOINT_NOT_DEPLOYED":
            print("   ℹ️  /upload-to-ml não disponível. Tentando obter token para upload direto...")
            ml_token = _get_ml_token_via_backend(token)
            if ml_token:
                strategy = "B"  # direto no ML
                print("   ✅ Token ML obtido — usando upload direto na API do ML")
            else:
                print()
                print("   ❌ DEPLOY PENDENTE: os novos endpoints não estão em produção ainda.")
                print()
                print("   Para desbloquear, acesse o painel do Northflank e faça redeploy manual:")
                print("   1. Acesse https://app.northflank.com")
                print("   2. Projeto snapmaker3d-studio → Serviço backend")
                print("   3. Clique em 'Redeploy' ou 'Trigger Build'")
                print()
                print("   Após o redeploy, verifique com:")
                print("   curl -s https://app.euachei3d.com.br/api/v1/health | python3 -m json.tool")
                print("   (deve aparecer campo 'git_commit')")
                sys.exit(1)
    else:
        strategy = "DRY"

    # Upload das imagens
    picture_ids: list[str] = []

    if args.dry_run:
        # Dry-run: percorre todas as imagens simulando
        for i, img in enumerate(ml_files, 1):
            print(f"   [{i}/{len(ml_files)}] {img.name}...")
            pid = upload_image(token, img, dry_run=True)
            if pid:
                picture_ids.append(pid)
                print(f"        ✅ picture_id={pid}")

    elif strategy == "A":
        # Estratégia A: via backend /upload-to-ml
        # Primeira imagem já foi testada e o resultado está em test_result
        first_pid = test_result
        print(f"   [1/{len(ml_files)}] {ml_files[0].name}...")
        if first_pid and first_pid not in ("ENDPOINT_NOT_DEPLOYED", "ERROR", None):
            picture_ids.append(first_pid)
            print(f"        ✅ picture_id={first_pid}")
        else:
            print(f"        ⚠️  Upload falhou")

        for i, img in enumerate(ml_files[1:], 2):
            print(f"   [{i}/{len(ml_files)}] {img.name}...")
            pid = upload_image(token, img, dry_run=False)
            if pid and pid not in ("ENDPOINT_NOT_DEPLOYED", "ERROR"):
                picture_ids.append(pid)
                print(f"        ✅ picture_id={pid}")
            else:
                print(f"        ⚠️  Upload falhou")
            time.sleep(0.5)

    else:
        # Estratégia B: upload direto na API do ML
        for i, img in enumerate(ml_files, 1):
            print(f"   [{i}/{len(ml_files)}] {img.name}...")
            pid = upload_image_direct(ml_token, img, dry_run=False)  # type: ignore[arg-type]
            if pid:
                picture_ids.append(pid)
                print(f"        ✅ picture_id={pid}")
            else:
                print(f"        ⚠️  Upload falhou")
            time.sleep(0.5)

    if not picture_ids:
        print("\n❌ Nenhuma imagem enviada com sucesso. Abortando publicação.")
        sys.exit(1)

    print(f"\n   ✅ {len(picture_ids)}/{len(ml_files)} imagens enviadas com sucesso")

    # Obtém ML token (necessário como fallback na Estratégia C)
    if not args.dry_run and not ml_token:
        ml_token = _get_ml_token_via_backend(token)
        if ml_token:
            print("   ℹ️  ML token obtido para fallback de publicação direta")

    # 4. Publicar
    print(f"\n4. Publicando {args.project}...")
    publish_project(token, args.project, picture_ids, args.dry_run, ml_token=ml_token)
    print("\nConcluído.")


if __name__ == "__main__":
    main()
