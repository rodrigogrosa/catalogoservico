from io import BytesIO
from pathlib import Path
import sys
from urllib.error import HTTPError

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

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
