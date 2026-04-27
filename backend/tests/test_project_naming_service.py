from pathlib import Path
import sys


from app.services.project_naming_service import ProjectNamingService


def test_character_name_gets_highlight() -> None:
    service = ProjectNamingService()
    title = service.generate_name(source_name="Deadpool 3 Mask plated_snapmaker_compatible_final_part08.3mf")
    assert title == "Deadpool Máscara"


def test_non_character_name_is_humanized_for_sales() -> None:
    service = ProjectNamingService()
    title = service.generate_name(source_name="Baby_Parrot_ZooCre8tions_3Colors.3mf")
    assert title == "Baby Parrot Multicor"


def test_keychain_name_becomes_friendlier() -> None:
    service = ProjectNamingService()
    title = service.generate_name(source_name="flower-keychain-from-a-to-z.3mf")
    assert title == "Flower Chaveiro"
