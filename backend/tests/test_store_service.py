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

    assert by_id["MATERIAL"]["value_name"] == "PLA"
    assert by_id["SCULPTURE_THEME"]["value_name"] == "Animais"
    assert by_id["SCULPTURE_TYPE"]["value_name"] == "Estátua"
    assert by_id["ARTWORK_TYPE"]["value_name"] == "Réplica"
    assert by_id["CHARACTER"]["value_name"] == "Papagaio"
    assert by_id["WIDTH"]["value_struct"] == {"number": 3.7, "unit": "cm"}
    assert by_id["HEIGHT"]["value_struct"] == {"number": 6.2, "unit": "cm"}
    assert by_id["LENGTH"]["value_struct"] == {"number": 4.4, "unit": "cm"}
    assert by_id["WEIGHT"]["value_struct"] == {"number": 15.0, "unit": "g"}
    assert by_id["WITH_BASE"]["value_name"] == "Não"
