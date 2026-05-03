from io import BytesIO
from pathlib import Path
import sys
from urllib.error import HTTPError

import pytest


import app.services.store_service as store_service_module
from app.services.store_service import StoreService


from io import BytesIO
from pathlib import Path
import sys
from urllib.error import HTTPError

import pytest


import app.services.store_service as store_service_module
from app.services.store_service import StoreService


def build_http_error(body: str, status: int = 400) -> HTTPError:
    return HTTPError(
        url="https://api.mercadolibre.com/items/validate",
        code=status,
        msg="Validation error",
        hdrs=None,
        fp=BytesIO(body.encode("utf-8")),
    )


# ---------------------------------------------------------------------------
# Helper: fake store, project, request stubs used across publish tests
# ---------------------------------------------------------------------------

def _make_fake_store(settings: dict | None = None) -> dict:
    return {
        "id": "store-1",
        "owner_username": "u",
        "marketplace": "mercado_livre",
        "credentials": {"access_token": "tok"},
        "settings": settings or {},
        "name": "Loja Teste",
    }


def _make_fake_project(tmp_path: Path, *, variations: list | None = None, warranty: dict | None = None) -> dict:
    img = tmp_path / "preview.jpg"
    img.write_bytes(b"FAKEJPEG")
    return {
        "id": "proj-1",
        "name": "Chaveiro Homem De Ferro",
        "preview_url": str(img),
        "previews": [{"label": "preview.jpg", "path": str(img), "kind": "preview"}],
        "sales_profile": {
            "suggested_price_50_margin_brl": 29.90,
            "marketplace_attributes": [
                {
                    "marketplace": "Mercado Livre",
                    "title": "Chaveiro Homem De Ferro Impresso Em 3D",
                    "full_description": "Chaveiro impresso em 3D.",
                }
            ],
            "variations": variations or [],
            "warranty": warranty or {"type": "seller", "duration": 1, "unit": "months"},
        },
    }


class _FakePublishRequest:
    price_override_brl = None
    stock = 50
    mode = "publish"
    image_base_url = None
    product_url = None


# ---------------------------------------------------------------------------
# publish_mercado_livre_item — payload correctness tests
# ---------------------------------------------------------------------------

def test_publish_includes_variations_in_item_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """variations must be forwarded to ML — they were previously stripped by the item_payload filter."""
    service = StoreService()
    project = _make_fake_project(
        tmp_path,
        variations=[{"sku": "SKU-KIT10", "name": "Kit 10 unidades", "stock": 320, "price_brl": 269.10, "quantity": 10}],
    )
    store = _make_fake_store()

    monkeypatch.setattr(service, "mercado_livre_validate_item", lambda token, payload: {})
    monkeypatch.setattr(service, "resolve_local_product_images", lambda p: [])
    monkeypatch.setattr(service, "upload_local_mercado_livre_pictures", lambda tok, paths: [{"id": "PIC1"}])

    sent_payloads: list[dict] = []

    def fake_api_request(*, access_token, method, path, payload=None):
        sent_payloads.append({"path": path, "payload": payload})
        return {"id": "MLB99", "permalink": "https://mercadolivre.com/MLB99"}

    monkeypatch.setattr(service, "mercado_livre_api_request", fake_api_request)
    monkeypatch.setattr(service, "build_payload_for_marketplace", lambda connector, store_, project_, req: {
        "title": "Chaveiro Homem De Ferro",
        "category_id": "MLB186814",
        "price": 29.90,
        "available_quantity": 50,
        "currency_id": "BRL",
        "buying_mode": "buy_it_now",
        "condition": "new",
        "listing_type_id": "gold_special",
        "pictures": [{"id": "PIC1"}],
        "sale_terms": [{"id": "WARRANTY_TYPE", "value_name": "Garantia do vendedor"}, {"id": "WARRANTY_TIME", "value_name": "1 meses"}],
        "attributes": [],
        "description_plain_text": "Chaveiro impresso em 3D.",
        "variations": [{"price": 269.10, "available_quantity": 320, "seller_custom_field": "SKU-KIT10", "attribute_combinations": [{"id": "COLOR", "value_name": "Kit 10 unidades"}]}],
    })

    service.publish_mercado_livre_item(store, service.build_payload_for_marketplace(None, store, project, _FakePublishRequest()), project)  # type: ignore[arg-type]

    item_post = next(p for p in sent_payloads if p["path"] == "/items")
    assert "variations" in item_post["payload"], "variations deve estar no payload enviado ao ML"
    assert item_post["payload"]["variations"][0]["seller_custom_field"] == "SKU-KIT10"


