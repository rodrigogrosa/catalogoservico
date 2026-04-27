from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import bcrypt

from app.core.config import get_settings
from app.core.permissions import PERMISSION_DEFINITIONS, ROLE_TEMPLATES, permission_keys, role_map
from app.schemas.auth import AccessModelResponse, AuthUser, UserCreateRequest, UserRecordResponse, UserUpdateRequest


class UserService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.data_dir = self.settings.storage_root / "_system"
        self.data_path = self.data_dir / "users.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.valid_permissions = permission_keys()
        self.roles = role_map()

    def access_model(self) -> AccessModelResponse:
        return AccessModelResponse(permissions=PERMISSION_DEFINITIONS, roles=ROLE_TEMPLATES)

    def list_users(self) -> list[UserRecordResponse]:
        items = [self.to_response(record) for record in self.load_records().values()]
        items.sort(key=lambda item: (item.role != "master", item.display_name.lower(), item.username.lower()))
        return items

    def get_user(self, username: str, provider: str) -> UserRecordResponse | None:
        record = self.load_records().get(self.record_key(username, provider))
        return self.to_response(record) if record else None

    def authenticate_local(self, username: str, password: str) -> AuthUser | None:
        records = self.load_records()
        record = records.get(self.record_key(username, "local"))
        if not record or record.get("status") != "active":
            return None
        stored_hash = str(record.get("password_hash") or "")
        if not stored_hash:
            return None

        # Migração transparente: hash legado SHA256 (64 hex chars sem prefixo)
        if not stored_hash.startswith("$2b$") and not stored_hash.startswith("$2a$"):
            legacy_hash = hashlib.sha256(
                f"{self.settings.auth_token_secret}:{password}".encode("utf-8")
            ).hexdigest()
            if not hmac.compare_digest(stored_hash, legacy_hash):
                return None
            # Promove para bcrypt na primeira autenticação
            record["password_hash"] = self.hash_password(password)
        else:
            if not bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
                return None

        record["last_login_at"] = datetime.now(tz=timezone.utc).isoformat()
        self.save_records({**self.load_records(), self.record_key(username, "local"): record})
        return self.to_auth_user(record)

    def resolve_authenticated_user(self, username: str, provider: str, display_name: str | None = None) -> AuthUser | None:
        if provider == "master" and username == self.settings.master_username:
            return self.master_user()
        record = self.load_records().get(self.record_key(username, provider))
        if record is None or record.get("status") != "active":
            return None
        if display_name and not record.get("display_name"):
            record["display_name"] = display_name
            self.save_records({**self.load_records(), self.record_key(username, provider): record})
        return self.to_auth_user(record)

    def ensure_social_user(self, *, username: str, display_name: str, provider: str) -> AuthUser:
        records = self.load_records()
        key = self.record_key(username, provider)
        record = records.get(key)
        now = datetime.now(tz=timezone.utc).isoformat()
        if record is None:
            record = {
                "id": uuid4().hex,
                "username": username,
                "display_name": display_name,
                "role": "viewer",
                "provider": provider,
                "status": "active",
                "granted_permissions": [],
                "revoked_permissions": [],
                "created_at": now,
                "updated_at": now,
                "last_login_at": now,
            }
        else:
            record["display_name"] = display_name or record.get("display_name") or username
            record["updated_at"] = now
            record["last_login_at"] = now
        records[key] = record
        self.save_records(records)
        return self.to_auth_user(record)

    def create_user(self, payload: UserCreateRequest) -> UserRecordResponse:
        records = self.load_records()
        key = self.record_key(payload.username, payload.provider)
        if key in records or (payload.provider == "master" and payload.username == self.settings.master_username):
            raise ValueError("Já existe um usuário com esse identificador.")
        if payload.provider == "local" and not payload.password:
            raise ValueError("Usuário local exige senha.")
        role = payload.role.strip()
        if role not in self.roles:
            raise ValueError("Papel inválido.")
        now = datetime.now(tz=timezone.utc).isoformat()
        record = {
            "id": uuid4().hex,
            "username": payload.username.strip(),
            "display_name": payload.display_name.strip(),
            "role": role,
            "provider": payload.provider.strip(),
            "status": payload.status.strip(),
            "granted_permissions": self.normalize_permissions(payload.granted_permissions),
            "revoked_permissions": self.normalize_permissions(payload.revoked_permissions),
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
        }
        if payload.password:
            record["password_hash"] = self.hash_password(payload.password)
        records[key] = record
        self.save_records(records)
        return self.to_response(record)

    def update_user(self, username: str, provider: str, payload: UserUpdateRequest) -> UserRecordResponse | None:
        records = self.load_records()
        key = self.record_key(username, provider)
        record = records.get(key)
        if record is None:
            return None
        if payload.display_name is not None:
            record["display_name"] = payload.display_name.strip()
        if payload.role is not None:
            role = payload.role.strip()
            if role not in self.roles:
                raise ValueError("Papel inválido.")
            record["role"] = role
        if payload.status is not None:
            record["status"] = payload.status.strip()
        if payload.granted_permissions is not None:
            record["granted_permissions"] = self.normalize_permissions(payload.granted_permissions)
        if payload.revoked_permissions is not None:
            record["revoked_permissions"] = self.normalize_permissions(payload.revoked_permissions)
        if payload.password is not None:
            password = payload.password.strip()
            if password:
                record["password_hash"] = self.hash_password(password)
            else:
                record.pop("password_hash", None)
        record["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        records[key] = record
        self.save_records(records)
        return self.to_response(record)

    def delete_user(self, username: str, provider: str) -> bool:
        records = self.load_records()
        key = self.record_key(username, provider)
        if key not in records:
            return False
        del records[key]
        self.save_records(records)
        return True

    def load_records(self) -> dict[str, dict[str, Any]]:
        if not self.data_path.exists():
            return {}
        try:
            raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(key): value for key, value in raw.items() if isinstance(value, dict)}

    def save_records(self, records: dict[str, dict[str, Any]]) -> None:
        self.data_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    def master_user(self) -> AuthUser:
        role = self.roles["master"]
        return AuthUser(
            username=self.settings.master_username,
            display_name="Rodrigo Rosa",
            role="master",
            provider="master",
            role_label=role.label,
            permissions=sorted(role.permissions),
            status="active",
        )

    def to_auth_user(self, record: dict[str, Any]) -> AuthUser:
        role_key = str(record.get("role") or "viewer")
        role = self.roles.get(role_key, self.roles["viewer"])
        permissions = set(role.permissions)
        permissions.update(self.normalize_permissions(record.get("granted_permissions", [])))
        permissions.difference_update(self.normalize_permissions(record.get("revoked_permissions", [])))
        return AuthUser(
            username=str(record.get("username") or ""),
            display_name=str(record.get("display_name") or record.get("username") or ""),
            role=role_key,
            provider=str(record.get("provider") or "local"),
            role_label=role.label,
            permissions=sorted(permissions),
            status=str(record.get("status") or "active"),
        )

    def to_response(self, record: dict[str, Any]) -> UserRecordResponse:
        auth_user = self.to_auth_user(record)
        return UserRecordResponse(
            id=str(record.get("id") or ""),
            username=auth_user.username,
            display_name=auth_user.display_name,
            role=auth_user.role,
            role_label=auth_user.role_label or auth_user.role,
            provider=auth_user.provider,
            status=auth_user.status,
            permissions=auth_user.permissions,
            granted_permissions=self.normalize_permissions(record.get("granted_permissions", [])),
            revoked_permissions=self.normalize_permissions(record.get("revoked_permissions", [])),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
            last_login_at=record.get("last_login_at"),
        )

    def normalize_permissions(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return sorted({str(item).strip() for item in values if str(item).strip() in self.valid_permissions})

    def record_key(self, username: str, provider: str) -> str:
        return f"{provider.strip().lower()}::{username.strip().lower()}"

    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
