from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
from urllib.error import HTTPError, URLError
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
from app.services.bundle_service import BundleService
from app.services.checksum_service import ChecksumService
from app.services.format_service import FormatService
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
        self.safe_parser = SafeParserService()
        self.sales_service = SalesService()
        self.naming_service = ProjectNamingService(self.local_llm, self.sales_service)
        self.audit = AuditService()
        self.checksum = ChecksumService()
        self.manifest_service = ManifestService()
        self.slicer_validation = SlicerValidationService()
        self.bundle_service = BundleService()

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
        project_name = requested_name or self.make_friendly_project_name(uploads[0].filename if uploads else "projeto-3d")
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

        project_name = requested_name or self.make_friendly_project_name(unquote(parsed.path), source_url=url)
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
        if origin_url:
            project_name = self.make_friendly_project_name(project_name, previews=previews, source_url=origin_url)
        else:
            project_name = self.make_friendly_project_name(project_name, previews=previews)
        preview_url = self.resolve_preview_url(previews, primary_source)
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
                "request_parameters": {},
                "limitations": parser_result.errors.copy(),
                "user_answers": [],
                "execution_snapshot": {},
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
        manifest["sales_profile"] = self.sales_service.build_sales_profile(manifest, allow_llm=False)
        self.storage.save_manifest(manifest)
        self.append_log(layout["folders"]["logs"], "Projeto criado e análise inicial concluída.")
        project_manifest = self.manifest_service.build_manifest(manifest, saved_files, [])
        self.manifest_service.write_manifest(layout["folders"]["root"], project_manifest)
        manifest["manifest"] = project_manifest
        manifest["logs"] = [{"label": "processing.log", "path": self.storage.to_storage_url(layout["folders"]["logs"] / "processing.log"), "kind": "log"}]
        self.storage.save_manifest(manifest)
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

    def make_friendly_project_name(
        self,
        source_name: str,
        previews: list[dict[str, Any]] | None = None,
        source_url: str | None = None,
    ) -> str:
        return self.naming_service.generate_name(source_name=source_name, previews=previews, source_url=source_url)

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

    def list_projects(self) -> list[ProjectSummary]:
        manifests = self.storage.list_manifests()
        summaries: list[ProjectSummary] = []
        for manifest in manifests:
            try:
                self.ensure_preview_fields(manifest, persist=True)
                self.ensure_sales_profile(manifest, persist=True, allow_llm=False)
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
        return summaries

    def get_project(self, project_id: str) -> ProjectDetailResponse | None:
        manifest = self.storage.load_manifest(project_id)
        if manifest is None:
            return None
        self.ensure_preview_fields(manifest, persist=True, extract_missing=True)
        self.ensure_sales_profile(manifest, persist=True, allow_llm=True)
        manifest_path = Path(manifest["storage_path"]) / "project_manifest.json"
        if manifest_path.exists():
            manifest["manifest"] = self.storage.read_json(manifest_path)
        return ProjectDetailResponse(**manifest)

    def delete_project(self, project_id: str) -> bool:
        manifest = self.storage.load_manifest(project_id)
        if manifest is None:
            return False
        if manifest.get("status") == "processing":
            raise ValueError("Nao e seguro excluir um projeto enquanto ele esta em processamento.")
        return self.storage.delete_project(project_id)

    async def process_project(self, project_id: str, request: ProcessProjectRequest) -> None:
        manifest = self.storage.load_manifest(project_id)
        if manifest is None:
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
            generated_artifacts = self.collect_generated_artifacts(outputs)
            preview_assets = self.collect_previews(original_files, folders["previews"])
            for artifact in generated_artifacts:
                if "/storage/" not in artifact["path"]:
                    continue
                artifact_path = self.settings.storage_root / artifact["path"].split("/storage/", 1)[1]
                if artifact_path.exists():
                    preview_assets.extend(
                        self.preview_service.extract_preview_assets(artifact_path, folders["previews"], self.settings.storage_root, artifact_path.stem)
                    )

            slicer_validations: list[dict[str, Any]] = []
            for artifact in generated_artifacts:
                if artifact["path"].endswith(".3mf"):
                    artifact_path = self.settings.storage_root / artifact["path"].split("/storage/", 1)[1]
                    if artifact_path.exists():
                        slicer_validations.append(self.slicer_validation.validate_project_export(artifact_path))

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
            update_stage("reports", "Geração de relatórios", "in_progress", "Montando relatórios técnico e JSON.")
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
            manifest["previews"] = list({f"{item['label']}::{item['path']}": item for item in preview_assets}.values())
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

    def select_primary_input(self, files: list[Path]) -> Path | None:
        priority = {".3mf": 0, ".stl": 1, ".obj": 2, ".step": 3, ".stp": 4, ".amf": 5, ".ply": 6, ".off": 7}
        candidates = sorted((file_path for file_path in files if file_path.is_file()), key=lambda item: priority.get(item.suffix.lower(), 99))
        return candidates[0] if candidates else None

    def collect_previews(self, files: list[Path], previews_dir: Path) -> list[dict[str, str]]:
        preview_assets = self.preview_service.collect_existing_previews(previews_dir, self.settings.storage_root)
        for file_path in files:
            preview_assets.extend(
                self.preview_service.extract_preview_assets(file_path, previews_dir, self.settings.storage_root, file_path.stem)
            )
        deduped = {f"{item['label']}::{item['path']}": item for item in preview_assets}
        return list(deduped.values())

    def resolve_preview_url(self, previews: list[dict[str, Any]] | None, fallback_file: Path | None = None) -> str | None:
        preview_url = self.preview_service.choose_primary_preview_url(previews)
        if preview_url:
            return preview_url
        if fallback_file is None:
            return None
        return self.preview_service.build_preview_url(fallback_file, self.settings.storage_root)

    def ensure_preview_fields(
        self,
        manifest: dict[str, Any],
        *,
        persist: bool,
        extract_missing: bool = False,
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
        if preview_assets:
            manifest["previews"] = list({f"{item['label']}::{item['path']}": item for item in preview_assets}.values())
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

    def ensure_sales_profile(self, manifest: dict[str, Any], *, persist: bool, allow_llm: bool = True) -> None:
        profile = manifest.get("sales_profile")
        if (
            isinstance(profile, dict)
            and profile.get("pricing_version") == self.sales_service.PRICING_VERSION
            and (not allow_llm or profile.get("copy_source") == "ollama")
        ):
            return
        manifest["sales_profile"] = self.sales_service.build_sales_profile(manifest, allow_llm=allow_llm)
        if persist:
            self.storage.save_manifest(manifest)

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