def test_publish_sends_warranty_sale_terms(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """sale_terms must be built from sales_profile.warranty, not from empty store.settings.sale_terms."""
    service = StoreService()
    project = _make_fake_project(tmp_path, warranty={"type": "seller", "duration": 1, "unit": "months"})
    store = _make_fake_store()  # no sale_terms in settings

    product_payload = {
        "title": "T",
        "category_id": "MLB1",
        "price": 10.0,
        "available_quantity": 10,
        "currency_id": "BRL",
        "buying_mode": "buy_it_now",
        "condition": "new",
        "listing_type_id": "gold_special",
        "pictures": [{"id": "PIC1"}],
        "sale_terms": [
            {"id": "WARRANTY_TYPE", "value_name": "Garantia do vendedor"},
            {"id": "WARRANTY_TIME", "value_name": "1 meses"},
        ],
        "attributes": [],
        "description_plain_text": "Desc",
    }

    monkeypatch.setattr(service, "mercado_livre_validate_item", lambda tok, p: {})
    monkeypatch.setattr(service, "resolve_local_product_images", lambda p: [])

    sent: list[dict] = []

    def fake_api(*, access_token, method, path, payload=None):
        sent.append({"path": path, "payload": payload})
        return {"id": "MLB1"}

    monkeypatch.setattr(service, "mercado_livre_api_request", fake_api)

    service.publish_mercado_livre_item(store, product_payload, project)

    item_post = next(p for p in sent if p["path"] == "/items")
    terms = {t["id"]: t["value_name"] for t in (item_post["payload"].get("sale_terms") or [])}
    assert terms.get("WARRANTY_TYPE") == "Garantia do vendedor", "WARRANTY_TYPE deve estar no payload"
    assert terms.get("WARRANTY_TIME") == "1 meses", "WARRANTY_TIME deve estar no payload"


def test_publish_uploads_local_files_instead_of_source_urls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Local files must be uploaded to ML (not passed as source URLs) so ML servers can access them."""
    service = StoreService()
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"FAKEJPEG")
    project = {"id": "p1", "name": "Produto", "preview_url": None, "previews": [], "sales_profile": {}}

    product_payload = {
        "title": "T", "category_id": "MLB1", "price": 10.0, "available_quantity": 10,
        "currency_id": "BRL", "buying_mode": "buy_it_now", "condition": "new",
        "listing_type_id": "gold_special", "pictures": [{"source": "https://api.euachei3d.com.br/photo.jpg"}],
        "sale_terms": [], "attributes": [], "description_plain_text": "",
    }

    monkeypatch.setattr(service, "resolve_local_product_images", lambda p: [str(img)])
    upload_called_with: list[list[str]] = []

    def fake_upload(tok, paths):
        upload_called_with.append(paths)
        return [{"id": "ML_PIC_1"}]

    monkeypatch.setattr(service, "upload_local_mercado_livre_pictures", fake_upload)
    monkeypatch.setattr(service, "mercado_livre_validate_item", lambda tok, p: {})

    sent: list[dict] = []

    def fake_api(*, access_token, method, path, payload=None):
        sent.append({"path": path, "payload": payload})
        return {"id": "MLB1"}

    monkeypatch.setattr(service, "mercado_livre_api_request", fake_api)

    service.publish_mercado_livre_item(_make_fake_store(), product_payload, project)

    assert upload_called_with, "upload_local_mercado_livre_pictures deve ser chamado"
    item_post = next(p for p in sent if p["path"] == "/items")
    pictures = item_post["payload"].get("pictures", [])
    assert all("id" in pic for pic in pictures), "fotos devem ter id ML, não source URL"
    assert all("source" not in pic for pic in pictures), "source URLs não devem ser enviadas ao ML"


def test_resolve_local_product_images_resolves_storage_url_paths(tmp_path: Path) -> None:
    """Paths stored as /storage/... must be resolved against storage_root, not treated as
    absolute filesystem paths — otherwise resolve_local_product_images always returns []
    in production (root cause of the ML variation picture_ids bug)."""
    import app.core.config as cfg_module

    # Create a fake image at {tmp_path}/projects/p1/previews/photo.jpg
    previews_dir = tmp_path / "projects" / "p1" / "previews"
    previews_dir.mkdir(parents=True)
    img = previews_dir / "photo.jpg"
    img.write_bytes(b"FAKEJPEG")

    service = StoreService()
    # Patch storage_root to tmp_path so the service resolves paths correctly
    original_storage_root = service.settings.__class__.storage_root.fget  # type: ignore[attr-defined]
    service.settings.__class__.storage_root = property(lambda self: tmp_path)  # type: ignore[attr-defined]
    try:
        project = {
            "id": "p1",
            "name": "Test",
            "preview_url": None,
            "previews": [
                # URL-relative path as stored by preview_service._artifact
                {"label": "photo.jpg", "path": "/storage/projects/p1/previews/photo.jpg", "kind": "preview"}
            ],
            "sales_profile": {},
        }
        result = service.resolve_local_product_images(project)
        assert result, "deve encontrar a imagem resolvendo /storage/ contra storage_root"
        assert str(img) in result, f"caminho esperado {img} não está em {result}"
    finally:
        service.settings.__class__.storage_root = property(original_storage_root)  # type: ignore[attr-defined]


def test_publish_variations_receive_picture_ids(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Each variation must have picture_ids — otherwise ML returns item.pictures.variation.quantity error."""
    service = StoreService()
    project = _make_fake_project(tmp_path)
    store = _make_fake_store()

    product_payload = {
        "title": "T", "category_id": "MLB439316", "price": 29.90, "available_quantity": 50,
        "currency_id": "BRL", "buying_mode": "buy_it_now", "condition": "new",
        "listing_type_id": "gold_special", "pictures": [],
        "sale_terms": [{"id": "WARRANTY_TYPE", "value_name": "Garantia do vendedor"}],
        "attributes": [], "description_plain_text": "Desc",
        "variations": [
            {"price": 269.10, "available_quantity": 320, "seller_custom_field": "SKU-KIT10",
             "attribute_combinations": [{"id": "COLOR", "value_name": "Kit 10 unidades"}]},
        ],
    }

    monkeypatch.setattr(service, "resolve_local_product_images", lambda p: [str(tmp_path / "photo.jpg")])
    monkeypatch.setattr(service, "upload_local_mercado_livre_pictures", lambda tok, paths: [{"id": "ML_P1"}, {"id": "ML_P2"}])
    monkeypatch.setattr(service, "mercado_livre_validate_item", lambda tok, p: {})

    sent: list[dict] = []

    def fake_api(*, access_token, method, path, payload=None):
        sent.append({"path": path, "payload": payload})
        return {"id": "MLB1"}

    monkeypatch.setattr(service, "mercado_livre_api_request", fake_api)

    service.publish_mercado_livre_item(store, product_payload, project)

    item_post = next(p for p in sent if p["path"] == "/items")
    for var in item_post["payload"].get("variations", []):
        assert "picture_ids" in var, "cada variação deve ter picture_ids"
        assert var["picture_ids"] == ["ML_P1", "ML_P2"], "picture_ids deve conter todos os IDs uploadados"


def test_publish_variations_receive_picture_ids_from_source_url_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When no local files exist but payload has source-URL pictures, they must be downloaded
    and uploaded to ML so that variations get picture_ids (fixes item.pictures.variation.quantity)."""
    service = StoreService()
    project = _make_fake_project(tmp_path)
    store = _make_fake_store()

    product_payload = {
        "title": "T", "category_id": "MLB439316", "price": 29.90, "available_quantity": 50,
        "currency_id": "BRL", "buying_mode": "buy_it_now", "condition": "new",
        "listing_type_id": "gold_special",
        "pictures": [{"source": "https://api.euachei3d.com.br/previews/p1/photo.jpg"}],
        "sale_terms": [{"id": "WARRANTY_TYPE", "value_name": "Garantia do vendedor"}],
        "attributes": [], "description_plain_text": "Desc",
        "variations": [
            {"price": 29.90, "available_quantity": 10, "seller_custom_field": "SKU-1",
             "attribute_combinations": [{"id": "COLOR", "value_name": "Azul"}]},
        ],
    }

    # No local files — fallback to source-URL download path
    monkeypatch.setattr(service, "resolve_local_product_images", lambda p: [])
    upload_from_urls_called_with: list[list[str]] = []

    def fake_upload_from_urls(tok, urls):
        upload_from_urls_called_with.append(urls)
        return [{"id": "ML_FROM_URL_1"}]

    monkeypatch.setattr(service, "_upload_pictures_from_urls", fake_upload_from_urls)
    monkeypatch.setattr(service, "mercado_livre_validate_item", lambda tok, p: {})

    sent: list[dict] = []

    def fake_api(*, access_token, method, path, payload=None):
        sent.append({"path": path, "payload": payload})
        return {"id": "MLB99"}

    monkeypatch.setattr(service, "mercado_livre_api_request", fake_api)

    service.publish_mercado_livre_item(store, product_payload, project)

    assert upload_from_urls_called_with, "_upload_pictures_from_urls deve ser chamado quando só há source URLs"
    assert upload_from_urls_called_with[0] == ["https://api.euachei3d.com.br/previews/p1/photo.jpg"]
    item_post = next(p for p in sent if p["path"] == "/items")
    for var in item_post["payload"].get("variations", []):
        assert "picture_ids" in var, "cada variação deve ter picture_ids mesmo sem arquivos locais"
        assert var["picture_ids"] == ["ML_FROM_URL_1"]


    """Description endpoint failure must NOT raise — it should be silently ignored."""
    service = StoreService()
    project = _make_fake_project(tmp_path)
    store = _make_fake_store()
    product_payload = {
        "title": "T", "category_id": "MLB1", "price": 10.0, "available_quantity": 10,
        "currency_id": "BRL", "buying_mode": "buy_it_now", "condition": "new",
        "listing_type_id": "gold_special", "pictures": [{"id": "PIC1"}],
        "sale_terms": [], "attributes": [], "description_plain_text": "Descrição longa do produto.",
    }

    monkeypatch.setattr(service, "resolve_local_product_images", lambda p: [])
    monkeypatch.setattr(service, "mercado_livre_validate_item", lambda tok, p: {})

    call_count = {"n": 0}

    def fake_api(*, access_token, method, path, payload=None):
        call_count["n"] += 1
        if "/description" in path:
            raise ValueError("description endpoint error simulado")
        return {"id": "MLB1"}

    monkeypatch.setattr(service, "mercado_livre_api_request", fake_api)

    result = service.publish_mercado_livre_item(store, product_payload, project)  # must not raise
    assert result["id"] == "MLB1"


def test_build_payload_sale_terms_built_from_warranty(monkeypatch: pytest.MonkeyPatch) -> None:
    """build_payload_for_marketplace deve embutir sale_terms de warranty do sales_profile."""
    from unittest.mock import MagicMock
    service = StoreService()
    connector = MagicMock()
    connector.marketplace = "mercado_livre"
    store = _make_fake_store()
    project = {
        "id": "p1",
        "name": "Chaveiro Homem De Ferro",
        "preview_url": None,
        "previews": [],
        "sales_profile": {
            "suggested_price_50_margin_brl": 29.90,
            "marketplace_attributes": [
                {"marketplace": "Mercado Livre", "title": "Chaveiro Impresso Em 3D", "full_description": "Desc"}
            ],
            "variations": [],
            "warranty": {"type": "seller", "duration": 3, "unit": "months"},
        },
    }
    request = _FakePublishRequest()

    monkeypatch.setattr(service, "predict_mercado_livre_category_id", lambda *a, **kw: "MLB186814")
    monkeypatch.setattr(service, "limit_mercado_livre_images", lambda cat, imgs: imgs)
    monkeypatch.setattr(service, "build_mercado_livre_attributes", lambda *a, **kw: [])
    monkeypatch.setattr(service, "resolve_product_images", lambda *a, **kw: [])

    payload = service.build_payload_for_marketplace(connector, store, project, request)  # type: ignore[arg-type]

    terms = {t["id"]: t["value_name"] for t in (payload.get("sale_terms") or [])}
    assert terms.get("WARRANTY_TYPE") == "Garantia do vendedor"
    assert terms.get("WARRANTY_TIME") == "3 meses"


def test_build_payload_title_uses_project_name_not_stale_channel_title(monkeypatch: pytest.MonkeyPatch) -> None:
    """ML title deve ser derivado do nome atual do projeto, não do channel.title salvo (que pode estar desatualizado)."""
    from unittest.mock import MagicMock
    service = StoreService()
    connector = MagicMock()
    connector.marketplace = "mercado_livre"
    store = _make_fake_store()
    project = {
        "id": "p1",
        "name": "Chaveiro Homem De Ferro",
        "preview_url": None,
        "previews": [],
        "sales_profile": {
            "suggested_price_50_margin_brl": 29.90,
            "marketplace_attributes": [
                # stale title — was generated when project had no name
                {"marketplace": "Mercado Livre", "title": "Impresso Em 3D", "full_description": "Desc"}
            ],
            "variations": [],
            "warranty": {"type": "seller", "duration": 1, "unit": "months"},
        },
    }
    request = _FakePublishRequest()

    monkeypatch.setattr(service, "predict_mercado_livre_category_id", lambda *a, **kw: "MLB186814")
    monkeypatch.setattr(service, "limit_mercado_livre_images", lambda cat, imgs: imgs)
    monkeypatch.setattr(service, "build_mercado_livre_attributes", lambda *a, **kw: [])
    monkeypatch.setattr(service, "resolve_product_images", lambda *a, **kw: [])

    payload = service.build_payload_for_marketplace(connector, store, project, request)  # type: ignore[arg-type]

    assert "Chaveiro Homem De Ferro" in payload["title"], f"Título esperado contendo nome do projeto, obtido: {payload['title']!r}"
    assert payload["title"] != "Impresso Em 3D", "Título não deve ser o channel.title desatualizado"


def test_mercado_livre_validate_item_accepts_warning_only_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    warning_payload = (
        '{"message":"Validation error","error":"validation_error","status":400,'
        '"cause":[{"department":"shipping","type":"warning","code":"shipping.lost_me1_by_user","message":"User has not mode me1"}]}'
    )

    def fake_urlopen(*args, **kwargs):
        raise build_http_error(warning_payload)

    monkeypatch.setattr(store_service_module, "urlopen", fake_urlopen)

    response = StoreService().mercado_livre_validate_item("token", {"title": "Produto"})
    assert response["error"] == "validation_error"
    assert response["cause"][0]["type"] == "warning"


def test_mercado_livre_validate_item_rejects_real_validation_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    error_payload = (
        '{"message":"Validation error","error":"validation_error","status":400,'
        '"cause":[{"department":"structured-data","type":"error","code":"item.attributes.missing_required","message":"Required attribute MODEL missing"}]}'
    )

    def fake_urlopen(*args, **kwargs):
        raise build_http_error(error_payload)

    monkeypatch.setattr(store_service_module, "urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="Mercado Livre API /items/validate falhou"):
        StoreService().mercado_livre_validate_item("token", {"title": "Produto"})


def test_refresh_listing_media_replaces_listing_pictures(monkeypatch: pytest.MonkeyPatch) -> None:
    service = StoreService()
    user = type("User", (), {"username": "rodrigogrosa"})()
    fake_store = {
        "id": "store-1",
        "owner_username": "rodrigogrosa",
        "marketplace": "mercado_livre",
        "credentials": {"access_token": "token"},
        "settings": {},
    }
    fake_project = type(
        "Project",
        (),
        {
            "model_dump": lambda self=None: {
                "id": "project-1",
                "name": "Produto",
                "preview_url": "/storage/p/previews/marketplace_01.jpg",
                "previews": [
                    {"label": "marketplace_01.jpg", "path": "/storage/p/previews/marketplace_01.jpg", "kind": "marketplace_preview"},
                    {"label": "marketplace_02.jpg", "path": "/storage/p/previews/marketplace_02.jpg", "kind": "marketplace_preview"},
                ],
                "sales_profile": {"suggested_price_50_margin_brl": 10, "marketplace_attributes": [{"marketplace": "Mercado Livre", "title": "Produto", "full_description": "Desc"}]},
            }
        },
    )()

    monkeypatch.setattr(service, "load_store_records", lambda: [fake_store])
    monkeypatch.setattr(store_service_module, "ProjectService", lambda: type("PS", (), {"get_project": lambda self, project_id: fake_project})())
    monkeypatch.setattr(service, "build_mercado_livre_attributes", lambda *args, **kwargs: [])

    captured: dict[str, object] = {}

    def fake_request(*, access_token: str, method: str, path: str, payload: dict[str, object] | None = None):
        captured["access_token"] = access_token
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {"id": "MLB123", "permalink": "https://example.com/item"}

    monkeypatch.setattr(service, "mercado_livre_api_request", fake_request)

    result = service.refresh_listing_media(user, "store-1", "project-1", "MLB123")

    assert result["status"] == "updated"
    assert captured["method"] == "PUT"
    assert captured["path"] == "/items/MLB123"
    assert captured["payload"] == {
        "pictures": [
            {"source": "https://api.euachei3d.com.br/storage/p/previews/marketplace_01.jpg"},
            {"source": "https://api.euachei3d.com.br/storage/p/previews/marketplace_02.jpg"},
        ]
    }


def test_build_mercado_livre_attributes_fills_secondary_sculpture_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    service = StoreService()
    category_attributes = [
        {"id": "MATERIAL", "name": "Material", "value_type": "string", "tags": {"required": True}, "values": []},
        {"id": "SCULPTURE_THEME", "name": "Temática da escultura", "value_type": "string", "values": [{"id": "2489107", "name": "Animais"}]},
        {"id": "SCULPTURE_TYPE", "name": "Tipo de escultura", "value_type": "string", "values": [{"id": "2489103", "name": "Estátua"}]},
        {"id": "ARTWORK_TYPE", "name": "Tipo de obra", "value_type": "list", "values": [{"id": "2489102", "name": "Réplica"}]},
        {"id": "CHARACTER", "name": "Personagem", "value_type": "string", "values": []},
        {"id": "LENGTH", "name": "Comprimento", "value_type": "number_unit", "allowed_units": [{"id": "cm", "name": "cm"}]},
        {"id": "WIDTH", "name": "Largura", "value_type": "number_unit", "allowed_units": [{"id": "cm", "name": "cm"}]},
        {"id": "HEIGHT", "name": "Altura", "value_type": "number_unit", "allowed_units": [{"id": "cm", "name": "cm"}]},
        {"id": "WEIGHT", "name": "Peso", "value_type": "number_unit", "allowed_units": [{"id": "g", "name": "g"}]},
        {"id": "WITH_BASE", "name": "Com base", "value_type": "boolean", "values": [{"id": "242084", "name": "Não"}, {"id": "242085", "name": "Sim"}]},
    ]
    monkeypatch.setattr(service, "fetch_mercado_livre_category_attributes", lambda category_id: category_attributes)

    project = {
        "name": "Baby Parrot Zoocre8tions 3Colors",
        "original_filename": "Baby_Parrot_ZooCre8tions_3Colors.3mf",
        "metadata": {"mesh_metrics": {"extents_mm_assumed": [37.0, 62.0, 44.0]}},
        "sales_profile": {
            "estimated_material_g": 15.0,
            "assumptions": ["Material assumido: PLA. Ajuste conforme uso final."],
        },
    }
    channel = {
        "title": "Baby Parrot Zoocre8Tions 3Colors Impresso Em 3D",
        "description": "Mini escultura decorativa de um papagaio bebê impressa em 3D.",
    }

    attributes = service.build_mercado_livre_attributes("MLB186814", project, channel)
    by_id = {item["id"]: item for item in attributes}

    assert by_id["MATERIAL"]["value_name"] == "Plástico"
    assert by_id["SCULPTURE_THEME"]["value_name"] == "Animais"
    assert by_id["SCULPTURE_TYPE"]["value_name"] == "Estátua"
    assert by_id["ARTWORK_TYPE"]["value_name"] == "Réplica"
    assert by_id["CHARACTER"]["value_name"] == "Papagaio"
    assert by_id["WIDTH"]["value_struct"] == {"number": 3.7, "unit": "cm"}
    assert by_id["HEIGHT"]["value_struct"] == {"number": 6.2, "unit": "cm"}
    assert by_id["LENGTH"]["value_struct"] == {"number": 4.4, "unit": "cm"}
    assert by_id["WEIGHT"]["value_struct"] == {"number": 15.0, "unit": "g"}
    assert by_id["WITH_BASE"]["value_name"] == "Não"


def test_build_mercado_livre_attributes_fills_keychain_secondary_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """INCLUDES_HOOK, INCLUDES_STRAP, PIECES_NUMBER e MIN_RECOMMENDED_AGE devem ser preenchidos
    automaticamente para chaveiros — os campos 'Características secundárias' que aparecem
    vazios no formulário do Mercado Livre."""
    service = StoreService()
    # Confirmed attribute IDs from GET /categories/MLB439316/attributes on 2026-05-03
    category_attributes = [
        {"id": "MATERIAL", "name": "Material", "value_type": "string", "tags": {"required": True}, "values": [{"id": "1", "name": "Plástico"}]},
        {"id": "HEIGHT", "name": "Altura", "value_type": "number_unit", "values": []},
        {"id": "WIDTH", "name": "Largura", "value_type": "number_unit", "values": []},
        {"id": "MIN_RECOMMENDED_AGE", "name": "Idade mínima recomendada", "value_type": "number_unit", "values": []},
        {"id": "INCLUDES_HOOK", "name": "Inclui gancho", "value_type": "boolean", "values": [{"id": "1", "name": "Não"}, {"id": "2", "name": "Sim"}]},
        {"id": "INCLUDES_STRAP", "name": "Inclui correia", "value_type": "boolean", "values": [{"id": "1", "name": "Não"}, {"id": "2", "name": "Sim"}]},
        {"id": "PIECES_NUMBER", "name": "Quantidade de peças", "value_type": "number", "values": []},
    ]
    monkeypatch.setattr(service, "fetch_mercado_livre_category_attributes", lambda cat: category_attributes)

    project = {
        "name": "Chaveiro Homem De Ferro",
        "original_filename": "chaveiro.3mf",
        "metadata": {"mesh_metrics": {"extents_mm_assumed": [45.0, 50.0, 8.0]}},
        "sales_profile": {
            "estimated_material_g": 5.0,
            "assumptions": ["Material assumido: PLA. Ajuste conforme uso final."],
        },
    }
    channel = {"title": "Chaveiro Homem De Ferro Impresso Em 3D", "description": "Chaveiro impresso."}

    attributes = service.build_mercado_livre_attributes("MLB439316", project, channel)
    by_id = {item["id"]: item for item in attributes}

    # Material PLA should be mapped to ML option "Plástico"
    assert by_id["MATERIAL"]["value_name"] == "Plástico", "PLA deve ser mapeado para Plástico"

    # Dimensions
    assert "WIDTH" in by_id, "WIDTH (Largura) deve estar preenchido"
    assert "HEIGHT" in by_id, "HEIGHT (Altura) deve estar preenchido"

    # Keychain has hook
    assert "INCLUDES_HOOK" in by_id, "INCLUDES_HOOK (Inclui gancho) deve estar preenchido"
    assert by_id["INCLUDES_HOOK"]["value_name"] == "Sim", "Chaveiro deve ter gancho=Sim"

    # No strap by default
    assert "INCLUDES_STRAP" in by_id, "INCLUDES_STRAP (Inclui correia) deve estar preenchido"
    assert by_id["INCLUDES_STRAP"]["value_name"] == "Não", "INCLUDES_STRAP default deve ser Não"

    # 1 piece
    assert "PIECES_NUMBER" in by_id, "PIECES_NUMBER (Quantidade de peças) deve estar preenchido"
    assert by_id["PIECES_NUMBER"]["value_name"] == "1", "Quantidade de peças default deve ser 1"

    # Minimum recommended age = 3 anos
    assert "MIN_RECOMMENDED_AGE" in by_id, "MIN_RECOMMENDED_AGE (Idade mínima) deve estar preenchido"
    assert by_id["MIN_RECOMMENDED_AGE"]["value_name"] == "3 anos", "Idade mínima default deve ser 3 anos"
