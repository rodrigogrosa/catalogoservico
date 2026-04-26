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
