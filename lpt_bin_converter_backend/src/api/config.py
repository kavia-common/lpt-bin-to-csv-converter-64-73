"""
Configuration for the LPT.bin → CSV FastAPI backend.

Centralizes environment-driven settings used for production hardening:
- Logging level/format
- Path allow-listing for path-based conversion endpoints
- Upload size limits and temp directory handling

Environment variables (all optional):
- LOG_LEVEL: e.g. DEBUG, INFO, WARNING (default: INFO)
- LPT_API_ALLOWED_INPUT_ROOT: base directory allowed for input_path (default: "")
- LPT_API_ALLOWED_OUTPUT_ROOT: base directory allowed for output_path (default: "")
- LPT_API_MAX_UPLOAD_BYTES: maximum upload size in bytes (default: 52428800 = 50MB)
- LPT_API_TEMP_DIR: temp directory for uploads/outputs (default: system temp)
- LPT_API_CORS_ORIGINS: comma-separated list of origins (default: "*")
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


def _get_env_int(name: str, default: int) -> int:
    """Parse an int environment variable with a safe fallback."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_env_str(name: str, default: str) -> str:
    """Read a string environment variable with a safe fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw


def _parse_cors_origins(raw: str) -> List[str]:
    """Parse comma-separated origins; supports '*'."""
    raw = (raw or "").strip()
    if raw == "" or raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    log_level: str
    allowed_input_root: Optional[Path]
    allowed_output_root: Optional[Path]
    max_upload_bytes: int
    temp_dir: Path
    cors_origins: List[str]


def load_settings() -> Settings:
    """Load settings from environment variables."""
    log_level = _get_env_str("LOG_LEVEL", "INFO").upper()

    allowed_input_root_raw = _get_env_str("LPT_API_ALLOWED_INPUT_ROOT", "").strip()
    allowed_output_root_raw = _get_env_str("LPT_API_ALLOWED_OUTPUT_ROOT", "").strip()

    allowed_input_root = Path(allowed_input_root_raw).resolve() if allowed_input_root_raw else None
    allowed_output_root = Path(allowed_output_root_raw).resolve() if allowed_output_root_raw else None

    max_upload_bytes = _get_env_int("LPT_API_MAX_UPLOAD_BYTES", 50 * 1024 * 1024)

    temp_dir_raw = _get_env_str("LPT_API_TEMP_DIR", "").strip()
    temp_dir = Path(temp_dir_raw).resolve() if temp_dir_raw else Path(tempfile.gettempdir()).resolve()
    temp_dir.mkdir(parents=True, exist_ok=True)

    cors_origins = _parse_cors_origins(_get_env_str("LPT_API_CORS_ORIGINS", "*"))

    return Settings(
        log_level=log_level,
        allowed_input_root=allowed_input_root,
        allowed_output_root=allowed_output_root,
        max_upload_bytes=max_upload_bytes,
        temp_dir=temp_dir,
        cors_origins=cors_origins,
    )


# PUBLIC_INTERFACE
def configure_logging(log_level: str) -> None:
    """Configure standard application logging.

    Args:
        log_level: Logging level name (e.g., "INFO").
    """
    # Avoid duplicate handlers if imported multiple times.
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(log_level)
        return

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
