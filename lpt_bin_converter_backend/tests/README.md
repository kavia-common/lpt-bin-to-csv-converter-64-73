# Backend tests (pytest)

This folder contains:

- Unit tests for the converter (`src/converter/lpt_converter.py`)
- FastAPI integration tests using `fastapi.testclient.TestClient` (no live server)

## Running

From `lpt_bin_converter_backend/`:

```bash
pytest -q
```

## Environment variables

Tests are self-contained and do **not** require real secrets.

For API integration tests, the suite sets these variables via `monkeypatch` and reloads `src.api.main` so settings are applied:

- `LPT_API_ALLOWED_INPUT_ROOT`
- `LPT_API_ALLOWED_OUTPUT_ROOT`
- `LPT_API_TEMP_DIR`
- `LPT_API_MAX_UPLOAD_BYTES`

So you do not need to set them manually.
