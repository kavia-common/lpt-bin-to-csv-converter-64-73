from __future__ import annotations

import importlib
import os
import struct
from pathlib import Path
from typing import Iterable, Sequence, Tuple

import pytest
from fastapi.testclient import TestClient


def _pack_header(magic: int, version: int, record_count: int, reserved: int) -> bytes:
    return struct.pack("<IIII", magic, version, record_count, reserved)


def _pack_record(
    timestamp: float,
    value1: float,
    value2: float,
    status: int,
    flags: int,
    reserved: int,
) -> bytes:
    return struct.pack("<dffIIq", timestamp, value1, value2, status, flags, reserved)


@pytest.fixture()
def lpt_bin_bytes_valid_two_records() -> bytes:
    """A small, fully valid LPT.bin payload with a header and 2 records."""
    header = _pack_header(magic=0xABCD1234, version=1, record_count=2, reserved=0)
    rec1 = _pack_record(1.0, 2.5, 3.5, 7, 9, 11)
    rec2 = _pack_record(2.0, 4.5, 5.5, 8, 10, 12)
    return header + rec1 + rec2


@pytest.fixture()
def lpt_bin_bytes_header_only_record_count_0() -> bytes:
    """Valid header declaring 0 records; no record bytes follow."""
    return _pack_header(magic=1, version=1, record_count=0, reserved=0)


@pytest.fixture()
def make_lpt_bin_bytes() -> callable:
    """Factory to build custom LPT.bin bytes for tests."""

    def _make(*, record_count: int, records: Sequence[Tuple] = (), include_header: bool = True) -> bytes:
        payload = b""
        if include_header:
            payload += _pack_header(magic=0xABCD1234, version=1, record_count=record_count, reserved=0)
        for r in records:
            payload += _pack_record(*r)
        return payload

    return _make


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """
    Create a FastAPI TestClient with isolated environment settings.

    Important: src.api.main loads settings at import time. We therefore set env vars
    first, then reload the module to ensure it picks up the test temp directory.
    """
    # Restrict any path-based conversion to the pytest-provided tmp_path.
    monkeypatch.setenv("LPT_API_ALLOWED_INPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("LPT_API_ALLOWED_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("LPT_API_TEMP_DIR", str(tmp_path / "api_temp"))
    monkeypatch.setenv("LPT_API_MAX_UPLOAD_BYTES", str(1024 * 1024))  # 1MB for tests

    # Reload main to pick up env changes.
    import src.api.main as api_main

    importlib.reload(api_main)

    client = TestClient(api_main.app)
    return client


def _list_files_recursive(p: Path) -> Iterable[Path]:
    if not p.exists():
        return []
    return [x for x in p.rglob("*") if x.is_file()]


@pytest.fixture()
def temp_dir_file_snapshot(tmp_path: Path) -> callable:
    """
    Helper to snapshot files under tmp_path for cleanup assertions.

    Returns a function `snapshot()` that returns a set of file Paths.
    """

    def _snapshot() -> set[Path]:
        return set(_list_files_recursive(tmp_path))

    return _snapshot
