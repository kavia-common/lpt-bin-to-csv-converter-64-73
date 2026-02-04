from __future__ import annotations

import io
import struct
from pathlib import Path

import pytest

from src.converter.lpt_converter import (
    LPTBinParserError,
    ParserConfig,
    convert_lpt_bin_to_csv,
    parse_header,
    parse_record,
    stream_records,
)


def _read_csv_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_parse_header_valid(lpt_bin_bytes_valid_two_records: bytes) -> None:
    fh = io.BytesIO(lpt_bin_bytes_valid_two_records)
    cfg = ParserConfig(skip_header=False)

    header = parse_header(fh, cfg)

    assert header["magic_number"] == 0xABCD1234
    assert header["version"] == 1
    assert header["record_count"] == 2
    assert header["reserved"] == 0


def test_parse_header_incomplete_raises() -> None:
    cfg = ParserConfig()
    fh = io.BytesIO(b"\x00\x01")  # far less than 16 bytes
    with pytest.raises(LPTBinParserError, match=r"Incomplete header: expected"):
        parse_header(fh, cfg)


def test_parse_header_struct_error_raises() -> None:
    # Invalid struct format should trigger struct.error -> LPTBinParserError
    cfg = ParserConfig(header_format="<Z")  # invalid format char
    fh = io.BytesIO(b"\x00" * 16)
    with pytest.raises(LPTBinParserError, match=r"Failed to parse header"):
        parse_header(fh, cfg)


def test_parse_record_valid() -> None:
    cfg = ParserConfig()
    record_bytes = struct.pack("<dffIIq", 1.0, 2.0, 3.0, 4, 5, 6)

    record = parse_record(record_bytes, cfg)

    assert record == (1.0, 2.0, 3.0, 4, 5, 6)


def test_parse_record_incomplete_returns_none() -> None:
    cfg = ParserConfig()
    record_size = struct.calcsize(cfg.record_format)

    record = parse_record(b"\x00" * (record_size - 1), cfg)

    assert record is None


def test_stream_records_respects_max_records(make_lpt_bin_bytes) -> None:
    cfg = ParserConfig(skip_header=True)
    # Provide 3 records in the payload; request only 2.
    payload = make_lpt_bin_bytes(
        record_count=0,
        include_header=False,
        records=[
            (1.0, 1.0, 1.0, 1, 1, 1),
            (2.0, 2.0, 2.0, 2, 2, 2),
            (3.0, 3.0, 3.0, 3, 3, 3),
        ],
    )
    fh = io.BytesIO(payload)

    records = list(stream_records(fh, cfg, max_records=2))

    assert len(records) == 2
    assert records[0][0] == 1.0
    assert records[1][0] == 2.0


def test_stream_records_incomplete_tail_is_ignored(make_lpt_bin_bytes) -> None:
    cfg = ParserConfig(skip_header=True)
    record_size = struct.calcsize(cfg.record_format)

    good_record = struct.pack("<dffIIq", 1.0, 2.0, 3.0, 4, 5, 6)
    payload = good_record + (b"\xFF" * (record_size - 3))  # incomplete second record
    fh = io.BytesIO(payload)

    records = list(stream_records(fh, cfg, max_records=None))

    assert records == [(1.0, 2.0, 3.0, 4, 5, 6)]


def test_convert_valid_with_header_record_count_limit(
    tmp_path: Path, lpt_bin_bytes_valid_two_records: bytes
) -> None:
    inp = tmp_path / "input.bin"
    out = tmp_path / "output.csv"
    inp.write_bytes(lpt_bin_bytes_valid_two_records)

    result = convert_lpt_bin_to_csv(str(inp), str(out), ParserConfig(skip_header=False))

    assert result["success"] is True
    assert result["records_converted"] == 2
    assert out.exists()

    lines = _read_csv_lines(out)
    # header + 2 data rows
    assert len(lines) == 3
    assert lines[0].split(",") == ["timestamp", "value1", "value2", "status", "flags", "reserved"]


def test_convert_header_only_results_in_csv_header_no_rows(
    tmp_path: Path, lpt_bin_bytes_header_only_record_count_0: bytes
) -> None:
    inp = tmp_path / "input.bin"
    out = tmp_path / "output.csv"
    inp.write_bytes(lpt_bin_bytes_header_only_record_count_0)

    result = convert_lpt_bin_to_csv(str(inp), str(out), ParserConfig(skip_header=False))

    assert result["success"] is True
    assert result["records_converted"] == 0

    lines = _read_csv_lines(out)
    assert len(lines) == 1
    assert lines[0].split(",") == ["timestamp", "value1", "value2", "status", "flags", "reserved"]


def test_convert_incomplete_header_falls_back_to_raw_records(tmp_path: Path) -> None:
    # When header parsing fails, converter seeks(0) and sets skip_header=True.
    cfg = ParserConfig(skip_header=False)

    # Provide fewer than HEADER_SIZE bytes, then a full record.
    # This ensures header parsing fails, but raw record parsing succeeds from position 0.
    record = struct.pack("<dffIIq", 1.0, 2.0, 3.0, 4, 5, 6)
    inp = tmp_path / "input.bin"
    out = tmp_path / "output.csv"
    inp.write_bytes(b"\x00" * 5 + record)

    result = convert_lpt_bin_to_csv(str(inp), str(out), cfg)

    assert result["success"] is True
    assert result["records_converted"] == 1
    lines = _read_csv_lines(out)
    assert len(lines) == 2


def test_convert_missing_input_raises(tmp_path: Path) -> None:
    out = tmp_path / "output.csv"
    with pytest.raises(FileNotFoundError):
        convert_lpt_bin_to_csv(str(tmp_path / "nope.bin"), str(out), ParserConfig())


def test_convert_input_path_not_file_raises(tmp_path: Path) -> None:
    # Create a directory and pass it as input_path.
    inp_dir = tmp_path / "input_dir"
    inp_dir.mkdir()
    out = tmp_path / "output.csv"

    with pytest.raises(ValueError, match="Input path is not a file"):
        convert_lpt_bin_to_csv(str(inp_dir), str(out), ParserConfig())


def test_convert_cleans_partial_output_on_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inp = tmp_path / "input.bin"
    out = tmp_path / "output.csv"
    # content doesn't matter; we'll force an exception during CSV write
    inp.write_bytes(b"\x00" * 16)

    # Patch csv.writer to raise when writing the header, ensuring output file gets created then error happens.
    import src.converter.lpt_converter as mod

    real_csv_writer = mod.csv.writer

    class _ExplodingWriter:
        def writerow(self, row):  # noqa: D401 - intentionally minimal for test
            raise RuntimeError("boom")

    def _writer_factory(*args, **kwargs):
        _ = (args, kwargs)
        return _ExplodingWriter()

    monkeypatch.setattr(mod.csv, "writer", _writer_factory)

    with pytest.raises(RuntimeError, match="boom"):
        convert_lpt_bin_to_csv(str(inp), str(out), ParserConfig(skip_header=True))

    # The converter should have removed the partial output file.
    assert not out.exists()

    # Restore (good practice; though monkeypatch fixture restores automatically).
    monkeypatch.setattr(mod.csv, "writer", real_csv_writer)
