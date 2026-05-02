from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from typing import Any

from fastapi import UploadFile

from app.core.config import get_settings
from app.schemas.project import (
    ArtifactReference,
    ProcessProjectRequest,
    ProjectBundleResponse,
    ProjectCompareResponse,
    ProjectDetailResponse,
    ProjectQuestion,
    ProjectSummary,
)
from app.services.agents.orchestrator import OrchestratorAgent
from app.services.agents.qa_agent import QATechnicalAgent
from app.services.audit_service import AuditService
from app.services.background_worker import enqueue
from app.services.bundle_service import BundleService
from app.services.checksum_service import ChecksumService
from app.services.format_service import FormatService
from app.services.free_ai_service import FreeAiService
from app.services.knowledge_service import KnowledgeService
from app.services.local_llm_service import LocalLlmService
from app.services.manifest_service import ManifestService
from app.services.mesh_analysis_service import MeshAnalysisService
from app.services.project_naming_service import ProjectNamingService
from app.services.preview_service import PreviewService
from app.services.report_service import ReportService
from app.services.safe_parser_service import SafeParserService
from app.services.sales_service import SalesService
from app.services.slicer_validation_service import SlicerValidationService
from app.services.storage_service import StorageService


logger = logging.getLogger(__name__)

DIRECT_PROJECT_SUFFIXES = {".3mf", ".stl", ".obj", ".step", ".stp", ".amf", ".zip"}
PRINTABLE_ARTIFACT_SUFFIXES = (".gcode", ".3mf", ".stl", ".obj", ".amf", ".step", ".stp")
PRINTABLE_ARTIFACT_PRIORITIES = {".gcode": 0, ".3mf": 1, ".stl": 2, ".obj": 3, ".amf": 4, ".step": 5, ".stp": 6}

