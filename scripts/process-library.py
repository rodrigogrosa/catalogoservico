#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
import sys

from fastapi import UploadFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.append(str(BACKEND_ROOT))

from app.core.config import get_settings
from app.schemas.project import ProcessProjectRequest
from app.services.project_service import ProjectService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Processa uma biblioteca de 3MFs com o perfil conservador do SnapMaker3d Studio.")
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Arquivos ou diretorios para processar. Se omitido, usa ~/Downloads/Projetos 3D.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limita a quantidade de arquivos processados.")
    parser.add_argument("--glob", default="*.3mf", help="Padrao de busca dentro de diretorios.")
    return parser


def collect_files(inputs: list[str], pattern: str) -> list[Path]:
    if not inputs:
        inputs = [str(Path.home() / "Downloads" / "Projetos 3D")]

    files: list[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            files.extend(sorted(item for item in path.glob(pattern) if item.is_file()))
        elif path.is_file():
            files.append(path)
    deduped = sorted({file.resolve() for file in files})
    return deduped


async def process_file(service: ProjectService, path: Path, request: ProcessProjectRequest) -> dict[str, object]:
    with path.open("rb") as handle:
        upload = UploadFile(filename=path.name, file=handle)
        created = await service.create_project(upload, requested_name=path.stem)
    await service.process_project(created.id, request)
    final = service.get_project(created.id)
    return {
        "source": str(path),
        "project_id": created.id,
        "status": final.status if final else "failed",
        "storage_path": final.storage_path if final else "",
        "artifacts": [artifact.model_dump() for artifact in final.artifacts] if final else [],
        "reports": [artifact.model_dump() for artifact in final.reports] if final else [],
        "questions_pending": [question.model_dump() for question in final.questions_pending] if final else [],
        "risks": list(final.risks) if final else ["Falha ao recuperar manifesto apos o processamento."],
    }


async def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    files = collect_files(args.inputs, args.glob)
    if args.limit > 0:
        files = files[: args.limit]

    if not files:
        print("Nenhum arquivo encontrado para processamento.")
        return 1

    service = ProjectService()
    request = ProcessProjectRequest(
        repair_mesh=True,
        adapt_to_snapmaker=True,
        convert_from_bambu=True,
        scale_mode="keep",
        hollowing=False,
        supports="auto",
        target_material=None,
        notes="Batch processing com suportes e primeira camada conservadores para Snapmaker U1.",
    )

    summary: list[dict[str, object]] = []
    total = len(files)
    for index, path in enumerate(files, start=1):
        print(f"[{index}/{total}] {path.name}")
        try:
            result = await process_file(service, path, request)
            summary.append(result)
            print(f"  -> {result['status']} | {result['storage_path']}")
        except Exception as exc:
            summary.append(
                {
                    "source": str(path),
                    "project_id": "",
                    "status": "failed",
                    "storage_path": "",
                    "artifacts": [],
                    "reports": [],
                    "questions_pending": [],
                    "risks": [str(exc)],
                }
            )
            print(f"  -> failed | {exc}")

    settings = get_settings()
    batch_dir = settings.storage_root / "batch_runs"
    batch_dir.mkdir(parents=True, exist_ok=True)
    summary_path = batch_dir / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Resumo salvo em {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
