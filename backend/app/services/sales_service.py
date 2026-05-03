from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.free_ai_service import FreeAiService


class SalesService:
    PRICING_VERSION = "br-v4-ollama-marketplace-copy"
    DEFAULT_FILAMENT_COST_BRL_PER_KG = 95.0
    ENERGY_BRL_PER_KWH = 1.05
    DEFAULT_MACHINE_WEAR_BRL_PER_HOUR = 1.25
    DEFAULT_PRINTER_POWER_KW = 0.12
    MARKETPLACE_COPY_PROMPT = """
Voce e um especialista brasileiro em cadastro de produtos impressos em 3D.
Explique o que e o produto em linguagem de venda e, se o nome indicar personagem conhecido, diga quem e e de qual universo veio.
Nao invente licenca, autoria, compatibilidade oficial ou marca oficial.
Se houver personagem, inclua alerta curto sobre direitos/licenca para venda.
Responda JSON valido e compacto com: product_explanation, character_context, bullet_points, hashtags.
character_context deve conter: is_character, name, origin, short_history, rights_note.
bullet_points deve ter no maximo 5 itens. hashtags deve ter no maximo 10 itens.
"""

    CATEGORY_RULES = {
        "keychain": {
            "label": "Chaveiro / brinde pequeno",
            "material_range_g": (6.0, 28.0),
            "hours_range": (0.35, 1.6),
            "labor_brl": 2.5,
            "packaging_brl": 1.2,
            "accessory_brl": 1.0,
            "machine_wear_brl_h": 0.9,
            "market_floor_brl": 7.9,
            "market_ceiling_brl": 24.9,
            "reseller_margin_percent": 18,
        },
        "small_decor": {
            "label": "Decoração pequena",
            "material_range_g": (18.0, 90.0),
            "hours_range": (1.0, 5.5),
            "labor_brl": 5.0,
            "packaging_brl": 2.5,
            "accessory_brl": 0.0,
            "machine_wear_brl_h": 1.25,
            "market_floor_brl": 19.9,
            "market_ceiling_brl": 79.9,
            "reseller_margin_percent": 22,
        },
        "figure": {
            "label": "Boneco / colecionável",
            "material_range_g": (35.0, 320.0),
            "hours_range": (2.5, 18.0),
            "labor_brl": 9.0,
            "packaging_brl": 4.5,
            "accessory_brl": 0.0,
            "machine_wear_brl_h": 1.6,
            "market_floor_brl": 39.9,
            "market_ceiling_brl": 249.9,
            "reseller_margin_percent": 25,
        },
        "functional": {
            "label": "Suporte / peça funcional",
            "material_range_g": (35.0, 450.0),
            "hours_range": (2.0, 24.0),
            "labor_brl": 10.0,
            "packaging_brl": 4.0,
            "accessory_brl": 0.0,
            "machine_wear_brl_h": 1.8,
            "market_floor_brl": 29.9,
            "market_ceiling_brl": 299.9,
            "reseller_margin_percent": 25,
        },
        "generic": {
            "label": "Produto 3D genérico",
            "material_range_g": (20.0, 260.0),
            "hours_range": (1.2, 16.0),
            "labor_brl": 7.0,
            "packaging_brl": 3.0,
            "accessory_brl": 0.0,
            "machine_wear_brl_h": 1.4,
            "market_floor_brl": 19.9,
            "market_ceiling_brl": 199.9,
            "reseller_margin_percent": 25,
        },
    }

    def __init__(self) -> None:
        self.settings = get_settings()
        self.free_ai = FreeAiService(self.settings)

    def build_sales_profile(self, manifest: dict[str, Any], *, allow_llm: bool = True) -> dict[str, Any]:
        metadata = manifest.get("metadata") or {}
        metrics = metadata.get("mesh_metrics") or {}
        material = self._infer_material(manifest)
        project_name = str(manifest.get("name") or manifest.get("slug") or "Projeto 3D")
        category_key = self._category_key(project_name)
        rules = self.CATEGORY_RULES[category_key]
        estimated_material_g = self._estimate_material_g(manifest, metrics, rules)
        estimated_print_hours = self._estimate_print_hours(metrics, estimated_material_g, rules)
        material_cost = estimated_material_g / 1000 * self.DEFAULT_FILAMENT_COST_BRL_PER_KG
        energy_cost = estimated_print_hours * self.DEFAULT_PRINTER_POWER_KW * self.ENERGY_BRL_PER_KWH
        machine_cost = estimated_print_hours * float(rules["machine_wear_brl_h"])
        base_cost = (
            material_cost
            + energy_cost
            + machine_cost
            + float(rules["labor_brl"])
            + float(rules["packaging_brl"])
            + float(rules["accessory_brl"])
        )
        suggested_price = self._round_commercial(base_cost * 1.5, category_key)
        reseller_margin_percent = float(rules["reseller_margin_percent"])
        reseller_price = self._round_money(base_cost * (1 + reseller_margin_percent / 100))

        assumptions = [
            f"Categoria comercial detectada: {rules['label']}.",
            f"Material assumido: {material}. Ajuste se o projeto usar outro filamento.",
            f"Custo de filamento assumido: R$ {self.DEFAULT_FILAMENT_COST_BRL_PER_KG:.2f}/kg.",
            "Para 3MF/Bambu, o tamanho do arquivo nao e usado sozinho como peso; a estimativa e limitada por categoria para evitar preco inflado.",
            "Nao inclui comissao especifica de marketplace, frete subsidiado, imposto ou perda por retrabalho.",
            self._market_reference_note(category_key),
        ]
        commerce_content = self._commerce_content(project_name, material, manifest, category_key, suggested_price, allow_llm=allow_llm)
        sku = self._generate_sku(manifest)

        return {
            "pricing_version": self.PRICING_VERSION,
            "copy_source": commerce_content.get("copy_source", "deterministic"),
            "sku": sku,
            "default_stock": 100,
            "warranty": {"type": "seller", "duration": 1, "unit": "months", "label": "1 mês — garantia do vendedor"},
            "variations": self._default_variations(sku, suggested_price),
            "estimated_material_g": round(estimated_material_g, 1),
            "estimated_print_hours": round(estimated_print_hours, 1),
            "estimated_base_cost_brl": round(base_cost, 2),
            "suggested_price_50_margin_brl": suggested_price,
            "reseller_price_brl": reseller_price,
            "default_margin_percent": 50,
            "reseller_margin_percent": reseller_margin_percent,
            "currency": "BRL",
            "assumptions": assumptions,
            "sales_tips": self._sales_tips(project_name, material, manifest),
            "marketplace_attributes": self._marketplace_attributes(project_name, material, manifest, commerce_content, sku),
        }

    def _infer_material(self, manifest: dict[str, Any]) -> str:
        request = (manifest.get("metadata") or {}).get("request_parameters") or {}
        target_material = request.get("target_material")
        if isinstance(target_material, str) and target_material.strip():
            return target_material.strip().upper()
        name = str(manifest.get("name") or "").lower()
        if "petg" in name:
            return "PETG"
        if "abs" in name:
            return "ABS"
        if "asa" in name:
            return "ASA"
        if "tpu" in name:
            return "TPU"
        return "PLA"

    # ------------------------------------------------------------------
    # SKU + Variations + Warranty helpers
    # ------------------------------------------------------------------

    def _generate_sku(self, manifest: dict[str, Any]) -> str:
        """Generate a deterministic SKU from the project slug/id."""
        import re
        slug = str(manifest.get("slug") or manifest.get("id") or "").strip()
        if not slug:
            name = str(manifest.get("name") or "produto")
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        # Trim the version suffix (_v001) if present
        slug = re.sub(r"_v\d+$", "", slug)
        # Keep only alphanumeric and hyphens, uppercase, max 16 chars
        clean = re.sub(r"[^a-z0-9-]", "", slug.lower())[:16].strip("-")
        return f"SM3D-{clean.upper()}-001"

    def _default_variations(self, base_sku: str, unit_price: float) -> list[dict[str, Any]]:
        """Return 2 standard variations: 1 unit and a pack of 10 (10% bulk discount)."""
        pack_price = round(unit_price * 10 * 0.90, 2)
        return [
            {
                "sku": f"{base_sku}-UN1",
                "name": "1 unidade",
                "quantity": 1,
                "stock": 100,
                "price_brl": unit_price,
                "description": "Peça individual — cor conforme disponibilidade (consulte antes).",
            },
            {
                "sku": f"{base_sku}-KIT10",
                "name": "Kit 10 unidades (10% desconto)",
                "quantity": 10,
                "stock": 100,
                "price_brl": pack_price,
                "description": "Lote de 10 peças iguais ou em cores variadas — 10% de desconto sobre o unitário.",
            },
        ]

    def _estimate_material_g(self, manifest: dict[str, Any], metrics: dict[str, Any], rules: dict[str, object]) -> float:
        minimum, maximum = rules["material_range_g"]
        volume = metrics.get("volume_mm3_assumed")
        if isinstance(volume, (int, float)) and volume > 0:
            return max(float(minimum), min(float(maximum), float(volume) * 1.24 / 1000))

        size_bytes = float(manifest.get("size_bytes") or 0)
        input_format = str(manifest.get("input_format") or "").lower()
        if input_format == "3mf":
            estimate = 8.0 + size_bytes / 550_000
            return max(float(minimum), min(float(maximum), estimate))
        if input_format in {"stl", "obj"}:
            estimate = 10.0 + size_bytes / 360_000
            return max(float(minimum), min(float(maximum), estimate))
        return max(float(minimum), min(float(maximum), 15.0 + size_bytes / 450_000))

    def _estimate_print_hours(self, metrics: dict[str, Any], material_g: float, rules: dict[str, object]) -> float:
        minimum, maximum = rules["hours_range"]
        height = 0.0
        extents = metrics.get("extents_mm_assumed")
        if isinstance(extents, list) and extents:
            try:
                height = max(float(value) for value in extents)
            except (TypeError, ValueError):
                height = 0.0
        base = material_g / 24.0
        height_factor = height / 90.0 if height else 0.8
        return max(float(minimum), min(float(maximum), base + height_factor))

    def _sales_tips(self, project_name: str, material: str, manifest: dict[str, Any]) -> list[str]:
        tips = [
            "Publique fotos reais do item impresso e uma imagem mostrando escala com a mão ou régua.",
            "Inclua prazo de produção separado do prazo de envio para evitar reclamações.",
            "Informe que pequenas linhas de camada são características de impressão 3D FDM.",
            "Ofereça variação de cor/material como adicional quando o modelo permitir.",
        ]
        source = str(manifest.get("source_ecosystem") or "")
        if source == "bambu_lab":
            tips.append("Revise a licença/autorização do modelo original antes de vender o item impresso.")
        if material in {"PETG", "ASA", "ABS"}:
            tips.append(f"Destaque maior resistência do {material}, mas informe limitações de acabamento e tolerância.")
        return tips

    def _commerce_content(
        self,
        project_name: str,
        material: str,
        manifest: dict[str, Any],
        category_key: str,
        suggested_price: float,
        *,
        allow_llm: bool,
    ) -> dict[str, Any]:
        dimensions = self._dimension_hint(manifest)
        character = self._character_context(project_name)
        fallback = self._fallback_commerce_content(project_name, material, dimensions, category_key, suggested_price, character)
        fallback["copy_source"] = "deterministic"
        if not allow_llm:
            return fallback

        preview_image = self._resolve_preview_image_path(manifest)
        payload = {
            "project_name": project_name,
            "material": material,
            "commercial_category": self._category_for_project(project_name),
            "dimensions": dimensions,
            "suggested_price_brl": suggested_price,
            "source_ecosystem": manifest.get("source_ecosystem"),
            "known_character_hint": character,
            "mesh_metrics": (manifest.get("metadata") or {}).get("mesh_metrics", {}),
            "detected_files": ((manifest.get("metadata") or {}).get("parsing") or {}).get("detected_files", []),
        }

        response, ai_meta = self.free_ai.generate_json_with_fallback(
            system_prompt=self.MARKETPLACE_COPY_PROMPT,
            user_prompt=json.dumps(payload, ensure_ascii=False),
            fallback=fallback,
            image_path=preview_image,
        )
        normalized = self._normalize_commerce_content(response, fallback)
        normalized["copy_source"] = "ia_fallback_chain" if response is not fallback else "deterministic"
        normalized["ai_generation"] = ai_meta
        return normalized

    def _resolve_preview_image_path(self, manifest: dict[str, Any]) -> Path | None:
        for preview in manifest.get("previews") or []:
            raw = str(preview.get("path") or "")
            if not raw:
                continue
            if raw.startswith("/storage/"):
                candidate = self.settings.storage_root / raw.split("/storage/", 1)[1]
            else:
                candidate = Path(raw)
            if candidate.exists() and candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                return candidate
        return None

    def _fallback_commerce_content(
        self,
        project_name: str,
        material: str,
        dimensions: str,
        category_key: str,
        suggested_price: float,
        character: dict[str, str | bool],
    ) -> dict[str, Any]:
        slug_title = self._title(project_name)
        category = self._category_for_project(project_name)
        product_explanation = (
            f"{slug_title} e um produto impresso em 3D sob demanda em {material}. "
            f"{dimensions} O acabamento e feito por manufatura aditiva FDM, portanto pequenas linhas de camada podem aparecer."
        )
        if character.get("is_character"):
            product_explanation = (
                f"{slug_title} e uma peca decorativa inspirada em {character['name']}. "
                f"{character['short_history']} {dimensions} Produto impresso em 3D sob demanda em {material}."
            )
        attributes = self._base_registration_attributes(project_name, material, dimensions, category, suggested_price)
        bullets = [
            f"Produto impresso em 3D sob demanda em {material}.",
            "Pode ter pequenas marcas de camada, caracteristicas do processo FDM.",
            "Cor e acabamento podem variar conforme disponibilidade de filamento.",
            "Ideal para presente, decoracao, colecao ou uso leve conforme o modelo.",
        ]
        hashtags = self._hashtags(project_name, material)
        return {
            "product_explanation": product_explanation,
            "character_context": character,
            "marketplaces": {
                "Mercado Livre": {
                    "title": f"{slug_title} Impresso Em 3D",
                    "category": category,
                    "short_description": product_explanation,
                    "full_description": self._full_marketplace_description(product_explanation, bullets, character),
                    "attributes": attributes,
                    "bullet_points": bullets,
                    "hashtags": hashtags,
                },
                "Shopee": {
                    "title": f"{slug_title} 3D Personalizavel",
                    "category": category,
                    "short_description": product_explanation,
                    "full_description": self._full_marketplace_description(product_explanation, bullets, character),
                    "attributes": attributes,
                    "bullet_points": bullets,
                    "hashtags": hashtags,
                },
                "Instagram": {
                    "title": f"{slug_title} | Impresso Em 3D",
                    "category": "Post / Reels / Loja",
                    "short_description": f"{slug_title} impresso em 3D sob demanda. Consulte cores e prazo por mensagem.",
                    "full_description": self._instagram_caption(product_explanation, bullets, hashtags, character),
                    "attributes": [
                        {"label": "Formato", "value": "Post, Reels, Stories e Loja"},
                        {"label": "Preco sugerido", "value": f"R$ {suggested_price:.2f}".replace(".", ",")},
                        {"label": "Chamada", "value": "Chame no direct/WhatsApp para cores e prazo"},
                    ],
                    "bullet_points": bullets,
                    "hashtags": hashtags,
                },
            },
        }

    def _normalize_commerce_content(self, response: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(response, dict):
            return fallback
        if "marketplaces" not in response:
            return self._merge_compact_llm_content(response, fallback)
        marketplaces = response.get("marketplaces")
        if not isinstance(marketplaces, dict):
            return fallback
        normalized = {**fallback, **response, "marketplaces": {**fallback["marketplaces"]}}
        for channel, fallback_channel in fallback["marketplaces"].items():
            source = marketplaces.get(channel)
            if not isinstance(source, dict):
                continue
            normalized["marketplaces"][channel] = {
                **fallback_channel,
                **{key: value for key, value in source.items() if value},
            }
            attrs = normalized["marketplaces"][channel].get("attributes")
            if not isinstance(attrs, list) or not attrs:
                normalized["marketplaces"][channel]["attributes"] = fallback_channel["attributes"]
            normalized["marketplaces"][channel]["attributes"] = [
                {"label": str(item.get("label", "")).strip(), "value": str(item.get("value", "")).strip()}
                for item in normalized["marketplaces"][channel]["attributes"]
                if isinstance(item, dict) and item.get("label") and item.get("value")
            ][:16]
        return normalized

    def _merge_compact_llm_content(self, response: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        product_explanation = str(response.get("product_explanation") or fallback["product_explanation"]).strip()
        character = response.get("character_context") if isinstance(response.get("character_context"), dict) else fallback["character_context"]
        bullets = response.get("bullet_points") if isinstance(response.get("bullet_points"), list) else []
        bullets = [str(item).strip() for item in bullets if str(item).strip()][:5] or fallback["marketplaces"]["Mercado Livre"]["bullet_points"]
        hashtags = response.get("hashtags") if isinstance(response.get("hashtags"), list) else []
        hashtags = [str(item).strip().lstrip("#") for item in hashtags if str(item).strip()][:10] or fallback["marketplaces"]["Instagram"]["hashtags"]

        merged = {**fallback, "product_explanation": product_explanation, "character_context": character, "marketplaces": {}}
        for channel, content in fallback["marketplaces"].items():
            full_description = (
                self._instagram_caption(product_explanation, bullets, hashtags, character)
                if channel == "Instagram"
                else self._full_marketplace_description(product_explanation, bullets, character)
            )
            merged["marketplaces"][channel] = {
                **content,
                "short_description": product_explanation,
                "full_description": full_description,
                "bullet_points": bullets,
                "hashtags": hashtags,
            }
        return merged

    def _marketplace_attributes(
        self,
        project_name: str,
        material: str,
        manifest: dict[str, Any],
        commerce_content: dict[str, Any],
        sku: str = "",
    ) -> list[dict[str, Any]]:
        slug_title = project_name.replace("_", " ").replace("-", " ").strip().title()
        category = self._category_for_project(project_name)
        tags = self._tags_for_project(project_name, material)
        dimensions = self._dimension_hint(manifest)
        character = commerce_content.get("character_context") if isinstance(commerce_content.get("character_context"), dict) else {}
        base_description = (
            f"Produto impresso em 3D sob demanda em {material}. {dimensions} "
            "Acabamento FDM com possibilidade de pequenas linhas de camada. Ideal para uso decorativo, presente ou organização."
        )
        defaults = [
            {
                "marketplace": "Mercado Livre",
                "title": f"{slug_title} Impresso Em 3D",
                "category": category,
                "description": base_description,
                "tags": tags,
                "required_fields": ["Título até 60 caracteres", "Categoria", "Fotos reais", "Estoque/prazo", "Variações de cor", "Garantia"],
            },
            {
                "marketplace": "Shopee",
                "title": f"{slug_title} 3D Personalizável",
                "category": category,
                "description": f"{base_description} Consulte cores disponíveis antes da compra.",
                "tags": tags,
                "required_fields": ["Título curto", "Descrição com medidas", "SKU", "Peso do pacote", "Prazo de postagem"],
            },
            {
                "marketplace": "Instagram",
                "title": f"{slug_title} | Impresso Em 3D",
                "category": "Post / Reels / Loja",
                "description": (
                    f"{slug_title} produzido sob demanda em {material}. "
                    "Peça leve, personalizável por cor e ideal para presente. "
                    "Envie mensagem para consultar prazo, cores disponíveis e entrega."
                ),
                "tags": [*tags, "produto personalizado", "presente criativo", "impressao3dbrasil"],
                "required_fields": ["Foto principal", "Preço em R$", "Medidas", "Prazo de produção", "CTA para direct/WhatsApp"],
            },
            {
                "marketplace": "Elo7",
                "title": f"{slug_title} Personalizado Em Impressão 3D",
                "category": "Personalizados / Decoração",
                "description": f"{base_description} Produção artesanal sob encomenda.",
                "tags": [*tags, "personalizado", "presente"],
                "required_fields": ["Prazo de produção", "Personalização", "Fotos", "Medidas", "Política de troca"],
            },
            {
                "marketplace": "Etsy",
                "title": f"3D Printed {slug_title}",
                "category": "Home & Living / Decor",
                "description": f"Made-to-order 3D printed item in {material}. Layer lines may be visible due to FDM manufacturing.",
                "tags": tags[:13],
                "required_fields": ["English title", "13 tags", "Production partner if applicable", "Materials", "Shipping profile"],
            },
        ]
        enriched = []
        marketplace_payload = commerce_content.get("marketplaces") if isinstance(commerce_content.get("marketplaces"), dict) else {}
        for item in defaults:
            channel = item["marketplace"]
            content = marketplace_payload.get(channel) if isinstance(marketplace_payload.get(channel), dict) else {}
            full_description = str(content.get("full_description") or item["description"])
            short_description = str(content.get("short_description") or item["description"])
            enriched.append(
                {
                    **item,
                    "title": str(content.get("title") or item["title"]),
                    "category": str(content.get("category") or item["category"]),
                    "description": short_description,
                    "short_description": short_description,
                    "full_description": full_description,
                    "product_context": str(commerce_content.get("product_explanation") or short_description),
                    "character_origin": self._character_origin_text(character),
                    "registration_attributes": content.get("attributes") or self._base_registration_attributes(
                        project_name, material, dimensions, item["category"], 0
                    ),
                    "bullet_points": content.get("bullet_points") or [],
                    "hashtags": content.get("hashtags") or self._hashtags(project_name, material),
                    "sku": f"{sku}-{channel[:2].upper()}" if sku else "",
                    "default_stock": 100,
                    "warranty": {"type": "seller", "duration": 1, "unit": "months", "label": "1 mês — garantia do vendedor"},
                }
            )
        return enriched

    def _category_for_project(self, project_name: str) -> str:
        return str(self.CATEGORY_RULES[self._category_key(project_name)]["label"])

    def _category_key(self, project_name: str) -> str:
        name = project_name.lower()
        if any(term in name for term in ["key", "keych", "chave", "chaveiro", "llavero"]):
            return "keychain"
        if any(term in name for term in ["stand", "holder", "suporte", "dock"]):
            return "functional"
        if any(term in name for term in ["toy", "flexi", "figure", "boneco"]):
            return "figure"
        if any(term in name for term in ["mini", "small", "ornament", "decor"]):
            return "small_decor"
        return "generic"

    def _title(self, project_name: str) -> str:
        return " ".join(project_name.replace("_", " ").replace("-", " ").split()).strip().title() or "Produto 3D"

    def _character_context(self, project_name: str) -> dict[str, str | bool]:
        name = project_name.lower()
        known = [
            # ── Marvel ────────────────────────────────────────────────────────────
            (
                ["deadpool", "dead pool"],
                "Deadpool",
                "Marvel Comics",
                "Deadpool e um anti-heroi dos quadrinhos da Marvel conhecido pelo humor acido, traje vermelho e preto e estilo irreverente.",
            ),
            (
                ["spiderman", "spider-man", "spider man", "homem aranha", "homem-aranha"],
                "Spider-Man",
                "Marvel Comics",
                "Spider-Man e um super-heroi da Marvel associado a Peter Parker, teias, agilidade e ao lema de responsabilidade.",
            ),
            (
                ["ironman", "iron man", "iron-man"],
                "Iron Man",
                "Marvel Comics",
                "Iron Man e um heroi da Marvel associado a Tony Stark, armaduras tecnologicas e visual metalico vermelho e dourado.",
            ),
            (
                ["thanos"],
                "Thanos",
                "Marvel Comics",
                "Thanos e o principal vilao do Universo Cinematografico Marvel, conhecido pela Manopla do Infinito e pela busca pelo poder absoluto.",
            ),
            (
                ["hulk"],
                "Hulk",
                "Marvel Comics",
                "Hulk e um super-heroi da Marvel, alter ego verde do cientista Bruce Banner, conhecido pela forca descomunal e pela raiva.",
            ),
            (
                ["thor"],
                "Thor",
                "Marvel Comics / Mitologia Nordica",
                "Thor e o deus do troveao da mitologia nordica e super-heroi da Marvel, reconhecido pelo mjolnir e pelo visual guerreiro.",
            ),
            (
                ["captain america", "capitao america", "cap america"],
                "Capitao America",
                "Marvel Comics",
                "Capitao America e um super-heroi da Marvel, simbolo de heroismo americano, reconhecido pelo escudo circular azul e vermelho.",
            ),
            (
                ["wolverine"],
                "Wolverine",
                "Marvel Comics / X-Men",
                "Wolverine e um mutante dos X-Men da Marvel, conhecido pelas garras de adamantio, fator de cura e visual icônico.",
            ),
            (
                ["venom"],
                "Venom",
                "Marvel Comics",
                "Venom e um simbionte alien da Marvel, villao e anti-heroi com aparencia preta, dentes afiados e lingua caracteristica.",
            ),
            (
                ["groot"],
                "Groot",
                "Marvel Comics / Guardioes da Galaxia",
                "Groot e um ser alienígena arboriforme dos Guardioes da Galaxia da Marvel, famoso pela frase 'Eu sou o Groot'.",
            ),
            # ── DC ────────────────────────────────────────────────────────────────
            (
                ["superman", "super man"],
                "Superman",
                "DC Comics",
                "Superman e um super-heroi da DC Comics, conhecido pelo uniforme azul e vermelho, capa e poderes sobre-humanos.",
            ),
            (
                ["batman", "bat man"],
                "Batman",
                "DC Comics",
                "Batman e o Cavaleiro das Trevas da DC Comics, vigilante de Gotham City reconhecido pelo traje negro e o morcego no peito.",
            ),
            (
                ["wonder woman", "mulher maravilha"],
                "Mulher-Maravilha",
                "DC Comics",
                "Mulher-Maravilha e uma heroina da DC Comics, princesa amazona guerreira reconhecida pela tiara, laço da verdade e visual icônico.",
            ),
            (
                ["joker", "coringa"],
                "Coringa",
                "DC Comics",
                "O Coringa e o principal villao do Batman na DC Comics, conhecido pelo visual caricatural, riso perturbador e imprevisibilidade.",
            ),
            # ── Nintendo / Mario ───────────────────────────────────────────────────
            (
                ["mario"],
                "Mario",
                "Super Mario / Nintendo",
                "Mario e o encanador protagonista da franquia Super Mario, associado a aventuras, cogumelos, estrelas e ao universo Nintendo.",
            ),
            (
                ["luigi"],
                "Luigi",
                "Super Mario / Nintendo",
                "Luigi e o irmao de Mario no universo Super Mario, normalmente reconhecido pela roupa verde e pelo papel em jogos de aventura.",
            ),
            (
                ["yoshi", "yoshy", "yoshii"],
                "Yoshi",
                "Super Mario / Nintendo",
                "Yoshi e um personagem do universo Super Mario, conhecido como companheiro de Mario e por sua aparencia de dinossauro amigavel.",
            ),
            (
                ["bowser"],
                "Bowser",
                "Super Mario / Nintendo",
                "Bowser e o rei Koopa e principal antagonista da franquia Super Mario, reconhecido pelo visual de tartaruga gigante com chifres.",
            ),
            (
                ["princess peach", "peach", "princesa peach"],
                "Princesa Peach",
                "Super Mario / Nintendo",
                "Princesa Peach e a governante do Reino dos Cogumelos na franquia Super Mario, reconhecida pelo vestido rosa e coroa.",
            ),
            (
                ["link", "zelda", "hyrule"],
                "Link / Zelda",
                "The Legend of Zelda / Nintendo",
                "Link e o heroi de Hyrule em The Legend of Zelda, uma das franquias mais icônicas da Nintendo, com espada, escudo e traje verde.",
            ),
            (
                ["kirby"],
                "Kirby",
                "Kirby / Nintendo / HAL Laboratory",
                "Kirby e um personagem da Nintendo conhecido pela aparencia arredondada rosa, capacidade de absorver inimigos e universo fofo.",
            ),
            (
                ["pikachu", "pikachou", "pikatchu"],
                "Pikachu",
                "Pokemon / Nintendo, Game Freak e Creatures",
                "Pikachu e o mascote da franquia Pokemon, um rato eletrico amarelo reconhecido mundialmente pelo visual fofo e ataques eletricos.",
            ),
            (
                ["charizard", "charizerd"],
                "Charizard",
                "Pokemon / Nintendo, Game Freak e Creatures",
                "Charizard e um Pokemon do tipo fogo/voador, popular por sua aparencia de dragao e por evoluir de Charmander e Charmeleon.",
            ),
            (
                ["mewtwo", "mewtow"],
                "Mewtwo",
                "Pokemon / Nintendo, Game Freak e Creatures",
                "Mewtwo e um Pokemon lendario geneticamente criado, um dos mais poderosos e reconhecidos da franquia Pokemon.",
            ),
            (
                ["eevee"],
                "Eevee",
                "Pokemon / Nintendo, Game Freak e Creatures",
                "Eevee e um Pokemon famoso por suas multiplas evolucoes, reconhecido pelo visual fofo e pelagem marrom.",
            ),
            (
                ["gengar"],
                "Gengar",
                "Pokemon / Nintendo, Game Freak e Creatures",
                "Gengar e um Pokemon fantasma roxo, um dos mais populares da franquia, conhecido pelo sorriso largo e personalidade travessa.",
            ),
            (
                ["bulbasaur", "bulbasor"],
                "Bulbasaur",
                "Pokemon / Nintendo, Game Freak e Creatures",
                "Bulbasaur e o primeiro Pokemon do Pokedex, do tipo Planta/Veneno, reconhecido pelo bulbo verde nas costas.",
            ),
            (
                ["charmander"],
                "Charmander",
                "Pokemon / Nintendo, Game Freak e Creatures",
                "Charmander e um Pokemon inicial do tipo Fogo, reconhecido pela chama sempre acesa na ponta do rabo.",
            ),
            (
                ["squirtle"],
                "Squirtle",
                "Pokemon / Nintendo, Game Freak e Creatures",
                "Squirtle e um Pokemon inicial do tipo Agua, reconhecido pela casco e o visual de tartaruga azul.",
            ),
            (
                ["snorlax"],
                "Snorlax",
                "Pokemon / Nintendo, Game Freak e Creatures",
                "Snorlax e um Pokemon conhecido por seu tamanho enorme e pelo habito de dormir quase o tempo todo, bloqueando estradas em Kanto.",
            ),
            (
                ["pokemon", "psyduck", "vaporeon", "jolteon", "flareon", "umbreon", "espeon", "glaceon", "leafeon", "sylveon"],
                "Pokemon",
                "Pokemon / Nintendo, Game Freak e Creatures",
                "Pokemon e uma franquia japonesa de jogos, animacao e colecionaveis baseada em criaturas com poderes e evolucoes.",
            ),
            # ── Sega / Sonic ──────────────────────────────────────────────────────
            (
                ["sonic"],
                "Sonic",
                "Sonic the Hedgehog / Sega",
                "Sonic e o mascote da Sega, um porco-espinho azul conhecido pela velocidade extrema, atitude rebelde e aventuras contra o Dr. Eggman.",
            ),
            (
                ["tails", "miles prower"],
                "Tails",
                "Sonic the Hedgehog / Sega",
                "Tails e o melhor amigo de Sonic, uma raposa de duas caudas capaz de voar, reconhecido pelo visual laranja e personalidade gentil.",
            ),
            (
                ["knuckles"],
                "Knuckles",
                "Sonic the Hedgehog / Sega",
                "Knuckles e um echidna vermelho da franquia Sonic, guardiao da Master Emerald, forte e determinado.",
            ),
            (
                ["shadow the hedgehog", "shadow hedgehog"],
                "Shadow",
                "Sonic the Hedgehog / Sega",
                "Shadow e um porco-espinho negro criado por G.U.N. na franquia Sonic, conhecido pelo visual sombrio e pelo uso dos Chaos Emeralds.",
            ),
            # ── Star Wars ─────────────────────────────────────────────────────────
            (
                ["grogu", "baby yoda", "baby yodda"],
                "Grogu",
                "Star Wars / Lucasfilm",
                "Grogu e um personagem de Star Wars popularizado na serie The Mandalorian, conhecido visualmente pela aparencia pequena e orelhas grandes.",
            ),
            (
                ["darth vader", "darthvader"],
                "Darth Vader",
                "Star Wars / Lucasfilm",
                "Darth Vader e um dos maiores viloes da historia do cinema, da saga Star Wars, reconhecido pela armadura negra e respiracao metalica.",
            ),
            (
                ["mandalorian", "din djarin", "mando"],
                "Mandalorian",
                "Star Wars / Lucasfilm",
                "O Mandalorian e o protagonista da serie homônima de Star Wars, guerreiro cuja armadura de Beskar e identidade sao icônicas.",
            ),
            (
                ["r2d2", "r2-d2", "r2 d2", "artoo"],
                "R2-D2",
                "Star Wars / Lucasfilm",
                "R2-D2 e um dos robos mais icônicos de Star Wars, um astromech azul e branco central em toda a saga.",
            ),
            (
                ["c3po", "c-3po", "c 3po", "threepio"],
                "C-3PO",
                "Star Wars / Lucasfilm",
                "C-3PO e o droide protocolar dourado de Star Wars, parceiro de R2-D2 e especialista em comunicacao.",
            ),
            (
                ["yoda"],
                "Mestre Yoda",
                "Star Wars / Lucasfilm",
                "Mestre Yoda e o lendario Grão-Mestre Jedi de Star Wars, reconhecido pelo visual verde pequeno e pela sabedoria invertida em suas falas.",
            ),
            (
                ["stormtrooper", "storm trooper"],
                "Stormtrooper",
                "Star Wars / Lucasfilm",
                "Stormtrooper e o soldado do Imperio/Primeira Ordem em Star Wars, reconhecido pelo uniforme branco e helmet.",
            ),
            # ── Disney ────────────────────────────────────────────────────────────
            (
                ["mickey", "mickey mouse"],
                "Mickey Mouse",
                "Disney",
                "Mickey Mouse e um personagem classico da Disney, reconhecido mundialmente pelas orelhas circulares e personalidade otimista.",
            ),
            (
                ["donald", "donald duck"],
                "Donald Duck",
                "Disney",
                "Donald Duck e um personagem classico da Disney, conhecido pelo temperamento forte, voz marcante e roupa de marinheiro.",
            ),
            (
                ["goofy"],
                "Goofy",
                "Disney",
                "Goofy e um personagem classico da Disney, conhecido pelo comportamento atrapalhado e visual alto e carismatico.",
            ),
            (
                ["minnie", "minnie mouse"],
                "Minnie Mouse",
                "Disney",
                "Minnie Mouse e a personagem feminina classica da Disney, par romantico de Mickey, reconhecida pelo vestido e lacos.",
            ),
            (
                ["stitch", "lilo"],
                "Stitch",
                "Lilo & Stitch / Disney",
                "Stitch e o experimento 626 da Disney, um alienígena azul adoravel de Lilo & Stitch, muito popular em produtos colecionaveis.",
            ),
            (
                ["elsa", "frozen"],
                "Elsa",
                "Frozen / Disney",
                "Elsa e a protagonista de Frozen da Disney, rainha com poderes de gelo reconhecida pelo vestido azul e pela musica Let It Go.",
            ),
            (
                ["moana"],
                "Moana",
                "Moana / Disney",
                "Moana e a protagonista do filme homônimo da Disney, jovem polinesia aventureira com ligacao ao mar.",
            ),
            (
                ["simba", "lion king", "rei leao"],
                "Simba",
                "O Rei Leao / Disney",
                "Simba e o protagonista de O Rei Leao da Disney, um leao que cresce para retomar seu lugar no Ciclo da Vida.",
            ),
            (
                ["toothless", "night fury", "como treinar seu dragao"],
                "Banguela",
                "Como Treinar Seu Dragao / DreamWorks",
                "Banguela (Toothless) e um Furia Negturna, o dragao protagonista de Como Treinar Seu Dragao, reconhecido pelo visual preto e olhos.",
            ),
            # ── Anime / Manga ─────────────────────────────────────────────────────
            (
                ["goku", "gocu", "gokku"],
                "Goku",
                "Dragon Ball / Akira Toriyama",
                "Goku e o protagonista de Dragon Ball, conhecido por artes marciais, transformacoes Super Saiyajin e visual de cabelo pontudo.",
            ),
            (
                ["vegeta", "vegita"],
                "Vegeta",
                "Dragon Ball / Akira Toriyama",
                "Vegeta e o Principe dos Saiyajins em Dragon Ball, reconhecido pelo orgulho guerreiro, cabelo elevado e rivalidade com Goku.",
            ),
            (
                ["gohan"],
                "Gohan",
                "Dragon Ball / Akira Toriyama",
                "Gohan e o filho de Goku em Dragon Ball, metade Saiyajin, com grande potencial ocultado frequentemente pela historia.",
            ),
            (
                ["broly"],
                "Broly",
                "Dragon Ball / Akira Toriyama",
                "Broly e o Saiyajin Lendario de Dragon Ball, conhecido pela forca brutal e pelo visual imponente.",
            ),
            (
                ["naruto"],
                "Naruto",
                "Naruto / Masashi Kishimoto",
                "Naruto e o protagonista da franquia homônima, um ninja com a raposa de nove caldas selada em seu corpo, sonhador e determinado.",
            ),
            (
                ["sasuke"],
                "Sasuke",
                "Naruto / Masashi Kishimoto",
                "Sasuke e o rival e parceiro de Naruto, um Uchiha com o Sharingan, marcado pela vinganca e pelo desenvolvimento ao longo da serie.",
            ),
            (
                ["kakashi"],
                "Kakashi",
                "Naruto / Masashi Kishimoto",
                "Kakashi e o professor da equipe 7 em Naruto, ninja de elite reconhecido pela mascara, cabelo prata e o olho do Sharingan copiado.",
            ),
            (
                ["luffy", "one piece", "monkey d luffy"],
                "Luffy",
                "One Piece / Eiichiro Oda",
                "Luffy e o capitao Chapeu de Palha de One Piece, um piratas elastico do tipo borracha com o sonho de ser o Rei dos Piratas.",
            ),
            (
                ["zoro", "roronoa"],
                "Zoro",
                "One Piece / Eiichiro Oda",
                "Roronoa Zoro e o espadachim da tripulacao de Luffy em One Piece, mestre do estilo tres espadas e fiel ao sonho do seu capitao.",
            ),
            (
                ["saitama", "one punch man"],
                "Saitama",
                "One Punch Man / ONE e Yusuke Murata",
                "Saitama e o protagonista de One Punch Man, um heroi que derrota qualquer inimigo com um unico soco, ironicamente entediado.",
            ),
            (
                ["eren", "titan", "ataque dos titas", "attack on titan"],
                "Eren Yeager",
                "Attack on Titan / Hajime Isayama",
                "Eren Yeager e o protagonista de Attack on Titan, um jovem que descobre segredos sobre os Titans e luta pela sobrevivencia.",
            ),
            (
                ["tanjiro", "demon slayer", "kimetsu no yaiba"],
                "Tanjiro",
                "Demon Slayer / Koyoharu Gotouge",
                "Tanjiro e o protagonista de Demon Slayer, um caçador de demonios que busca curar sua irma transformada em demonio.",
            ),
            (
                ["nezuko"],
                "Nezuko",
                "Demon Slayer / Koyoharu Gotouge",
                "Nezuko e a irma de Tanjiro em Demon Slayer, uma demonia que manteve sua humanidade e luta ao lado de seu irmao.",
            ),
            (
                ["deku", "izuku midoriya", "midoriya", "my hero academia", "boku no hero"],
                "Deku",
                "My Hero Academia / Kohei Horikoshi",
                "Deku (Izuku Midoriya) e o protagonista de My Hero Academia, um jovem sem poderes que herdou o One for All e busca se tornar um heroi.",
            ),
            (
                ["bakugo", "bakugou"],
                "Bakugo",
                "My Hero Academia / Kohei Horikoshi",
                "Bakugo e o rival de Deku em My Hero Academia, com poderes de explosao, personalidade intensa e enorme potencial heroico.",
            ),
            # ── Games ─────────────────────────────────────────────────────────────
            (
                ["creeper", "minecraft"],
                "Creeper / Minecraft",
                "Minecraft / Mojang / Microsoft",
                "Creeper e o inimigo mais icônico de Minecraft, reconhecido pelo visual verde pixelado e por explodir silenciosamente os jogadores.",
            ),
            (
                ["steve", "alex minecraft"],
                "Steve / Minecraft",
                "Minecraft / Mojang / Microsoft",
                "Steve e o personagem padrao de Minecraft, reconhecido pelo visual pixelado e por ser o avatar de milhoes de jogadores.",
            ),
            (
                ["master chief", "halo", "spartan"],
                "Master Chief",
                "Halo / 343 Industries / Microsoft",
                "Master Chief e o protagonista da franquia Halo, um supersoldado Spartan reconhecido pelo capacete verde e viseira dourada.",
            ),
            (
                ["kratos", "god of war"],
                "Kratos",
                "God of War / Santa Monica Studio / Sony",
                "Kratos e o protagonista de God of War, um guerreiro espartano que se tornou Deus da Guerra e enfrenta figuras mitologicas.",
            ),
            (
                ["geralt", "witcher"],
                "Geralt de Rivia",
                "The Witcher / CD Projekt RED",
                "Geralt de Rivia e o protagonista de The Witcher, um caçador de monstros mutante de cabelos brancos com grande habilidade em combate.",
            ),
            (
                ["lara croft", "tomb raider"],
                "Lara Croft",
                "Tomb Raider / Crystal Dynamics / Square Enix",
                "Lara Croft e a protagonista de Tomb Raider, uma arqueologa aventureira conhecida por explorar tumbaas e superar desafios extremos.",
            ),
            (
                ["doom slayer", "doomguy", "doom"],
                "Doom Slayer",
                "Doom / id Software / Bethesda",
                "Doom Slayer e o protagonista sem fala da franquia Doom, reconhecido pela armadura verde e pela missao de acabar com demonios.",
            ),
            # ── Outros icônicos ───────────────────────────────────────────────────
            (
                ["snoopy"],
                "Snoopy",
                "Peanuts / Charles M. Schulz",
                "Snoopy e o cachorro beagle da tira Peanuts, famoso por sua imaginacao e por dormir sobre a casinha.",
            ),
            (
                ["bob esponja", "spongebob", "sponge bob", "patrick"],
                "Bob Esponja",
                "SpongeBob SquarePants / Nickelodeon",
                "Bob Esponja e o protagonista da serie animada da Nickelodeon, um ser amarelo poroso que trabalha como cozinheiro no fundo do mar.",
            ),
        ]
        for terms, character_name, origin, history in known:
            if any(term in name for term in terms):
                return {
                    "is_character": True,
                    "name": character_name,
                    "origin": origin,
                    "short_history": history,
                    "rights_note": "Verifique direitos autorais, marca e licenca antes de vender como produto comercial.",
                }
        return {
            "is_character": False,
            "name": "",
            "origin": "",
            "short_history": "A origem visual do modelo nao foi inferida com seguranca apenas pelo nome do arquivo.",
            "rights_note": "Confirme autoria, licenca do arquivo e permissao de uso comercial antes de vender.",
        }

    def detect_character_context(self, project_name: str) -> dict[str, str | bool]:
        return self._character_context(project_name)

    def _character_origin_text(self, character: dict[str, Any]) -> str:
        if character.get("is_character"):
            return (
                f"{character.get('name', 'Personagem')} - origem: {character.get('origin', 'nao informada')}. "
                f"{character.get('short_history', '')} {character.get('rights_note', '')}"
            ).strip()
        return str(character.get("short_history") or "Origem visual nao inferida com seguranca.")

    def _base_registration_attributes(
        self,
        project_name: str,
        material: str,
        dimensions: str,
        category: str,
        suggested_price: float,
    ) -> list[dict[str, str]]:
        character = self._character_context(project_name)
        attributes = [
            {"label": "Tipo de produto", "value": category},
            {"label": "Material", "value": material},
            {"label": "Processo de fabricacao", "value": "Impressao 3D FDM sob demanda"},
            {"label": "Marca", "value": "Producao propria / sem marca oficial"},
            {"label": "Condicao", "value": "Novo"},
            {"label": "Acabamento", "value": "Linhas de camada podem ser visiveis"},
            {"label": "Personalizacao", "value": "Consultar cores e escala disponiveis"},
            {"label": "Medidas", "value": dimensions},
            {"label": "Prazo de producao", "value": "Informar conforme fila de impressao"},
            {"label": "Conteudo da embalagem", "value": "1 unidade impressa em 3D"},
            {"label": "Uso recomendado", "value": "Decorativo, presente ou uso leve conforme modelo"},
            {"label": "Cuidados", "value": "Evitar calor excessivo, sol prolongado e impacto forte"},
        ]
        if suggested_price > 0:
            attributes.insert(1, {"label": "Preco sugerido", "value": f"R$ {suggested_price:.2f}".replace(".", ",")})
        if character.get("is_character"):
            attributes.extend(
                [
                    {"label": "Personagem/tema", "value": str(character["name"])},
                    {"label": "Universo de origem", "value": str(character["origin"])},
                    {"label": "Licenca comercial", "value": "Verificar permissao de uso antes da venda"},
                ]
            )
        return attributes

    def _full_marketplace_description(
        self,
        product_explanation: str,
        bullets: list[str],
        character: dict[str, str | bool],
    ) -> str:
        parts = [
            product_explanation,
            "",
            "Destaques:",
            *[f"- {item}" for item in bullets],
            "",
            "Observacoes importantes:",
            "- Produto feito sob demanda em impressora 3D.",
            "- Pequenas variacoes de cor, textura e linhas de camada podem ocorrer.",
            "- Confirme cor, escala e prazo antes da compra.",
        ]
        if character.get("is_character"):
            parts.extend(["", f"Contexto do personagem: {character['short_history']}", str(character["rights_note"])])
        return "\n".join(parts)

    def _instagram_caption(
        self,
        product_explanation: str,
        bullets: list[str],
        hashtags: list[str],
        character: dict[str, str | bool],
    ) -> str:
        lines = [
            product_explanation,
            "",
            "Destaques:",
            *[f"- {item}" for item in bullets[:3]],
            "",
            "Quer uma cor ou tamanho especifico? Chame no direct.",
        ]
        if character.get("is_character"):
            lines.extend(["", f"Inspiracao visual: {character['name']} ({character['origin']}). Verifique disponibilidade e licenca de uso."])
        lines.extend(["", " ".join(f"#{tag.replace(' ', '')}" for tag in hashtags[:12])])
        return "\n".join(lines)

    def _hashtags(self, project_name: str, material: str) -> list[str]:
        words = [word for word in project_name.replace("_", " ").replace("-", " ").lower().split() if len(word) > 2]
        base = [*words[:6], "impressao3d", "impressao3dbrasil", material.lower(), "presentepersonalizado", "feitoSobDemanda"]
        return list(dict.fromkeys(base))

    def _market_reference_note(self, category_key: str) -> str:
        if category_key == "keychain":
            return "Referencia de mercado: chaveiros 3D comuns no Brasil aparecem frequentemente entre R$ 5 e R$ 25, variando por lote, tamanho e acabamento."
        if category_key == "small_decor":
            return "Referencia de mercado: itens decorativos pequenos em PLA costumam ficar abaixo de pecas colecionaveis grandes."
        return "Referencia de mercado: preco final deve ser comparado com produtos similares por tamanho, acabamento e nicho."

    def _round_money(self, value: float) -> float:
        return round(value + 1e-9, 2)

    def _round_commercial(self, value: float, category_key: str) -> float:
        if category_key == "keychain":
            if value <= 8.0:
                return 7.9
            if value <= 10.0:
                return 9.9
            if value <= 12.5:
                return 11.9
            if value <= 15.5:
                return 14.9
            if value <= 20.5:
                return 19.9
            return min(24.9, self._round_money(value))
        return self._round_money(value)

    def _tags_for_project(self, project_name: str, material: str) -> list[str]:
        words = [word for word in project_name.replace("_", " ").replace("-", " ").lower().split() if len(word) > 2]
        return list(dict.fromkeys([*words[:8], "impressao 3d", "feito sob encomenda", material.lower(), "presente"]))

    def _dimension_hint(self, manifest: dict[str, Any]) -> str:
        metrics = (manifest.get("metadata") or {}).get("mesh_metrics") or {}
        extents = metrics.get("extents_mm_assumed")
        if not isinstance(extents, list) or len(extents) < 3:
            return "Medidas finais variam conforme escala escolhida."
        try:
            x, y, z = [round(float(value), 1) for value in extents[:3]]
        except (TypeError, ValueError):
            return "Medidas finais variam conforme escala escolhida."
        return f"Medidas aproximadas: {x} x {y} x {z} mm."
