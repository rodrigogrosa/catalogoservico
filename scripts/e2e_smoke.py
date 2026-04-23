from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
import sys
import tempfile
import uuid
import urllib.error
import urllib.request


DEFAULT_FRONTEND_URL = "https://http--frontend--pqz4rffnktnn.code.run"
DEFAULT_USERNAME = "rodrigogrosa"
DEFAULT_PASSWORD = "Violao2021@"


def build_large_stl(path: Path, size_mb: int = 42) -> Path:
    size = size_mb * 1024 * 1024
    triangles = (size - 84) // 50
    actual_size = 84 + triangles * 50
    with path.open("wb") as handle:
        handle.write(b"0" * 80)
        handle.write(int(triangles).to_bytes(4, "little"))
        remaining = actual_size - 84
        chunk = b"\0" * (1024 * 1024)
        while remaining > 0:
            part = chunk[: min(len(chunk), remaining)]
            handle.write(part)
            remaining -= len(part)
    return path


def json_request(url: str, method: str = "GET", token: str | None = None, payload: dict | None = None) -> tuple[int, dict, dict]:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.status, dict(response.headers), json.loads(response.read().decode())


def multipart_request(url: str, file_path: Path, token: str, project_name: str) -> tuple[int, dict, dict]:
    boundary = f"----SnapMakerBoundary{uuid.uuid4().hex}"
    file_bytes = file_path.read_bytes()
    file_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body = []

    def add_field(name: str, value: str) -> None:
        body.append(f"--{boundary}\r\n".encode())
        body.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.append(f"{value}\r\n".encode())

    def add_file(name: str, filename: str, payload: bytes, content_type: str) -> None:
        body.append(f"--{boundary}\r\n".encode())
        body.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        body.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        body.append(payload)
        body.append(b"\r\n")

    add_field("project_name", project_name)
    add_file("files", file_path.name, file_bytes, file_type)
    body.append(f"--{boundary}--\r\n".encode())
    data = b"".join(body)

    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(data)),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        return response.status, dict(response.headers), json.loads(response.read().decode())


def main() -> int:
    frontend = os.getenv("SNAPMAKER_E2E_FRONTEND_URL", DEFAULT_FRONTEND_URL).rstrip("/")
    username = os.getenv("SNAPMAKER_E2E_USERNAME", DEFAULT_USERNAME)
    password = os.getenv("SNAPMAKER_E2E_PASSWORD", DEFAULT_PASSWORD)

    print(f"[e2e] frontend={frontend}")
    login_status, login_headers, login_payload = json_request(
        f"{frontend}/api/v1/auth/login",
        method="POST",
        payload={"username": username, "password": password},
    )
    assert login_status == 200, "Login falhou"
    token = login_payload["access_token"]
    print(f"[e2e] login ok request_id={login_headers.get('x-request-id')}")

    list_status, list_headers, list_payload = json_request(
        f"{frontend}/api/v1/projects",
        token=token,
    )
    assert list_status == 200, "Listagem falhou"
    print(f"[e2e] list ok items={len(list_payload.get('items', []))} request_id={list_headers.get('x-request-id')}")

    with tempfile.TemporaryDirectory(prefix="snapmaker-e2e-") as temp_dir:
        upload_path = build_large_stl(Path(temp_dir) / "e2e-large-upload.stl")
        project_name = f"E2E Smoke {uuid.uuid4().hex[:8]}"
        upload_status, upload_headers, upload_payload = multipart_request(
            f"{frontend}/api/v1/projects/upload",
            upload_path,
            token,
            project_name,
        )
        assert upload_status == 200, "Upload falhou"
        project_id = upload_payload["id"]
        print(f"[e2e] upload ok project_id={project_id} request_id={upload_headers.get('x-request-id')}")

        detail_status, detail_headers, detail_payload = json_request(
            f"{frontend}/api/v1/projects/{project_id}",
            token=token,
        )
        assert detail_status == 200, "Detalhe do projeto falhou"
        print(f"[e2e] detail ok status={detail_payload.get('status')} request_id={detail_headers.get('x-request-id')}")

        delete_status, delete_headers, delete_payload = json_request(
            f"{frontend}/api/v1/projects/{project_id}",
            method="DELETE",
            token=token,
        )
        assert delete_status == 200, "Exclusão do projeto de teste falhou"
        print(f"[e2e] cleanup ok project_id={delete_payload.get('project_id')} request_id={delete_headers.get('x-request-id')}")

    print("[e2e] success")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"[e2e] http error {exc.code}: {exc.read().decode(errors='ignore')}", file=sys.stderr)
        raise
