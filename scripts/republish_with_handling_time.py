#!/usr/bin/env python3
"""Recria um anúncio do Mercado Livre com handling_time=0 (envio no mesmo dia).

O campo handling_time NÃO pode ser editado em itens existentes — é necessário
fechar o item atual e publicar um novo com o campo correto.

Uso:
    python scripts/republish_with_handling_time.py --item MLB4652361417 --project deadpool-keych-ams-version_v001
    python scripts/republish_with_handling_time.py --item MLB4652361417 --project deadpool-keych-ams-version_v001 --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = "https://app.euachei3d.com.br/api/v1"
STORE_ID = "1b2536a86e4044b5a1accafb926128a5"
USERNAME = "rodrigogrosa"
PASSWORD = "Violao2021@"


def _request(url: str, method: str = "GET", body: bytes | None = None, headers: dict | None = None) -> dict:
    req = Request(url, data=body, method=method, headers=headers or {})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        print(f"[ERRO {exc.code}] {url}\n{detail[:800]}", file=sys.stderr)
        raise


def login() -> str:
    body = json.dumps({"username": USERNAME, "password": PASSWORD}).encode()
    data = _request(f"{BASE_URL}/auth/login", method="POST", body=body,
                    headers={"Content-Type": "application/json"})
    return data["access_token"]


def get_ml_token(bearer: str) -> str:
    data = _request(f"{BASE_URL}/stores/{STORE_ID}/ml-token",
                    headers={"Authorization": f"Bearer {bearer}"})
    return data["access_token"]


def get_item(ml_token: str, item_id: str) -> dict:
    return _request(f"https://api.mercadolibre.com/items/{item_id}?include_attributes=all",
                    headers={"Authorization": f"Bearer {ml_token}"})


def upload_picture(ml_token: str, image_path: str) -> str:
    """Faz upload de uma imagem e retorna o picture_id."""
    import mimetypes
    import uuid
    from email.generator import BytesGenerator
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders
    import io

    mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    data = Path(image_path).read_bytes()

    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{Path(image_path).name}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()

    req = Request(
        "https://api.mercadolibre.com/pictures/items/upload",
        data=body, method="POST",
        headers={
            "Authorization": f"Bearer {ml_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
    return result["id"]


def find_local_images(project_slug: str) -> list[str]:
    """Encontra imagens ml_ready_*.jpg ou *.jpg do projeto."""
    storage_root = Path.home() / "Downloads" / "Projetos3d" / "SnapMaker3d"
    project_dir = storage_root / project_slug
    if not project_dir.exists():
        return []
    images = sorted(project_dir.glob("ml_ready_*.jpg"))
    if not images:
        images = sorted(project_dir.glob("*.jpg"))[:8]
    return [str(p) for p in images[:8]]


def close_item(ml_token: str, item_id: str) -> None:
    body = json.dumps({"status": "closed"}).encode()
    _request(f"https://api.mercadolibre.com/items/{item_id}",
             method="PUT", body=body,
             headers={"Authorization": f"Bearer {ml_token}", "Content-Type": "application/json"})
    print(f"[OK] Item {item_id} fechado.")


def create_item(ml_token: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    return _request("https://api.mercadolibre.com/items",
                    method="POST", body=body,
                    headers={"Authorization": f"Bearer {ml_token}", "Content-Type": "application/json"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Recria anúncio ML com handling_time=0")
    parser.add_argument("--item", required=True, help="Item ID a ser recriado (ex: MLB4652361417)")
    parser.add_argument("--project", required=True, help="Slug do projeto para encontrar imagens locais")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem publicar nem fechar")
    args = parser.parse_args()

    print(f"[INFO] Login...")
    bearer = login()
    ml_token = get_ml_token(bearer)

    print(f"[INFO] Buscando item {args.item}...")
    item = get_item(ml_token, args.item)
    print(f"[INFO] Título: {item['title']}")
    print(f"[INFO] handling_time atual: {item.get('shipping', {}).get('handling_time')}")
    print(f"[INFO] Status atual: {item.get('status')}")

    # Buscar imagens locais do projeto
    local_images = find_local_images(args.project)
    print(f"[INFO] Imagens locais encontradas: {len(local_images)}")

    # Fazer upload das imagens
    picture_ids: list[str] = []
    if local_images:
        for img_path in local_images:
            if args.dry_run:
                print(f"[DRY-RUN] Faria upload: {img_path}")
            else:
                print(f"[INFO] Uploading {Path(img_path).name}...")
                pid = upload_picture(ml_token, img_path)
                picture_ids.append(pid)
                print(f"  -> {pid}")
    else:
        # Reusa as pictures do item existente
        picture_ids = [p.get("id") or p.get("source", "") for p in item.get("pictures", [])]
        picture_ids = [p for p in picture_ids if p]
        print(f"[INFO] Reutilizando {len(picture_ids)} imagens do item existente")

    # Montar novo payload idêntico ao original + handling_time=0
    variations = item.get("variations", [])
    new_variations = []
    for v in variations:
        new_v = {
            "price": round(float(item["price"]), 2),  # garante preço igual
            "available_quantity": v.get("available_quantity", 1),
            "seller_custom_field": v.get("seller_custom_field") or "",
            "attribute_combinations": v.get("attribute_combinations", []),
        }
        if picture_ids:
            new_v["picture_ids"] = picture_ids
        new_variations.append(new_v)

    new_payload: dict = {
        "title": item["title"],
        "category_id": item["category_id"],
        "price": round(float(item["price"]), 2),
        "currency_id": item.get("currency_id", "BRL"),
        "available_quantity": item.get("available_quantity", 1),
        "buying_mode": item.get("buying_mode", "buy_it_now"),
        "condition": item.get("condition", "new"),
        "listing_type_id": item.get("listing_type_id", "gold_special"),
        "shipping": {
            "mode": "me2",
            "local_pick_up": False,
            "free_shipping": True,
            "logistic_type": "drop_off",
            "handling_time": 0,  # envio no mesmo dia (pedidos até ~12h)
        },
        "pictures": [{"id": pid} for pid in picture_ids] if picture_ids else [],
        "sale_terms": [
            {"id": "WARRANTY_TYPE", "value_name": "Garantia do vendedor"},
            {"id": "WARRANTY_TIME", "value_name": "1 meses"},
        ],
        "attributes": [
            {"id": a["id"], "value_name": a.get("value_name")}
            for a in item.get("attributes", [])
            if a.get("value_name") and a["id"] not in {"COLOR"}
        ],
    }
    if new_variations:
        new_payload["variations"] = new_variations
        new_payload["available_quantity"] = sum(v.get("available_quantity", 1) for v in new_variations)

    if args.dry_run:
        print("\n[DRY-RUN] Payload que seria publicado:")
        print(json.dumps(new_payload, indent=2, ensure_ascii=False))
        print(f"\n[DRY-RUN] Item {args.item} NÃO foi fechado.")
        return

    print(f"\n[ATENÇÃO] Isso vai:")
    print(f"  1. Fechar o item atual: {args.item}")
    print(f"  2. Publicar novo item com handling_time=0 (envio no mesmo dia)")
    print(f"  A URL/ID do produto vai MUDAR.")
    resp = input("Confirmar? (s/N): ").strip().lower()
    if resp != "s":
        print("Cancelado.")
        return

    # 1. Fechar item atual
    close_item(ml_token, args.item)

    # 2. Publicar novo item
    print("[INFO] Publicando novo item...")
    created = create_item(ml_token, new_payload)
    new_id = created.get("id")
    print(f"\n[SUCESSO] Novo item publicado!")
    print(f"  ID:  {new_id}")
    print(f"  URL: https://produto.mercadolivre.com.br/{new_id.replace('MLB', 'MLB-')}")
    print(f"  handling_time: {created.get('shipping', {}).get('handling_time')}")

    # 3. Adicionar descrição se disponível
    # (a descrição não é copiada automaticamente pela API)
    print("\n[INFO] Para copiar a descrição, edite manualmente no Mercado Livre.")


if __name__ == "__main__":
    main()
