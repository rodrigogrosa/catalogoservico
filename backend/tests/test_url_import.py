from pathlib import Path
import sys
from urllib.parse import urlparse

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.project_service import ProjectService


def test_makerworld_model_page_is_rejected_as_non_direct_file() -> None:
    service = ProjectService()
    parsed = urlparse("https://makerworld.com/pt/models/2280290-heart-spin-keychain-fidget?from=recommend#profileId-2486522")
    assert service.is_makerworld_model_page(parsed)
    assert "pagina do modelo" in service.makerworld_page_error()
    assert "Baixar 3MF" in service.makerworld_page_error()
    assert "sessao logada" in service.makerworld_blocked_error()


def test_makerworld_text_fragment_download_hint_is_not_direct_file() -> None:
    service = ProjectService()
    parsed = urlparse(
        "https://makerworld.com/pt/models/2574686-flower-keychain-from-a-to-z"
        "?appSharePlatform=whatsapp#profileId-2838931:~:text=Baixar-,3MF,-Impulsionar"
    )
    assert service.is_makerworld_model_page(parsed)
