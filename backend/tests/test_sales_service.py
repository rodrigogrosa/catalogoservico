from pathlib import Path
import sys


from app.services.sales_service import SalesService


def test_keychain_pricing_uses_market_anchor_and_brl() -> None:
    profile = SalesService().build_sales_profile(
        {
            "name": "gostface_mini_keychain",
            "input_format": "3mf",
            "size_bytes": 18_000_000,
            "metadata": {},
            "source_ecosystem": "bambu_lab",
        },
        allow_llm=False,
    )

    assert profile["pricing_version"] == SalesService.PRICING_VERSION
    assert profile["currency"] == "BRL"
    assert profile["suggested_price_50_margin_brl"] <= 24.9
    assert profile["estimated_material_g"] <= 28.0
    assert "Chaveiro" in profile["marketplace_attributes"][0]["category"]
    assert any(item["marketplace"] == "Instagram" for item in profile["marketplace_attributes"])
    assert profile["marketplace_attributes"][0]["registration_attributes"]
    assert profile["marketplace_attributes"][0]["full_description"]