class ProjectService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.storage = StorageService()
        self.format_service = FormatService()
        self.knowledge_service = KnowledgeService()
        self.preview_service = PreviewService()
        self.mesh_service = MeshAnalysisService()
        self.report_service = ReportService()
        self.orchestrator = OrchestratorAgent()
        self.qa_agent = QATechnicalAgent()
        self.local_llm = LocalLlmService()
        self.free_ai = FreeAiService(self.settings, llm_service=self.local_llm)
        self.safe_parser = SafeParserService()
        self.sales_service = SalesService()
        self.naming_service = ProjectNamingService(self.local_llm, self.sales_service)
        self.audit = AuditService()
        self.checksum = ChecksumService()
        self.manifest_service = ManifestService()
        self.slicer_validation = SlicerValidationService()
        self.bundle_service = BundleService()
        self._processing_locks: dict[str, threading.Lock] = {}
        self._processing_locks_guard = threading.Lock()

    async def create_project(
        self,
        file: UploadFile | None = None,
        files: list[UploadFile] | None = None,
        requested_name: str | None = None,
    ) -> ProjectDetailResponse:
        uploads = [candidate for candidate in ([file] if file is not None else []) + (files or []) if candidate is not None]
        if not uploads:
            raise ValueError("Nenhum arquivo enviado.")
        if len(uploads) > self.settings.max_project_files:
            raise ValueError(f"O projeto excede o limite de {self.settings.max_project_files} arquivos por upload.")
        project_name = requested_name or self.make_friendly_project_name(
            uploads[0].filename if uploads else "projeto-3d",
            allow_vision=False,
        )
        logger.info(
            "project_create_started",
            extra={
                "project_name": project_name,
                "file_count": len(uploads),
                "filenames": [upload.filename for upload in uploads],
            },
        )
        layout = self.storage.create_project_layout(project_name)
        saved_files = await asyncio.to_thread(
            self.storage.save_uploads_sync,
            uploads,
            layout["folders"]["original"],
        )
        logger.info(
            "project_upload_saved",
            extra={
                "project_name": project_name,
                "storage_path": str(layout["folders"]["root"]),
                "saved_files": [str(path) for path in saved_files],
                "saved_size_bytes": sum(path.stat().st_size for path in saved_files if path.exists()),
            },
        )
        return await asyncio.to_thread(
            self.create_project_from_saved_files,
            saved_files,
            layout,
            project_name,
            None,
        )

    async def create_project_from_url(self, url: str, requested_name: str | None = None) -> ProjectDetailResponse:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Informe uma URL http(s) valida.")
        if self.is_makerworld_model_page(parsed):
            raise ValueError(self.makerworld_page_error())

        project_name = requested_name or self.make_friendly_project_name(
            unquote(parsed.path),
            source_url=url,
            allow_vision=False,
        )
        layout = self.storage.create_project_layout(project_name)
        logger.info(
            "project_import_from_url_started",
            extra={"project_name": project_name, "url": url, "storage_path": str(layout["folders"]["root"])},
        )
        downloaded_file = await asyncio.to_thread(
            self.download_project_url,
            url,
            layout["folders"]["original"],
            project_name,
        )
        return await asyncio.to_thread(
            self.create_project_from_saved_files,
            [downloaded_file],
            layout,
            project_name,
            url,
        )

    def create_project_from_saved_files(
        self,
        saved_files: list[Path],
        layout: dict[str, Any],
        project_name: str,
        origin_url: str | None,
    ) -> ProjectDetailResponse:
        total_size_mb = sum(file_path.stat().st_size for file_path in saved_files if file_path.exists()) / (1024 * 1024)
        logger.info(
            "project_saved_files_received",
            extra={
                "project_name": project_name,
                "saved_file_count": len(saved_files),
                "saved_files": [file_path.name for file_path in saved_files],
                "total_size_mb": round(total_size_mb, 2),
            },
        )
        if total_size_mb > self.settings.max_upload_size_mb:
            raise ValueError(
                f"O upload excede o limite configurado de {self.settings.max_upload_size_mb} MB por projeto."
            )
        logger.info("project_parser_started", extra={"project_name": project_name, "saved_file_count": len(saved_files)})
        parser_result = self.safe_parser.inspect_inputs(saved_files)
        logger.info(
            "project_parser_completed",
            extra={
                "project_name": project_name,
                "parser_error_count": len(parser_result.errors),
                "parser_warning_count": len(parser_result.warnings),
            },
        )
        detected = self.format_service.detect_group(saved_files)
        primary_source = self.select_primary_input(saved_files)
        upload_intake = self.build_upload_intake_summary(primary_source, detected, parser_result)
        logger.info(
            "project_input_inspected",
            extra={
                "project_name": project_name,
                "primary_source": primary_source.name if primary_source else None,
                "source_ecosystem": detected.get("source_ecosystem"),
                "input_formats": detected.get("input_formats"),
                "parser_error_count": len(parser_result.errors),
                "parser_warning_count": len(parser_result.warnings),
            },
        )

        now = datetime.now(tz=timezone.utc)
        previews = self.collect_previews(saved_files, layout["folders"]["previews"])

        # Use embedded metadata name from the file itself (3MF project_settings / XML metadata)
        # as a richer seed before the heuristic name cleaner runs.
        file_meta_name = self.extract_file_metadata_name(saved_files)
        name_seed = file_meta_name or project_name

        if origin_url:
            project_name = self.make_friendly_project_name(
                name_seed,
                previews=previews,
                source_url=origin_url,
                allow_vision=False,
            )
        else:
            project_name = self.make_friendly_project_name(name_seed, previews=previews, allow_vision=False)
        preview_url = self.resolve_preview_url(previews, primary_source)
        try:
            slicer_hints: dict[str, Any] = self.slicer_validation.profile_service.load_profile().get("slicer_safe_defaults", {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("upload_slicer_hints_failed", extra={"project_name": project_name, "error": str(exc)})
            slicer_hints = {}
        manifest = {
            "id": layout["version_name"],
            "name": project_name,
            "slug": layout["slug"],
            "version": layout["version"],
            "status": "failed" if parser_result.errors else "uploaded",
            "input_format": str(detected.get("extension", "unknown")),
            "source_ecosystem": str(detected.get("source_ecosystem", "generic")),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "storage_path": str(layout["folders"]["root"]),
            "original_filename": primary_source.name if primary_source else (saved_files[0].name if saved_files else "unknown"),
            "size_bytes": sum(file_path.stat().st_size for file_path in saved_files if file_path.exists()),
            "input_files": [
                {
                    "name": file_path.name,
                    "path": str(file_path),
                    "suffix": file_path.suffix.lower(),
                    "size_bytes": file_path.stat().st_size,
                    "sha256": self.checksum.sha256(file_path),
                    "role": "primary" if file_path == primary_source else "dependency",
                    "status": "ok",
                }
                for file_path in saved_files
            ],
            "requested_actions": ["upload", "analysis"],
            "findings": [
                *upload_intake.get("findings", []),
                *parser_result.warnings,
            ],
            "risks": [
                *upload_intake.get("risks", []),
                *parser_result.errors,
            ],
            "questions_pending": self.normalize_questions(upload_intake.get("questions", [])),
            "blocking_questions": [question for question in self.normalize_questions(upload_intake.get("questions", [])) if question["kind"] == "blocking"],
            "metadata": {
                "origin_url": origin_url,
                "format_detection": detected,
                "parsing": {
                    "errors": parser_result.errors,
                    "warnings": parser_result.warnings,
                    "detected_files": parser_result.detected_files,
                    "linked_groups": parser_result.linked_groups,
                    **parser_result.metadata,
                },
                "mesh_metrics": {},
                "snapmaker_profile": self.settings.snapmaker_profile_name,
                "llm_runtime": self.local_llm.describe_runtime(),
                "decision_log": [],
                "request_parameters": self.infer_initial_parameters(project_name, detected, parser_result),
                "limitations": parser_result.errors.copy(),
                "user_answers": [],
                "execution_snapshot": {},
                "ai_media_pipeline": {"status": "scheduled", "generated_count": 0, "attempts": []},
                # Slicer safe-defaults: embedded on every import so the user
                # (and the process pipeline) always has the recommended settings
                # pre-computed from the Snapmaker U1 profile.
                "slicer_hints": slicer_hints,
            },
            "processing_stages": self.build_initial_stages(now),
            "stage_metrics": [],
            "decisions": [],
            "artifacts": [],
            "previews": previews,
            "reports": [],
            "logs": [],
            "bundles": [],
            "preview_url": preview_url,
            "manifest": None,
            "snapshot": None,
            "bambu_parameter_equivalence": [],
            "printable_score": self.calculate_printable_score(
                findings=upload_intake.get("findings", []),
                risks=[*upload_intake.get("risks", []), *parser_result.errors],
                blocking_questions=[question for question in self.normalize_questions(upload_intake.get("questions", [])) if question["kind"] == "blocking"],
            ),
        }
        # Defer heavy work so the upload request returns immediately:
        #   1. sales_profile — generated deterministically NOW (all needed info is available at
        #      upload time: name, size, format, ecosystem). AI copy upgrade happens in background.
        #   2. build_manifest/write_manifest — formal Snapmaker manifest JSON (large write)
        #   3. second save_manifest — only needed after #2 completes
        try:
            manifest["sales_profile"] = self.sales_service.build_sales_profile(manifest, allow_llm=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("upload_sales_profile_build_failed", extra={"project_name": project_name, "error": str(exc)})
            manifest["sales_profile"] = None
        manifest["logs"] = [{"label": "processing.log", "path": self.storage.to_storage_url(layout["folders"]["logs"] / "processing.log"), "kind": "log"}]
        self.storage.save_manifest(manifest)
        self.append_log(layout["folders"]["logs"], "Projeto criado e análise inicial concluída.")

        # Snapshot of values captured for the deferred job (avoid closure over
        # mutable `manifest` dict which may be modified by the caller after return).
        _saved_files = list(saved_files)
        _layout_root = layout["folders"]["root"]
        _project_id = layout["version_name"]
        _service_ref = self  # weak reference would be safer, but service is singleton-like

        def _write_formal_manifest() -> None:
            """Build and persist the Snapmaker project_manifest.json in the background."""
            try:
                fresh = _service_ref.storage.load_manifest(_project_id)
                if fresh is None:
                    return
                project_manifest = _service_ref.manifest_service.build_manifest(fresh, _saved_files, [])
                _service_ref.manifest_service.write_manifest(_layout_root, project_manifest)
                fresh["manifest"] = project_manifest
                fresh["has_project_manifest"] = True
                _service_ref.storage.save_manifest(fresh)
                logger.info("project_formal_manifest_written", extra={"project_id": _project_id})
            except Exception as exc:  # noqa: BLE001
                logger.warning("project_formal_manifest_failed", extra={"project_id": _project_id, "error": str(exc)})

        enqueue(f"formal-manifest-{_project_id}", _write_formal_manifest, max_retries=1)
        self.schedule_post_import_ai_enrichment(layout["version_name"])
        logger.info(
            "project_create_completed",
            extra={
                "project_id": layout["version_name"],
                "project_name": project_name,
                "status": manifest["status"],
                "storage_path": str(layout["folders"]["root"]),
            },
        )
        return ProjectDetailResponse(**manifest)

    # ------------------------------------------------------------------
    # Helpers: metadata extraction + smart defaults
    # ------------------------------------------------------------------

    def extract_file_metadata_name(self, saved_files: list[Path]) -> str | None:
        """Return a human-readable name found inside the 3MF/ZIP file, or None."""
        import zipfile, json as _json
        from xml.etree import ElementTree as _ET

        for file_path in saved_files:
            if file_path.suffix.lower() not in {".3mf", ".zip"}:
                continue
            if not zipfile.is_zipfile(file_path):
                continue
            try:
                with zipfile.ZipFile(file_path) as archive:
                    names = archive.namelist()
                    # 1. Bambu/Orca project_settings.config
                    if "Metadata/project_settings.config" in names:
                        try:
                            settings = _json.loads(archive.read("Metadata/project_settings.config").decode("utf-8"))
                            title = str(settings.get("project_name") or "").strip()
                            if title and title.lower() not in {"", "auto", "project", "untitled"}:
                                return title
                        except Exception:
                            pass
                    # 2. model.model root element metadata
                    model_entry = next((n for n in names if n.lower().endswith("/3dmodel.model") or n == "3D/3dmodel.model"), None)
                    if model_entry:
                        try:
                            raw_xml = archive.read(model_entry)
                            if len(raw_xml) < 2 * 1024 * 1024:  # only parse if < 2 MB
                                root = _ET.fromstring(raw_xml)
                                ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
                                for meta in root.findall(".//m:metadata", ns) + root.findall(".//metadata"):
                                    meta_name = (meta.get("name") or "").lower()
                                    if meta_name in {"title", "name", "object_name", "model_name"}:
                                        title = (meta.text or "").strip()
                                        if title:
                                            return title
                        except Exception:
                            pass
            except Exception:
                pass
        return None

    _DECORATIVE_KEYWORDS = frozenset(
        "boneco figura estatua decoracao decorativo estatueta mascara capacete chibi bust stand keychain chaveiro mini".split()
    )
    _FUNCTIONAL_KEYWORDS = frozenset(
        "suporte holder bracket mount enclosure caixa support fixador clip gancho functional parte organizer engrenagem".split()
    )

    def infer_initial_parameters(
        self,
        project_name: str,
        detected: dict[str, Any],
        parser_result: Any,
    ) -> dict[str, Any]:
        """Derive smart process defaults from upload signals so the UI comes pre-filled."""
        from app.schemas.project import ProcessProjectRequest, MaterialPreferences, ColorPreferences, HollowingPreferences, TransformPreferences

        name_lower = project_name.lower()
        ecosystem = str(detected.get("source_ecosystem", "generic")).lower()
        extension = str(detected.get("extension", "unknown")).lower()

        # Detect use-case from name keywords
        has_decorative = any(kw in name_lower for kw in self._DECORATIVE_KEYWORDS)
        has_functional = any(kw in name_lower for kw in self._FUNCTIONAL_KEYWORDS)

        if has_functional and not has_decorative:
            use_case = "functional"
            orientation = "support_economy"
            preset = "functional_part"
        elif has_decorative or not has_functional:
            use_case = "decorative"
            orientation = "aesthetics"
            preset = "quality"
        else:
            use_case = "decorative"
            orientation = "aesthetics"
            preset = "quality"

        # Infer material from name
        material = "PLA"
        for mat in ("PETG", "ASA", "ABS", "TPU", "PA-CF", "PLA"):
            if mat.lower() in name_lower:
                material = mat
                break

        # Bambu projects are typically decorative/character and need conversion
        convert_bambu = ecosystem == "bambu_lab"

        params = ProcessProjectRequest(
            repair_mesh=True,
            adapt_to_snapmaker=True,
            convert_from_bambu=convert_bambu,
            scale_mode="keep",
            unit_mode="auto",
            hollowing=False,
            supports="auto",
            target_material=material,
            objective_preset=preset,
            orientation_priority=orientation,
            target_nozzle_mm=0.4,
            material_preferences=MaterialPreferences(use_case=use_case, prioritize="aesthetics" if use_case == "decorative" else "balanced"),
            color_preferences=ColorPreferences(),
            hollowing_preferences=HollowingPreferences(),
            transform_preferences=TransformPreferences(),
        )
        return params.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Edit project
    # ------------------------------------------------------------------

    def update_project(self, project_id: str, updates: dict[str, Any]) -> ProjectDetailResponse | None:
        manifest = self.storage.load_manifest(project_id)
        if manifest is None:
            return None
        now = datetime.now(tz=timezone.utc).isoformat()
        if "name" in updates and updates["name"]:
            manifest["name"] = str(updates["name"]).strip()
        if "request_parameters" in updates and isinstance(updates["request_parameters"], dict):
            manifest.setdefault("metadata", {})
            manifest["metadata"]["request_parameters"] = updates["request_parameters"]
            # Also sync target_material from request_parameters into sales_profile context
        if "target_material" in updates and updates["target_material"] is not None:
            manifest.setdefault("metadata", {})
            rp = manifest["metadata"].get("request_parameters") or {}
            rp["target_material"] = str(updates["target_material"]).strip().upper()
            manifest["metadata"]["request_parameters"] = rp
        if "sales_profile" in updates and isinstance(updates["sales_profile"], dict):
            manifest["sales_profile"] = updates["sales_profile"]
        manifest["updated_at"] = now
        self.storage.save_manifest(manifest)
        return ProjectDetailResponse(**manifest)

    # ------------------------------------------------------------------
    # Backfill: generate sales_profile for all existing projects
    # ------------------------------------------------------------------

    def backfill_sales_profiles(self) -> dict[str, Any]:
        all_manifests = self.storage.list_manifests()
        fixed = 0
        skipped = 0
        errors_list: list[str] = []
        for summary in all_manifests:
            project_id = summary.get("id")
            if not project_id:
                skipped += 1
                continue
            if summary.get("sales_profile") and isinstance(summary["sales_profile"], dict):
                skipped += 1
                continue
            try:
                manifest = self.storage.load_manifest(project_id)
                if manifest is None:
                    skipped += 1
                    continue
                manifest["sales_profile"] = self.sales_service.build_sales_profile(manifest, allow_llm=False)
                manifest["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
                self.storage.save_manifest(manifest)
                fixed += 1
            except Exception as exc:  # noqa: BLE001
                errors_list.append(f"{project_id}: {exc}")
                skipped += 1
        return {"fixed": fixed, "skipped": skipped, "errors": errors_list}

    def make_friendly_project_name(
        self,
        source_name: str,
        previews: list[dict[str, Any]] | None = None,
        source_url: str | None = None,
        allow_vision: bool = True,
    ) -> str:
        return self.naming_service.generate_name(
            source_name=source_name,
            previews=previews,
            source_url=source_url,
            allow_vision=allow_vision,
        )

    def download_project_url(self, url: str, target_dir: Path, project_name: str) -> Path:
        logger.info("project_download_started", extra={"project_name": project_name, "url": url})
        request = Request(
            url,
            headers={
                "User-Agent": "SnapMaker3d-Studio/0.4 (+local import)",
                "Accept": "application/octet-stream,application/zip,model/3mf,text/html;q=0.2,*/*;q=0.1",
            },
        )
        try:
            with urlopen(request, timeout=45) as response:  # noqa: S310 - URL is user supplied but constrained to http(s) and saved as data.
                content_type = response.headers.get("content-type", "").lower()
                disposition = response.headers.get("content-disposition", "")
                filename = self.filename_from_download(url, disposition, project_name)
                destination = self.storage.unique_upload_path(target_dir / filename)
                max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
                written = 0
                with destination.open("wb") as buffer:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > max_bytes:
                            destination.unlink(missing_ok=True)
                            raise ValueError(f"O download excede o limite de {self.settings.max_upload_size_mb} MB.")
                        buffer.write(chunk)
        except ValueError:
            raise
        except HTTPError as exc:
            logger.warning(
                "project_download_http_error",
                extra={"project_name": project_name, "url": url, "status_code": exc.code, "reason": exc.reason},
            )
            parsed = urlparse(url)
            if exc.code in {401, 403} and self.is_makerworld_host(parsed):
                raise ValueError(self.makerworld_blocked_error()) from exc
            raise ValueError(f"Falha ao baixar o projeto pela URL informada: HTTP {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            logger.warning("project_download_url_error", extra={"project_name": project_name, "url": url, "reason": str(exc.reason)})
            raise ValueError(f"Falha ao baixar o projeto pela URL informada: {exc.reason}") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("project_download_unexpected_error", extra={"project_name": project_name, "url": url})
            raise ValueError(f"Falha ao baixar o projeto pela URL informada: {exc}") from exc

        if destination.suffix.lower() not in DIRECT_PROJECT_SUFFIXES:
            if "zip" in content_type:
                renamed = destination.with_suffix(".zip")
                destination.rename(renamed)
                destination = renamed
            elif "3mf" in content_type or "octet-stream" in content_type:
                renamed = destination.with_suffix(".3mf")
                destination.rename(renamed)
                destination = renamed
            else:
                destination.unlink(missing_ok=True)
                raise ValueError("A URL nao retornou um arquivo 3D direto. Use um link de download do arquivo .3mf/.stl/.zip.")
        logger.info(
            "project_download_completed",
            extra={"project_name": project_name, "url": url, "destination": str(destination), "bytes_written": written},
        )
        return destination

    def is_makerworld_host(self, parsed: Any) -> bool:
        hostname = (parsed.hostname or "").lower()
        return hostname == "makerworld.com" or hostname.endswith(".makerworld.com")

    def is_makerworld_model_page(self, parsed: Any) -> bool:
        path = parsed.path.lower()
        return self.is_makerworld_host(parsed) and "/models/" in path and Path(path).suffix.lower() not in DIRECT_PROJECT_SUFFIXES

    def makerworld_page_error(self) -> str:
        return (
            "Esse link do MakerWorld abre uma pagina do modelo, nao o arquivo 3MF direto. "
            "Mesmo quando ele destaca o botao 'Baixar 3MF' no navegador, a parte depois de # e apenas uma ancora visual "
            "e nao carrega sua sessao logada para o backend. Abra o link no navegador, clique em Baixar 3MF/All files, "
            "baixe o .3mf ou .zip e envie esse arquivo pelo botao Selecionar arquivo. "
            "Se voce tiver uma URL direta que termine em .3mf ou .zip, ela tambem pode ser colada aqui."
        )

    def makerworld_blocked_error(self) -> str:
        return (
            "O MakerWorld bloqueou o download direto por login/Cloudflare. "
            "Isso acontece porque o backend local nao compartilha a sessao logada do seu navegador. "
            "Baixe o arquivo .3mf/.zip no navegador e envie pelo upload do sistema."
        )

    def filename_from_download(self, url: str, disposition: str, project_name: str) -> str:
        if "filename=" in disposition:
            filename = disposition.split("filename=", 1)[1].strip().strip('"')
            if filename:
                return Path(filename).name
        parsed_name = Path(unquote(urlparse(url).path)).name
        if parsed_name and "." in parsed_name:
            return Path(parsed_name).name
        return f"{self.storage.slugify(project_name)}.3mf"

    def build_upload_intake_summary(
        self,
        primary_source: Path | None,
        detected: dict[str, Any],
        parser_result: Any,
    ) -> dict[str, Any]:
        if primary_source is None:
            return {
                "findings": ["Arquivos recebidos, mas nenhum arquivo primário pôde ser selecionado."],
                "risks": ["Projeto sem arquivo primário válido para análise posterior."],
                "questions": [],
            }

        findings = [
            "Upload concluído e arquivos persistidos com versionamento.",
            "A análise geométrica completa será executada ao iniciar o processamento do projeto.",
        ]
        risks: list[str] = []
        questions: list[dict[str, Any]] = []

        source_ecosystem = str(detected.get("source_ecosystem", "generic"))
        input_formats = detected.get("input_formats") or [detected.get("extension", "unknown")]
        findings.append(
            f"Formato principal detectado: {str(detected.get('extension', 'unknown')).upper()} · ecossistema {source_ecosystem}."
        )
        if parser_result.metadata.get("has_obj_bundle"):
            findings.append("Bundle OBJ/MTL/textura detectado e agrupado para processamento conjunto.")
        if "bambu_plate_previews" in detected.get("detected_items", []):
            findings.append("Projeto Bambu com previews/plates detectados; a preservação de layout será tratada na conversão.")
        if parser_result.errors:
            risks.append("O parser detectou problemas de entrada; revise os riscos antes do processamento final.")
        if len(input_formats) > 1:
            findings.append(f"Lote correlacionado com {len(input_formats)} tipos de arquivo detectados.")

        return {
            "findings": findings,
            "risks": risks,
            "questions": questions,
        }

    def list_projects(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        status_filter: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        manifest_summaries = self.storage.list_manifests()
        summaries: list[ProjectSummary] = []
        for manifest in manifest_summaries:
            try:
                summaries.append(ProjectSummary(**manifest))
            except Exception:
                logger.exception(
                    "project_manifest_skipped",
                    extra={
                        "project_id": manifest.get("id"),
                        "storage_path": manifest.get("storage_path"),
                        "name": manifest.get("name"),
                    },
                )
                continue

        # Filter server-side so we never ship the full list over the wire.
        if status_filter:
            summaries = [s for s in summaries if s.status == status_filter]
        if search:
            q = search.lower()
            summaries = [s for s in summaries if q in (s.name or "").lower()]

        total = len(summaries)
        per_page = max(1, min(per_page, 200))
        page = max(1, page)
        pages = max(1, (total + per_page - 1) // per_page)
        offset = (page - 1) * per_page
        page_items = summaries[offset : offset + per_page]

        return {
            "items": page_items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }


    def get_project(self, project_id: str) -> ProjectDetailResponse | None:
        manifest = self.storage.load_manifest(project_id)
        if manifest is None:
            return None
        # GET is a pure read — do NOT write to disk.  persist=False ensures
        # stale-recovery only mutates the in-memory dict; the write is deferred
        # to the next POST/process call that actually changes state.
        self.recover_stale_processing(manifest, persist=False)

        # project_manifest.json availability: read from the stored flag instead
        # of calling is_file() on NFS on every request.  The flag is set to True
        # by the background worker (upload) and the process pipeline.
        if manifest.get("manifest") is None and manifest.get("has_project_manifest"):
            manifest["manifest"] = {
                "project_id": manifest.get("id", ""),
                "project_name": manifest.get("name", ""),
                "slug": manifest.get("slug", ""),
                "version": manifest.get("version", 1),
                "created_at": manifest.get("created_at"),
                "updated_at": manifest.get("updated_at"),
                "source_ecosystem": manifest.get("source_ecosystem", "generic"),
                "pipeline_version": "stored",
            }
        return ProjectDetailResponse(**manifest)

    def delete_project(self, project_id: str) -> bool:
        manifest = self.storage.load_manifest(project_id)
        if manifest is None:
            return False
        if manifest.get("status") == "processing":
            raise ValueError("Nao e seguro excluir um projeto enquanto ele esta em processamento.")
        return self.storage.delete_project(project_id)

    def list_project_versions(self, project_id: str) -> list[ProjectSummary]:
        """Return all stored versions for the same slug as *project_id*, newest first."""
        manifest = self.storage.load_manifest(project_id)
        if manifest is None:
            return []
        slug = manifest.get("slug", "")
        if not slug:
            return []
        summaries: list[ProjectSummary] = []
        for item in self.storage.list_versions_for_slug(slug):
            try:
                summaries.append(ProjectSummary(**item))
            except Exception:
                continue
        return summaries

    def create_reprocess_version(self, project_id: str, request: ProcessProjectRequest) -> ProjectDetailResponse:
        """Copy original files to a new version dir and prepare the manifest.

        The caller is responsible for starting the pipeline on the returned project.
        Raises ``ValueError`` if the project is not found or already processing.
        """
        manifest = self.storage.load_manifest(project_id)
        if manifest is None:
            raise ValueError("Projeto não encontrado.")
        if manifest.get("status") == "processing":
            raise ValueError("Projeto está em processamento. Aguarde concluir antes de reprocessar.")

        new_layout = self.storage.create_reprocess_version(manifest)
        now = datetime.now(tz=timezone.utc)
        new_original = new_layout["folders"]["original"]

        # Rebuild input_files pointing to the new original directory.
        new_input_files = []
        for file_info in manifest.get("input_files", []):
            new_path = new_original / Path(str(file_info.get("path", ""))).name
            if new_path.exists():
                new_input_files.append({**file_info, "path": str(new_path)})

        new_manifest: dict[str, Any] = {
            # Carry over static fields from the source version.
            "name": manifest.get("name"),
            "slug": new_layout["slug"],
            "input_format": manifest.get("input_format"),
            "source_ecosystem": manifest.get("source_ecosystem"),
            "original_filename": manifest.get("original_filename"),
            "size_bytes": manifest.get("size_bytes", 0),
            "findings": list(manifest.get("findings") or []),
            "risks": list(manifest.get("risks") or []),
            "questions_pending": list(manifest.get("questions_pending") or []),
            "blocking_questions": list(manifest.get("blocking_questions") or []),
            "bambu_parameter_equivalence": list(manifest.get("bambu_parameter_equivalence") or []),
            # New version-specific fields.
            "id": new_layout["version_name"],
            "version": new_layout["version"],
            "storage_path": str(new_layout["folders"]["root"]),
            "status": "uploaded",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "input_files": new_input_files,
            "requested_actions": ["reprocess"],
            "processing_stages": self.build_initial_stages(now),
            "stage_metrics": [],
            "decisions": [],
            "artifacts": [],
            "previews": [],
            "preview_url": None,
            "reports": [],
            "logs": [],
            "bundles": [],
            "manifest": None,
            "snapshot": None,
            "printable_score": manifest.get("printable_score"),
            "sales_profile": manifest.get("sales_profile"),
            "metadata": {
                **(manifest.get("metadata") or {}),
                "reprocess_of": project_id,
                "request_parameters": request.model_dump(mode="json"),
            },
        }
        self.storage.save_manifest(new_manifest)
        self.append_log(
            new_layout["folders"]["logs"],
            f"Nova versão criada por reprocessamento a partir de {project_id}.",
        )
        return ProjectDetailResponse(**new_manifest)

    async def process_project(self, project_id: str, request: ProcessProjectRequest) -> None:
        lock = self.project_processing_lock(project_id)
        if not lock.acquire(blocking=False):
            logger.warning("project_process_already_running", extra={"project_id": project_id})
            return

        manifest = self.storage.load_manifest(project_id)
        if manifest is None:
            lock.release()
            return
        self.recover_stale_processing(manifest, persist=True)
        if manifest.get("status") == "processing":
            logger.info("project_process_skipped_already_processing", extra={"project_id": project_id})
            lock.release()
            return

        project_root = Path(manifest["storage_path"])
        folders = {
            "root": project_root,
            "original": project_root / "original",
            "processed": project_root / "processado",
            "export": project_root / "export",
            "reports": project_root / "relatorios",
            "previews": project_root / "previews",
            "logs": project_root / "logs",
        }

        try:
            manifest["status"] = "processing"
            manifest["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
            manifest["requested_actions"] = self.build_requested_actions(request)
            manifest.setdefault("metadata", {})
            manifest["metadata"]["request_parameters"] = request.model_dump(mode="json")

            original_files = sorted(file_path for file_path in folders["original"].iterdir() if file_path.is_file())
            source_file = self.select_primary_input(original_files)
            detected = self.format_service.detect_group(original_files)
            parser_result = self.safe_parser.inspect_inputs(original_files)
            manifest["source_ecosystem"] = str(detected["source_ecosystem"])
            manifest["input_format"] = str(detected["extension"])
            manifest["blocking_questions"] = []
            manifest["stage_metrics"] = []
            context: dict[str, Any] = {
                "project": manifest,
                "request": request,
                "folders": folders,
                "source_file": source_file,
                "source_files": original_files,
                "working_file": str(source_file) if source_file else "",
                "source_ecosystem": manifest["source_ecosystem"],
                "parser_result": {
                    "errors": parser_result.errors,
                    "warnings": parser_result.warnings,
                    "linked_groups": parser_result.linked_groups,
                    "metadata": parser_result.metadata,
                },
            }
            manifest["metadata"]["llm_runtime"] = self.local_llm.describe_runtime()
            manifest["processing_stages"] = self.build_processing_stages(context)
            self.storage.save_manifest(manifest)
            stage_timers: dict[str, Any] = {}

            def update_stage(stage_key: str, stage_label: str, stage_status: str, message: str | None = None) -> None:
                if stage_status == "in_progress":
                    stage_timers[stage_key] = self.audit.start_timer()
                elif stage_key in stage_timers:
                    metric = self.audit.finish_metric(stage_timers.pop(stage_key), stage_key, stage_status)
                    manifest.setdefault("stage_metrics", []).append(metric)

                self.update_stage_status(manifest, stage_key, stage_label, stage_status, message)
                manifest["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
                self.storage.save_manifest(manifest)
                if message:
                    self.append_log(folders["logs"], f"[{stage_key}] {message}", stage_key=stage_key, status=stage_status)

            try:
                outputs = await asyncio.wait_for(
                    asyncio.to_thread(self.orchestrator.run, context, update_stage),
                    timeout=self.settings.stage_timeout_seconds * max(1, len(self.orchestrator.describe_pipeline(context))),
                )
            except TimeoutError:
                manifest["status"] = "failed"
                self.update_stage_status(
                    manifest,
                    "pipeline_timeout",
                    "Timeout operacional",
                    "failed",
                    f"O pipeline excedeu o limite operacional de {self.settings.stage_timeout_seconds} segundos por etapa.",
                )
                manifest["risks"] = [
                    *manifest.get("risks", []),
                    "O processamento foi interrompido por timeout operacional.",
                ]
                self.storage.save_manifest(manifest)
                self.append_log(
                    folders["logs"],
                    "Processamento interrompido por timeout operacional.",
                    stage_key="pipeline_timeout",
                    status="failed",
                )
                return

            flattened_findings = [item for output in outputs for item in output["achados"]]
            flattened_risks = [item for output in outputs for item in output["riscos"]]
            pending_questions = self.normalize_questions([item for output in outputs for item in output["perguntas_ao_usuario"]])
            blocking_questions = [question for question in pending_questions if question["kind"] == "blocking"]
            update_stage("reports", "Geração de relatórios", "in_progress", "Consolidando artefatos e preparando relatórios.")
            generated_artifacts = self.collect_generated_artifacts(outputs)
            preview_assets = self.collect_previews_fast(folders["previews"])
            # Hotfix operacional:
            # - evita travamento do worker em projetos 3MF pesados durante etapa síncrona pós-orquestração
            # - validação detalhada de slicer e extração adicional de previews passam a ser tratadas fora do caminho crítico
            slicer_validations: list[dict[str, Any]] = [
                {
                    "status": "skipped",
                    "findings": [
                        "Validação operacional detalhada foi adiada para pós-processamento assíncrono para manter estabilidade do pipeline."
                    ],
                    "risks": [],
                    "estimates": {},
                }
            ]

            report_payload = {
                "status": "awaiting_user" if blocking_questions else "completed",
                "etapa": "orquestracao_final",
                "achados": flattened_findings,
                "riscos": flattened_risks,
                "perguntas_ao_usuario": pending_questions,
                "acoes_executadas": [action for output in outputs for action in output["acoes_executadas"]],
                "artefatos_gerados": [path for output in outputs for path in output["artefatos_gerados"]],
                "caminho_de_saida": str(project_root),
                "agentes": outputs,
                "knowledge_rules": context.get("knowledge_rules", []),
                "slicer_validations": slicer_validations,
            }
            report_artifacts = self.report_service.write_report_bundle(folders["reports"], report_payload)
            snapshot = self.build_snapshot(original_files, request, outputs, generated_artifacts, flattened_risks)
            snapshot_artifact = self.audit.write_snapshot(folders["reports"], snapshot)
            report_artifacts.append(snapshot_artifact)
            update_stage("reports", "Geração de relatórios", "completed", "Relatórios gerados.")

            context["report_artifacts"] = report_artifacts
            context["pending_questions"] = pending_questions
            update_stage("qa", "Validação final", "in_progress", "Executando validação técnica final.")
            qa_result = self.qa_agent.run(context)
            update_stage("qa", "Validação final", "completed", "Validação final concluída.")
            outputs.append(qa_result)
            flattened_findings.extend(qa_result["achados"])
            flattened_risks.extend(qa_result["riscos"])

            manifest["status"] = "awaiting_user" if blocking_questions else "completed"
            manifest["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
            manifest["findings"] = flattened_findings
            manifest["risks"] = [*flattened_risks, *parser_result.errors]
            manifest["questions_pending"] = pending_questions
            manifest["blocking_questions"] = blocking_questions
            manifest["artifacts"] = generated_artifacts
            manifest["previews"] = self.curate_preview_assets(preview_assets, previews_dir=folders["previews"])
            manifest["preview_url"] = self.resolve_preview_url(manifest["previews"], source_file)
            manifest["reports"] = report_artifacts
            manifest["metadata"]["agent_outputs"] = outputs
            manifest["metadata"]["knowledge_rules"] = context.get("knowledge_rules", [])
            manifest["metadata"]["execution_snapshot"] = snapshot
            manifest["metadata"]["limitations"] = [
                *manifest["metadata"].get("limitations", []),
                *[item for output in outputs for item in output.get("extra", {}).get("limitations", [])],
            ]
            manifest["decisions"] = self.collect_decisions(outputs)
            manifest["bambu_parameter_equivalence"] = self.collect_parameter_equivalence(outputs)
            manifest["snapshot"] = snapshot
            manifest["printable_score"] = qa_result.get("extra", {}).get(
                "printable_score",
                self.calculate_printable_score(flattened_findings, manifest["risks"], blocking_questions),
            )
            manifest["sales_profile"] = self.sales_service.build_sales_profile(manifest)
            manifest["bundles"] = []
            manifest["logs"] = [
                {"label": "processing.log", "path": self.storage.to_storage_url(folders["logs"] / "processing.log"), "kind": "log"},
                {"label": "events.jsonl", "path": self.storage.to_storage_url(folders["logs"] / "events.jsonl"), "kind": "log"},
            ]
            self.finalize_stages(manifest)

            formal_manifest = self.manifest_service.build_manifest(manifest, original_files, generated_artifacts, snapshot=snapshot)
            self.manifest_service.write_manifest(project_root, formal_manifest)
            manifest["manifest"] = formal_manifest
            manifest["has_project_manifest"] = True
            self.storage.save_manifest(manifest)
            self.append_log(folders["logs"], f"Processamento concluído com status {manifest['status']}.", stage_key="project", status=manifest["status"])
            logger.info("Projeto %s processado com status %s", project_id, manifest["status"])
        except Exception as exc:  # noqa: BLE001
            manifest["status"] = "failed"
            manifest["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
            manifest["risks"] = [*manifest.get("risks", []), f"Falha interna no pipeline: {exc}"]
            self.update_stage_status(
                manifest,
                "pipeline_error",
                "Falha de processamento",
                "failed",
                f"O pipeline abortou por exceção interna: {exc}",
            )
            self.storage.save_manifest(manifest)
            self.append_log(
                folders["logs"],
                f"Processamento abortado por exceção interna: {exc}",
                stage_key="pipeline_error",
                status="failed",
            )
            logger.exception("Falha ao processar projeto %s", project_id)
        finally:
            lock.release()

    def project_processing_lock(self, project_id: str) -> threading.Lock:
        with self._processing_locks_guard:
            lock = self._processing_locks.get(project_id)
            if lock is None:
                lock = threading.Lock()
                self._processing_locks[project_id] = lock
            return lock

    def recover_stale_processing(self, manifest: dict[str, Any], persist: bool = False) -> bool:
        if manifest.get("status") != "processing":
            return False

        updated_at = self.parse_manifest_datetime(manifest.get("updated_at"))
        if updated_at is None:
            return False

        age_seconds = (datetime.now(tz=timezone.utc) - updated_at).total_seconds()
        stale_after = max(120, int(self.settings.processing_stale_seconds))
        if age_seconds <= stale_after:
            return False

        now = datetime.now(tz=timezone.utc).isoformat()
        manifest["status"] = "failed"
        manifest["updated_at"] = now
        risks = manifest.setdefault("risks", [])
        risks.append(
            f"Processamento anterior interrompido por timeout operacional ({int(age_seconds)}s sem heartbeat)."
        )
        for stage in manifest.get("processing_stages", []):
            if stage.get("status") == "in_progress":
                stage["status"] = "failed"
                stage["message"] = "Etapa interrompida por timeout/reinício do worker. Reexecute o processamento."
                stage["completed_at"] = now
                if stage.get("started_at"):
                    started = self.parse_manifest_datetime(stage.get("started_at"))
                    if started is not None:
                        stage["duration_ms"] = max(
                            0.0,
                            round((datetime.now(tz=timezone.utc) - started).total_seconds() * 1000, 2),
                        )
                    else:
                        stage["duration_ms"] = 0.0
                else:
                    stage["started_at"] = now
                    stage["duration_ms"] = 0.0
        self.update_stage_status(
            manifest,
            "pipeline_timeout",
            "Timeout operacional",
            "failed",
            "Processamento interrompido por falta de heartbeat; execute novamente.",
        )
        if persist:
            self.storage.save_manifest(manifest)
            try:
                self.append_log(
                    Path(manifest["storage_path"]) / "logs",
                    "Recuperação automática de pipeline travado aplicada.",
                    stage_key="pipeline_timeout",
                    status="failed",
                )
            except Exception:
                logger.exception("project_stale_log_write_failed", extra={"project_id": manifest.get("id")})
        logger.warning(
            "project_processing_recovered_as_stale",
            extra={
                "project_id": manifest.get("id"),
                "age_seconds": round(age_seconds, 2),
                "stale_after_seconds": stale_after,
            },
        )
        return True

    def parse_manifest_datetime(self, raw_value: Any) -> datetime | None:
        if not isinstance(raw_value, str) or not raw_value.strip():
            return None
        value = raw_value.strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def build_requested_actions(self, request: ProcessProjectRequest) -> list[str]:
        actions = []
        if request.repair_mesh:
            actions.append("repair_mesh")
        if request.adapt_to_snapmaker:
            actions.append("adapt_to_snapmaker")
        if request.convert_from_bambu:
            actions.append("convert_from_bambu")
        if request.hollowing or request.hollowing_preferences.enabled:
            actions.append("hollowing")
        actions.append(f"supports:{request.supports}")
        actions.append(f"scale_mode:{request.scale_mode}")
        actions.append(f"unit_mode:{request.unit_mode}")
        actions.append(f"preset:{request.objective_preset}")
        actions.append(f"orientation_priority:{request.orientation_priority}")
        if request.target_material:
            actions.append(f"target_material:{request.target_material}")
        return actions

    def append_log(self, log_dir: Path, message: str, stage_key: str | None = None, status: str | None = None) -> str:
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        path = log_dir / "processing.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")
        self.audit.append_structured_log(
            log_dir,
            {
                "timestamp": timestamp,
                "stage_key": stage_key,
                "status": status,
                "message": message,
            },
        )
        return self.storage.to_storage_url(path)

    def build_initial_stages(self, now: datetime) -> list[dict[str, str | None]]:
        timestamp = now.isoformat()
        return [
            {
                "key": "upload",
                "label": "Upload",
                "status": "completed",
                "message": "Arquivos salvos na pasta original.",
                "started_at": timestamp,
                "completed_at": timestamp,
                "duration_ms": 0.0,
            },
        ]

    def build_processing_stages(self, context: dict[str, Any]) -> list[dict[str, str | None]]:
        now = datetime.now(tz=timezone.utc).isoformat()
        base = self.build_initial_stages(datetime.now(tz=timezone.utc))
        for stage in self.orchestrator.describe_pipeline(context):
            base.append(
                {
                    "key": stage["key"],
                    "label": stage["label"],
                    "status": "pending",
                    "message": None,
                    "started_at": None,
                    "completed_at": None,
                    "duration_ms": None,
                }
            )
        base.extend(
            [
                {
                    "key": "reports",
                    "label": "Geração de relatórios",
                    "status": "pending",
                    "message": None,
                    "started_at": None,
                    "completed_at": None,
                    "duration_ms": None,
                },
                {
                    "key": "qa",
                    "label": "Validação final",
                    "status": "pending",
                    "message": None,
                    "started_at": None,
                    "completed_at": None,
                    "duration_ms": None,
                },
            ]
        )
        for stage in base:
            if stage["status"] == "completed" and stage["started_at"] is None:
                stage["started_at"] = now
                stage["completed_at"] = now
                stage["duration_ms"] = 0.0
        return base

    def update_stage_status(
        self,
        manifest: dict[str, Any],
        stage_key: str,
        stage_label: str,
        stage_status: str,
        message: str | None = None,
    ) -> None:
        stages = manifest.setdefault("processing_stages", [])
        target = next((stage for stage in stages if stage["key"] == stage_key), None)
        now = datetime.now(tz=timezone.utc).isoformat()
        if target is None:
            target = {
                "key": stage_key,
                "label": stage_label,
                "status": stage_status,
                "message": message,
                "started_at": now if stage_status in {"in_progress", "completed", "failed", "skipped", "blocked"} else None,
                "completed_at": now if stage_status in {"completed", "failed", "skipped", "blocked"} else None,
                "duration_ms": 0.0 if stage_status in {"completed", "failed", "skipped", "blocked"} else None,
            }
            stages.append(target)
            return

        target["label"] = stage_label
        target["status"] = stage_status
        if message:
            target["message"] = message
        if stage_status == "in_progress" and not target.get("started_at"):
            target["started_at"] = now
        if stage_status in {"completed", "failed", "skipped", "blocked"}:
            target["started_at"] = target.get("started_at") or now
            target["completed_at"] = now
            if target.get("started_at"):
                started = datetime.fromisoformat(str(target["started_at"]))
                target["duration_ms"] = round((datetime.fromisoformat(now) - started).total_seconds() * 1000, 2)

    def finalize_stages(self, manifest: dict[str, Any]) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        for stage in manifest.get("processing_stages", []):
            if stage["status"] == "pending":
                stage["status"] = "skipped"
                stage["message"] = stage.get("message") or "Etapa não necessária para este projeto."
                stage["completed_at"] = now
                stage["duration_ms"] = 0.0

    def compare_projects(self, base_project_id: str, target_project_id: str) -> ProjectCompareResponse:
        base = self.get_project(base_project_id)
        target = self.get_project(target_project_id)
        if base is None or target is None:
            raise FileNotFoundError("Projeto base ou projeto alvo não encontrado.")

        summary = [
            f"Status: {base.status} -> {target.status}",
            f"Material alvo: {base.metadata.get('request_parameters', {}).get('target_material')} -> {target.metadata.get('request_parameters', {}).get('target_material')}",
            f"Artefatos: {len(base.artifacts)} -> {len(target.artifacts)}",
        ]
        parameter_changes = {
            "supports": [
                base.metadata.get("request_parameters", {}).get("supports"),
                target.metadata.get("request_parameters", {}).get("supports"),
            ],
            "scale_mode": [
                base.metadata.get("request_parameters", {}).get("scale_mode"),
                target.metadata.get("request_parameters", {}).get("scale_mode"),
            ],
            "target_material": [
                base.metadata.get("request_parameters", {}).get("target_material"),
                target.metadata.get("request_parameters", {}).get("target_material"),
            ],
        }
        printable_score_delta = {
            "base": base.printable_score.model_dump() if base.printable_score else None,
            "target": target.printable_score.model_dump() if target.printable_score else None,
        }
        known_paths = {artifact.path for artifact in base.artifacts}
        artifacts_added = [artifact for artifact in target.artifacts if artifact.path not in known_paths]
        return ProjectCompareResponse(
            base_project_id=base_project_id,
            target_project_id=target_project_id,
            summary=summary,
            parameter_changes=parameter_changes,
            printable_score_delta=printable_score_delta,
            artifacts_added=artifacts_added,
        )

    def build_bundle(self, project_id: str) -> ProjectBundleResponse:
        project = self.get_project(project_id)
        if project is None:
            raise FileNotFoundError("Projeto não encontrado.")
        artifact = self.bundle_service.build_project_bundle(Path(project.storage_path))
        return ProjectBundleResponse(bundle=ArtifactReference(**artifact))

    def build_print_file(self, project_id: str) -> dict[str, Any]:
        project = self.get_project(project_id)
        if project is None:
            raise FileNotFoundError("Projeto não encontrado.")
        artifact = self.select_printable_artifact(project.model_dump())
        if artifact is None:
            raise FileNotFoundError("Nenhum arquivo final de impressão encontrado na pasta de exportação.")
        return artifact

    def select_primary_input(self, files: list[Path]) -> Path | None:
        priority = {".3mf": 0, ".stl": 1, ".obj": 2, ".step": 3, ".stp": 4, ".amf": 5, ".ply": 6, ".off": 7}
        candidates = sorted((file_path for file_path in files if file_path.is_file()), key=lambda item: priority.get(item.suffix.lower(), 99))
        return candidates[0] if candidates else None

    def collect_previews(self, files: list[Path], previews_dir: Path) -> list[dict[str, str]]:
        preview_assets = self.preview_service.collect_existing_previews(previews_dir, self.settings.storage_root)
        for file_path in files:
            try:
                preview_assets.extend(
                    self.preview_service.extract_preview_assets(file_path, previews_dir, self.settings.storage_root, file_path.stem)
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "preview_extract_failed",
                    extra={"file_path": str(file_path), "error": str(exc)},
                )
        return self.curate_preview_assets(preview_assets, previews_dir=previews_dir)

    def collect_previews_fast(self, previews_dir: Path) -> list[dict[str, str]]:
        preview_assets = self.preview_service.collect_existing_previews(previews_dir, self.settings.storage_root)
        return self.curate_preview_assets(preview_assets, previews_dir=previews_dir)

    def enrich_previews_with_ai(
        self,
        *,
        previews: list[dict[str, str]],
        previews_dir: Path,
        source_files: list[Path],
        project_name: str,
        detected: dict[str, Any],
    ) -> dict[str, Any]:
        image_candidates: list[Path] = []
        for preview in previews:
            raw_path = str(preview.get("path") or "")
            if not raw_path:
                continue
            if raw_path.startswith("/storage/"):
                candidate = self.settings.storage_root / raw_path.split("/storage/", 1)[1]
            else:
                candidate = Path(raw_path)
            if candidate.exists() and candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                image_candidates.append(candidate)
        if not image_candidates:
            return {"enabled": self.free_ai.is_enabled(), "generated_count": 0, "attempts": []}

        source_context = " ".join(file_path.suffix.lower().lstrip(".") for file_path in source_files if file_path.suffix)
        context_text = (
            f"produto 3D para venda online, ecossistema {detected.get('source_ecosystem', 'generic')}, "
            f"formatos detectados: {source_context or 'desconhecido'}"
        )
        try:
            max_previews = max(1, int(getattr(self.settings, "max_project_previews", 5)))
            raw_count = len([p for p in previews if p.get("kind") != "marketplace_preview"])
            needed = max(1, max_previews - raw_count)
            generated_paths, meta = self.free_ai.generate_marketplace_images(
                source_images=image_candidates,
                output_dir=previews_dir,
                project_name=project_name,
                context_text=context_text,
                count=needed,
            )
            for path in generated_paths:
                previews.append(
                    {
                        "label": path.name,
                        "path": self.storage.to_storage_url(path),
                        "kind": "marketplace_preview",
                    }
                )
            return {
                "enabled": True,
                "generated_count": len(generated_paths),
                **meta,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ai_preview_enrichment_failed",
                extra={"project_name": project_name, "error": str(exc)},
            )
            return {
                "enabled": self.free_ai.is_enabled(),
                "generated_count": 0,
                "attempts": [{"provider": "pipeline", "status": "failed", "error": str(exc)}],
            }

    def resolve_preview_url(self, previews: list[dict[str, Any]] | None, fallback_file: Path | None = None) -> str | None:
        preview_url = self.preview_service.choose_primary_preview_url(previews)
        if preview_url:
            return preview_url
        if fallback_file is None:
            return None
        return self.preview_service.build_preview_url(fallback_file, self.settings.storage_root)

    def curate_preview_assets(self, preview_assets: list[dict[str, Any]], previews_dir: Path | None = None) -> list[dict[str, str]]:
        deduped = {f"{item['label']}::{item['path']}": item for item in preview_assets if item.get("path")}
        curated = self.preview_service.curate_project_previews(
            list(deduped.values()),
            self.settings.storage_root,
            max_items=max(1, int(getattr(self.settings, "max_project_previews", 5))),
        )
        if previews_dir is not None:
            self.preview_service.prune_preview_directory(previews_dir, curated, self.settings.storage_root)
        return curated

    def ensure_preview_fields(
        self,
        manifest: dict[str, Any],
        *,
        persist: bool,
        extract_missing: bool = False,
        generate_marketplace: bool = True,
    ) -> None:
        project_root = Path(manifest["storage_path"])
        previews_dir = project_root / "previews"
        preview_assets = list(manifest.get("previews") or [])
        if extract_missing or not preview_assets:
            preview_assets.extend(self.preview_service.collect_existing_previews(previews_dir, self.settings.storage_root))
        if extract_missing and not preview_assets:
            for file_info in manifest.get("input_files", []):
                file_path = Path(file_info["path"])
                if file_path.exists():
                    preview_assets.extend(
                        self.preview_service.extract_preview_assets(file_path, previews_dir, self.settings.storage_root, file_path.stem)
                    )
        source_files = [Path(file_info["path"]) for file_info in manifest.get("input_files", []) if file_info.get("path")]
        dimensions_mm = self.preview_dimensions_from_manifest(manifest)
        if generate_marketplace:
            try:
                preview_assets.extend(
                    self.preview_service.generate_marketplace_ready_assets(
                        previews_dir,
                        self.settings.storage_root,
                        source_files,
                        dimensions_mm,
                        force=extract_missing,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ensure_preview_marketplace_generation_failed",
                    extra={"project_id": manifest.get("id"), "error": str(exc)},
                )
        if preview_assets:
            manifest["previews"] = self.curate_preview_assets(preview_assets, previews_dir=previews_dir)
        else:
            manifest["previews"] = []
        source_file = None
        for file_info in manifest.get("input_files", []):
            if file_info.get("role") == "primary":
                source_file = Path(file_info["path"])
                break
        if source_file is None and manifest.get("input_files"):
            source_file = Path(manifest["input_files"][0]["path"])
        manifest["preview_url"] = self.resolve_preview_url(manifest.get("previews"), source_file)
        if persist:
            self.storage.save_manifest(manifest)

    def refresh_previews(self, project_id: str) -> ProjectDetailResponse | None:
        manifest = self.storage.load_manifest(project_id)
        if manifest is None:
            return None
        project_root = Path(manifest["storage_path"])
        previews_dir = project_root / "previews"
        source_files = [Path(file_info["path"]) for file_info in manifest.get("input_files", []) if file_info.get("path")]
        dimensions_mm = self.preview_dimensions_from_manifest(manifest)
        preview_assets = self.preview_service.collect_existing_previews(previews_dir, self.settings.storage_root)
        if not preview_assets:
            for file_path in source_files:
                if file_path.exists():
                    preview_assets.extend(
                        self.preview_service.extract_preview_assets(file_path, previews_dir, self.settings.storage_root, file_path.stem)
                    )
        try:
            preview_assets.extend(
                self.preview_service.generate_marketplace_ready_assets(
                    previews_dir,
                    self.settings.storage_root,
                    source_files,
                    dimensions_mm,
                    force=True,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "refresh_preview_marketplace_generation_failed",
                extra={"project_id": project_id, "error": str(exc)},
            )
        ai_media_meta = self.enrich_previews_with_ai(
            previews=preview_assets,
            previews_dir=previews_dir,
            source_files=source_files,
            project_name=str(manifest.get("name") or manifest.get("slug") or "Projeto 3D"),
            detected={
                "source_ecosystem": manifest.get("source_ecosystem", "generic"),
            },
        )
        manifest.setdefault("metadata", {})
        manifest["metadata"]["ai_media_pipeline"] = ai_media_meta
        manifest["previews"] = self.curate_preview_assets(preview_assets, previews_dir=previews_dir)
        self.ensure_preview_fields(manifest, persist=True, extract_missing=False, generate_marketplace=False)
        self.ensure_sales_profile(manifest, persist=True, allow_llm=False)
        manifest_path = Path(manifest["storage_path"]) / "project_manifest.json"
        if manifest_path.exists():
            manifest["manifest"] = self.storage.read_json(manifest_path)
        return ProjectDetailResponse(**manifest)

    def preview_dimensions_from_manifest(self, manifest: dict[str, Any]) -> tuple[float, float, float] | None:
        mesh_metrics = manifest.get("metadata", {}).get("mesh_metrics", {})
        extents = mesh_metrics.get("extents_mm_assumed")
        if not isinstance(extents, list) or len(extents) < 3:
            return None
        try:
            values = tuple(round(float(value), 1) for value in extents[:3])
        except (TypeError, ValueError):
            return None
        if len(values) == 3 and all(value > 0 for value in values):
            return values
        return None

    def ensure_sales_profile(self, manifest: dict[str, Any], *, persist: bool, allow_llm: bool = True) -> None:
        profile = manifest.get("sales_profile")
        version_ok = isinstance(profile, dict) and profile.get("pricing_version") == self.sales_service.PRICING_VERSION
        if version_ok:
            if not allow_llm:
                return  # deterministic profile is sufficient when LLM is not requested
            copy_source = profile.get("copy_source", "deterministic")
            if copy_source in {"ollama", "ia_fallback_chain"}:
                return  # already has AI-generated copy; no need to regenerate
            # copy_source == "deterministic": try LLM upgrade only if any AI provider is active
            runtime = self.free_ai.runtime_preferences() if hasattr(self, "free_ai") else {}
            if not runtime.get("free_ai_enabled", False):
                return  # AI is globally disabled; keep the deterministic profile
        manifest["sales_profile"] = self.sales_service.build_sales_profile(manifest, allow_llm=allow_llm)
        if persist:
            self.storage.save_manifest(manifest)

    def schedule_post_import_ai_enrichment(self, project_id: str) -> None:
        def run() -> None:
            try:
                # Load initial snapshot only to obtain project paths and seed data for AI work.
                initial = self.storage.load_manifest(project_id)
                if initial is None:
                    return
                project_root = Path(initial["storage_path"])
                previews_dir = project_root / "previews"
                source_files = [Path(file_info["path"]) for file_info in initial.get("input_files", []) if file_info.get("path")]
                detected = {"source_ecosystem": initial.get("source_ecosystem", "generic")}
                preview_assets = list(initial.get("previews") or [])
                if not preview_assets:
                    preview_assets = self.preview_service.collect_existing_previews(previews_dir, self.settings.storage_root)
                try:
                    dimensions_mm = self.preview_dimensions_from_manifest(initial)
                    preview_assets.extend(
                        self.preview_service.generate_marketplace_ready_assets(
                            previews_dir,
                            self.settings.storage_root,
                            source_files,
                            dimensions_mm,
                            force=False,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "post_import_marketplace_preview_failed",
                        extra={"project_id": project_id, "error": str(exc)},
                    )
                ai_meta = self.enrich_previews_with_ai(
                    previews=preview_assets,
                    previews_dir=previews_dir,
                    source_files=source_files,
                    project_name=str(initial.get("name") or initial.get("slug") or "Projeto 3D"),
                    detected=detected,
                )
                original_name_source = str(initial.get("original_filename") or initial.get("name") or "")
                refined_name = self.make_friendly_project_name(
                    original_name_source,
                    previews=preview_assets,
                    allow_vision=True,
                )
                curated_previews = self.curate_preview_assets(preview_assets, previews_dir=previews_dir)

                # CRITICAL: Reload manifest fresh before saving to prevent overwriting results from
                # process_project, which may have started or completed while AI work was running above.
                # Only apply AI-enrichment-specific fields to the freshly loaded manifest.
                manifest = self.storage.load_manifest(project_id)
                if manifest is None:
                    return

                # process_project never updates the project name; always apply the AI-refined name.
                if refined_name:
                    manifest["name"] = refined_name
                manifest.setdefault("metadata", {})
                manifest["metadata"]["ai_media_pipeline"] = {"status": "completed", **ai_meta}

                # CRITICAL: Merge all previews (manifest existing + new AI-generated) then
                # re-curate to strictly enforce the max-5-photos rule.
                all_previews = list(manifest.get("previews") or [])
                existing_paths = {p.get("path") for p in all_previews}
                for preview in curated_previews:
                    if preview.get("path") not in existing_paths:
                        all_previews.append(preview)
                manifest["previews"] = self.curate_preview_assets(all_previews)

                manifest["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
                self.storage.save_manifest(manifest)
                self.append_log(project_root / "logs", "Pós-importação: enriquecimento de mídia e copy concluído.", stage_key="post_import_ai", status="completed")
            except Exception as exc:  # noqa: BLE001
                logger.warning("post_import_ai_enrichment_failed", extra={"project_id": project_id, "error": str(exc)})

            # AI copy upgrade is isolated so that preview failures above cannot prevent it.
            # The deterministic ad was already written at upload time; here we only upgrade to
            # AI-generated copy when an AI provider is available.
            try:
                manifest_for_copy = self.storage.load_manifest(project_id)
                if manifest_for_copy is not None:
                    current_copy_source = (manifest_for_copy.get("sales_profile") or {}).get("copy_source", "deterministic")
                    if current_copy_source == "deterministic":
                        self.ensure_sales_profile(manifest_for_copy, persist=True, allow_llm=True)
                        logger.info("post_import_sales_copy_upgraded", extra={"project_id": project_id, "copy_source": (manifest_for_copy.get("sales_profile") or {}).get("copy_source")})
            except Exception as exc:  # noqa: BLE001
                logger.warning("post_import_sales_copy_upgrade_failed", extra={"project_id": project_id, "error": str(exc)})

        worker = enqueue(
            f"post-import-ai-{project_id}",
            run,
            max_retries=1,
        )

    def collect_generated_artifacts(self, outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        generated: list[dict[str, Any]] = []
        for output in outputs:
            for path in output["artefatos_gerados"]:
                file_path = Path(path)
                if not file_path.exists():
                    continue
                generated.append(
                    ArtifactReference(
                        label=file_path.name,
                        path=self.storage.to_storage_url(file_path),
                        kind="artifact",
                        sha256=self.checksum.sha256(file_path),
                        size_bytes=file_path.stat().st_size,
                    ).model_dump()
                )
        deduped = {item["path"]: item for item in generated}
        return list(deduped.values())

    def build_snapshot(
        self,
        original_files: list[Path],
        request: ProcessProjectRequest,
        outputs: list[dict[str, Any]],
        artifacts: list[dict[str, Any]],
        risks: list[str],
    ) -> dict[str, Any]:
        return {
            "inputs": [
                {
                    "name": file_path.name,
                    "path": str(file_path),
                    "suffix": file_path.suffix.lower(),
                    "size_bytes": file_path.stat().st_size,
                    "sha256": self.checksum.sha256(file_path),
                    "role": "primary" if index == 0 else "dependency",
                    "status": "ok",
                }
                for index, file_path in enumerate(original_files)
            ],
            "final_parameters": request.model_dump(mode="json"),
            "agent_outputs": outputs,
            "prompts": self.orchestrator.collect_prompts(),
            "fallbacks": [item for output in outputs for item in output.get("extra", {}).get("fallbacks", [])],
            "risks": risks,
            "artifacts": artifacts,
        }

    def collect_decisions(self, outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        decisions: list[dict[str, Any]] = []
        for output in outputs:
            decisions.extend(output.get("extra", {}).get("decisions", []))
        return decisions

    def collect_parameter_equivalence(self, outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for output in outputs:
            equivalence = output.get("extra", {}).get("parameter_equivalence")
            if equivalence:
                return equivalence
        return []

    def normalize_questions(self, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for question in questions:
            severity = question.get("severity", "medium")
            kind = question.get("kind")
            if kind is None:
                kind = "blocking" if severity == "high" else "recommended"
            normalized.append(
                ProjectQuestion(
                    code=question.get("code", "question"),
                    question=question["question"],
                    reason=question.get("reason", "Ambiguidade relevante detectada."),
                    severity=severity,
                    kind=kind,
                ).model_dump(mode="json")
            )
        return normalized

    def calculate_printable_score(
        self,
        findings: list[str],
        risks: list[str],
        blocking_questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        score = 100
        for risk in risks:
            lowered = risk.lower()
            if any(keyword in lowered for keyword in ("failed", "corrompido", "truncado", "ausente", "vazio", "excede")):
                score -= 25
            else:
                score -= 10
        score -= len(blocking_questions) * 10
        score = max(0, min(100, score))
        level = "low" if score >= 80 else "medium" if score >= 55 else "high"
        blockers = [item["question"] for item in blocking_questions]
        recommendations = []
        if risks:
            recommendations.append("Revisar riscos remanescentes antes da exportação final.")
        if blocking_questions:
            recommendations.append("Responder perguntas bloqueantes antes de tratar a saída como definitiva.")
        return {
            "score": score,
            "level": level,
            "blockers": blockers,
            "warnings": risks[:8],
            "recommendations": recommendations,
        }

    def select_printable_artifact(self, project: dict[str, Any]) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        artifacts = list(project.get("artifacts") or [])
        for artifact in artifacts:
            raw_path = str(artifact.get("path") or "")
            local_path = self.storage_path_from_artifact(raw_path)
            if local_path is None or local_path.suffix.lower() not in PRINTABLE_ARTIFACT_SUFFIXES:
                continue
            artifact_path = raw_path
            if not artifact_path.startswith("/storage/") and not artifact_path.startswith("http"):
                artifact_path = self.storage.to_storage_url(local_path)
            candidates.append(
                {
                    "label": str(artifact.get("label") or local_path.name),
                    "path": artifact_path,
                    "kind": str(artifact.get("kind") or "artifact"),
                    "sha256": artifact.get("sha256") or self.checksum.sha256(local_path),
                    "size_bytes": artifact.get("size_bytes") or local_path.stat().st_size,
                    "_local_path": local_path,
                }
            )

        export_dir = Path(project.get("storage_path", "")) / "export"
        if export_dir.exists():
            for local_path in export_dir.iterdir():
                if not local_path.is_file() or local_path.suffix.lower() not in PRINTABLE_ARTIFACT_SUFFIXES:
                    continue
                candidates.append(
                    {
                        "label": local_path.name,
                        "path": self.storage.to_storage_url(local_path),
                        "kind": "artifact",
                        "sha256": self.checksum.sha256(local_path),
                        "size_bytes": local_path.stat().st_size,
                        "_local_path": local_path,
                    }
                )
        if not candidates:
            return None

        def score(item: dict[str, Any]) -> tuple[int, int, str]:
            local_path = item.get("_local_path")
            suffix = local_path.suffix.lower() if isinstance(local_path, Path) else Path(str(item.get("label", ""))).suffix.lower()
            extension_priority = PRINTABLE_ARTIFACT_PRIORITIES.get(suffix, 99)
            label = str(item.get("label") or "").lower()
            keyword_priority = 0
            if "snapmaker_compatible_final" in label or "_final" in label:
                keyword_priority -= 3
            elif "snapmaker_compatible" in label:
                keyword_priority -= 2
            elif "final" in label:
                keyword_priority -= 1
            return (extension_priority, keyword_priority, label)

        selected = sorted(candidates, key=score)[0]
        selected.pop("_local_path", None)
        return selected

    def storage_path_from_artifact(self, raw_path: str) -> Path | None:
        value = raw_path.strip()
        if not value:
            return None
        if value.startswith("/storage/"):
            candidate = self.settings.storage_root / value.split("/storage/", 1)[1]
            return candidate if candidate.exists() else None
        if value.startswith("http://") or value.startswith("https://"):
            parsed = urlparse(value)
            if "/storage/" in parsed.path:
                candidate = self.settings.storage_root / parsed.path.split("/storage/", 1)[1]
                return candidate if candidate.exists() else None
            return None
        candidate = Path(value)
        return candidate if candidate.exists() else None
