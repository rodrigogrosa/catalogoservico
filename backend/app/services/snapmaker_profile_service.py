from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


class SnapmakerProfileService:
    def __init__(self) -> None:
        self.profile_path = Path(__file__).resolve().parents[1] / "data" / "profiles" / "snapmaker_u1_v1.json"

    @lru_cache(maxsize=1)
    def load_profile(self) -> dict[str, Any]:
        return json.loads(self.profile_path.read_text(encoding="utf-8"))

    def get_preset(self, objective: str) -> dict[str, Any]:
        profile = self.load_profile()
        presets = profile.get("objective_presets", {})
        return presets.get(objective, presets.get("balanced", {}))

    def get_material_rule(self, material: str) -> dict[str, Any] | None:
        profile = self.load_profile()
        return profile.get("material_rules", {}).get(material.upper())
