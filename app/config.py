"""Application configuration, secure credential storage, and validated settings persistence."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

APP_NAME = "Sortify"
APP_TAGLINE = "Order, by design"
APP_VERSION = "1.0.0"
APP_ORGANIZATION = "Sortify"
SETTINGS_SCHEMA_VERSION = 2

VALID_NAMING_STYLES = (
    "Underscore_Separated",
    "Readable With Spaces",
    "Title Case",
    "Hyphen-Separated",
    "camelCase",
)

VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def migrate_legacy_data_dir(sortify_dir: Path, legacy_dir: Path) -> bool:
    """Safely migrate settings and history from legacy RenovaAI directory without deleting originals."""
    if not legacy_dir.exists() or not legacy_dir.is_dir():
        return False
    migrated = False
    try:
        sortify_dir.mkdir(parents=True, exist_ok=True)
        for fname in ("settings.json", "history.sqlite3"):
            src = legacy_dir / fname
            dst = sortify_dir / fname
            if src.is_file() and not dst.exists():
                # Copy via temp file for atomicity while leaving original legacy file intact
                tmp_dst = sortify_dir / f".migrating-{fname}"
                shutil.copy2(src, tmp_dst)
                os.replace(tmp_dst, dst)
                migrated = True
    except OSError:
        pass
    return migrated


def _resolve_app_dir() -> Path:
    custom = os.environ.get("SORTIFY_DATA_DIR", "").strip()
    if custom:
        candidate = Path(custom).expanduser().resolve()
    else:
        base = Path(os.environ.get("APPDATA", Path.home()))
        candidate = base / "Sortify"
        legacy_dir = base / "RenovaAI"
        if not candidate.exists() and legacy_dir.exists():
            migrate_legacy_data_dir(candidate, legacy_dir)

    try:
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "Sortify"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return fallback


APP_DIR = _resolve_app_dir()
CONFIG_PATH = APP_DIR / "settings.json"
DB_PATH = APP_DIR / "history.sqlite3"
LOG_PATH = APP_DIR / "sortify.log"

KEYRING_SERVICE = "Sortify"
LEGACY_KEYRING_SERVICE = "RenovaAI"
KEYRING_USER = "ai-provider-api-key"


def _clamp_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        if isinstance(value, bool):
            return default
        parsed = int(value)  # type: ignore[arg-type]
        return max(minimum, min(maximum, parsed))
    except (TypeError, ValueError):
        return default


def _to_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "1", "yes", "on"}:
            return True
        if low in {"false", "0", "no", "off"}:
            return False
    return default


def validate_api_url(url: str) -> tuple[bool, str]:
    """Validate that an API base URL is well-formed and safe."""
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned:
        return False, "API base URL cannot be empty."
    try:
        parsed = urlparse(cleaned)
    except ValueError:
        return False, "API base URL is malformed."
    if parsed.scheme not in {"https", "http"}:
        return False, "The API base URL must start with https:// or http://."
    if not parsed.netloc or not parsed.hostname:
        return False, "The API base URL must include a valid hostname."
    host = parsed.hostname.lower()
    # Block cloud instance metadata link-local addresses (SSRF protection)
    if host.startswith("169.254.") or host in {
        "metadata.google.internal",
        "100.100.100.200",
        "fd00:ec2::254",
    }:
        return False, "Link-local cloud metadata addresses are not permitted."
    return True, cleaned


def is_loopback_url(url: str) -> bool:
    """Return True if the URL points to localhost / loopback."""
    try:
        host = (urlparse(url).hostname or "").lower()
        return host in {"localhost", "127.0.0.1", "::1"} or host.startswith("127.")
    except ValueError:
        return False


@dataclass
class Settings:
    schema_version: int = SETTINGS_SCHEMA_VERSION
    provider: str = "OpenAI-compatible API"
    api_base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str = ""  # loaded from OS credential storage; never written to settings.json
    naming_style: str = "Underscore_Separated"
    max_filename_length: int = 100
    include_subfolders: bool = False
    max_extract_chars: int = 12000
    request_timeout_seconds: int = 45
    max_concurrent_requests: int = 3
    external_ai_consent: bool = False
    history_retention_days: int = 365
    dark_mode: bool = True
    reduced_motion: bool = False
    cache_enabled: bool = True
    default_folder: str = ""
    prepend_date: bool = False
    custom_prefix: str = ""
    organize_by_category: bool = False
    confirm_before_apply: bool = True
    skip_symlinks: bool = True
    log_level: str = "INFO"
    recovered_from_corrupt: bool = field(default=False, repr=False, compare=False)
    corrupt_backup_path: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        self.sanitize()

    def sanitize(self) -> None:
        """Normalize and clamp all configuration values to safe ranges."""
        self.schema_version = _clamp_int(
            self.schema_version, SETTINGS_SCHEMA_VERSION, 1, 100
        )
        self.provider = str(self.provider or "OpenAI-compatible API").strip()[:100]
        ok, cleaned_url = validate_api_url(
            str(self.api_base_url or "https://api.openai.com/v1")
        )
        self.api_base_url = cleaned_url if ok else "https://api.openai.com/v1"
        self.model = str(self.model or "gpt-4o-mini").strip()[:120] or "gpt-4o-mini"
        self.api_key = str(self.api_key or "").strip()

        if self.naming_style not in VALID_NAMING_STYLES:
            self.naming_style = "Underscore_Separated"

        self.max_filename_length = _clamp_int(self.max_filename_length, 100, 20, 220)
        self.include_subfolders = _to_bool(self.include_subfolders, False)
        self.max_extract_chars = _clamp_int(self.max_extract_chars, 12000, 500, 100000)
        self.request_timeout_seconds = _clamp_int(
            self.request_timeout_seconds, 45, 5, 300
        )
        self.max_concurrent_requests = _clamp_int(self.max_concurrent_requests, 3, 1, 8)
        self.external_ai_consent = _to_bool(self.external_ai_consent, False)
        self.history_retention_days = _clamp_int(
            self.history_retention_days, 365, 1, 3650
        )
        self.dark_mode = _to_bool(self.dark_mode, True)
        self.reduced_motion = _to_bool(self.reduced_motion, False)
        self.cache_enabled = _to_bool(self.cache_enabled, True)
        self.default_folder = str(self.default_folder or "").strip()
        self.prepend_date = _to_bool(self.prepend_date, False)
        self.custom_prefix = str(self.custom_prefix or "").strip()[:30]
        self.organize_by_category = _to_bool(self.organize_by_category, False)
        self.confirm_before_apply = _to_bool(self.confirm_before_apply, True)
        self.skip_symlinks = _to_bool(self.skip_symlinks, True)
        lvl = str(self.log_level or "INFO").strip().upper()
        self.log_level = lvl if lvl in VALID_LOG_LEVELS else "INFO"

    @classmethod
    def load(cls, config_path: Path | None = None) -> Settings:
        target_path = Path(config_path) if config_path else CONFIG_PATH
        recovered = False
        backup_str = ""
        if target_path.exists():
            try:
                raw_text = target_path.read_text(encoding="utf-8")
                data = json.loads(raw_text)
                if not isinstance(data, dict):
                    raise TypeError("Top-level settings JSON must be an object.")
                allowed = {f.name for f in fields(cls)} - {
                    "api_key",
                    "recovered_from_corrupt",
                    "corrupt_backup_path",
                }
                obj = cls(**{k: v for k, v in data.items() if k in allowed})
                obj.schema_version = SETTINGS_SCHEMA_VERSION
            except (OSError, ValueError, TypeError) as exc:
                logging.getLogger(__name__).warning(
                    "Corrupt or unreadable settings file %s (%s); backing up and restoring defaults.",
                    target_path,
                    exc,
                )
                try:
                    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                    backup = target_path.with_name(f"settings.corrupt-{ts}.json.bak")
                    shutil.copy2(target_path, backup)
                    backup_str = str(backup)
                    recovered = True
                except OSError:
                    recovered = True
                obj = cls()
                obj.recovered_from_corrupt = recovered
                obj.corrupt_backup_path = backup_str
        else:
            obj = cls()

        try:
            import keyring

            key = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
            if not key:
                legacy_key = keyring.get_password(LEGACY_KEYRING_SERVICE, KEYRING_USER)
                if legacy_key:
                    key = legacy_key
                    # Migrate key to Sortify keyring service seamlessly
                    try:
                        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, legacy_key)
                    except Exception as exc:  # noqa: BLE001
                        logging.getLogger(__name__).debug("Legacy keyring migration skipped: %s", exc)
            obj.api_key = (key or "").strip()
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).debug("Keyring read unavailable: %s", exc)
            obj.api_key = ""
        return obj

    def save(self, config_path: Path | None = None) -> None:
        self.sanitize()
        self.schema_version = SETTINGS_SCHEMA_VERSION
        target_path = Path(config_path) if config_path else CONFIG_PATH
        target_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            k: v
            for k, v in self.__dict__.items()
            if k not in {"api_key", "recovered_from_corrupt", "corrupt_backup_path"}
        }

        # Atomic write with restrictive permissions; preserves existing file if write fails
        serialized = json.dumps(data, indent=2, ensure_ascii=False)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".settings-", suffix=".tmp", dir=str(target_path.parent)
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(serialized)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
            os.replace(tmp_path, target_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

        try:
            import keyring

            if self.api_key:
                keyring.set_password(KEYRING_SERVICE, KEYRING_USER, self.api_key)
            else:
                for svc in (KEYRING_SERVICE, LEGACY_KEYRING_SERVICE):
                    try:
                        keyring.delete_password(svc, KEYRING_USER)
                    except Exception as exc:  # noqa: BLE001
                        logging.getLogger(__name__).debug("Keyring delete skipped for %s: %s", svc, exc)
        except Exception as e:
            if self.api_key:
                raise RuntimeError(
                    "Could not save the API key to Windows Credential Manager / OS keyring. "
                    "Install requirements and verify an available OS credential backend. "
                    "No plaintext key was saved."
                ) from e
            logging.getLogger(__name__).debug("Keyring cleanup skipped: %s", e)
