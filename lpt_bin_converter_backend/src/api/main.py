"""
FastAPI Application for LPT.bin to CSV Converter

Provides REST API endpoints for converting LPT.bin binary files to CSV format.
Includes file upload support, path-based conversion, and comprehensive API documentation.

Production hardening notes:
- Path-based endpoints validate and optionally restrict input/output roots via env settings.
- Upload endpoint streams file to disk with a configurable size limit (no full in-memory reads).
- Temporary upload/output files are created in a safe temp directory and cleaned up post-response.
- Logging and CORS are environment-configurable.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, UploadFile, File, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from starlette.background import BackgroundTask

from .config import load_settings, configure_logging
from .security import resolve_and_validate_path, sanitize_download_filename
from .models import (
    ConversionRequest,
    ConversionResponse,
    ErrorResponse,
    HealthResponse,
    ParserConfigRequest,
)
from ..converter.lpt_converter import (
    convert_lpt_bin_to_csv,
    ParserConfig,
    LPTBinParserError,
)

settings = load_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

# OpenAPI metadata
openapi_tags = [
    {"name": "health", "description": "Health check and service status endpoints"},
    {"name": "conversion", "description": "LPT.bin to CSV conversion operations"},
    {"name": "docs", "description": "Documentation and usage help"},
]

app = FastAPI(
    title="LPT.bin to CSV Converter API",
    description="""
Convert LPT.bin binary files to CSV format.

## Features

* **Path-based conversion**: Convert files by specifying input/output paths
* **File upload**: Upload LPT.bin files directly and get CSV back
* **Streaming**: Efficient processing for large inputs
* **Configurable parsing**: Customize binary struct formats for different LPT.bin variants
* **Error handling**: Comprehensive error messages and validation

## Production configuration (environment variables)

* `LPT_API_ALLOWED_INPUT_ROOT` / `LPT_API_ALLOWED_OUTPUT_ROOT`: restrict path-based conversion to these roots.
* `LPT_API_MAX_UPLOAD_BYTES`: max upload size (default 50MB).
* `LPT_API_TEMP_DIR`: directory for temporary upload/output files (default: system temp).
* `LOG_LEVEL`: logging verbosity.
* `LPT_API_CORS_ORIGINS`: comma-separated origins (default: "*").
""",
    version="1.0.0",
    openapi_tags=openapi_tags,
)

# CORS middleware (env-configurable)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _cleanup_files(paths: List[str]) -> None:
    """Best-effort cleanup of temp files; runs after response is sent."""
    for p in paths:
        if not p:
            continue
        try:
            if os.path.exists(p):
                os.unlink(p)
        except Exception as e:
            logger.warning("Failed to clean up temp file %s: %s", p, e)


async def _stream_upload_to_disk(upload: UploadFile, dest_path: str, max_bytes: int) -> int:
    """Stream an UploadFile to disk with a strict max size.

    Args:
        upload: Incoming UploadFile.
        dest_path: Destination path to write.
        max_bytes: Maximum allowed bytes.

    Returns:
        Total bytes written.

    Raises:
        HTTPException: if file exceeds limit or I/O fails.
    """
    total = 0
    chunk_size = 1024 * 1024  # 1MB
    try:
        with open(dest_path, "wb") as out:
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail={
                            "success": False,
                            "error": "FileTooLarge",
                            "message": f"Upload exceeds max size of {max_bytes} bytes",
                        },
                    )
                out.write(chunk)
        return total
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "InternalServerError",
                "message": "Failed to persist uploaded file",
                "details": str(e),
            },
        ) from e


# PUBLIC_INTERFACE
@app.get(
    "/",
    response_model=HealthResponse,
    tags=["health"],
    summary="Health Check",
    description="Check if the API service is running and healthy",
)
def health_check():
    """
    Verify that the LPT.bin to CSV Converter API is operational.

    Returns:
        HealthResponse: Service status information
    """
    return HealthResponse(status="healthy", message="LPT.bin to CSV Converter API is running")


# PUBLIC_INTERFACE
@app.get(
    "/docs/usage",
    response_class=PlainTextResponse,
    tags=["docs"],
    summary="Web API usage notes",
    description="Operational and security notes for using the API in production.",
)
def docs_usage() -> str:
    """
    Provide human-readable usage notes for the API.

    Returns:
        PlainTextResponse: Notes on upload limits, path restrictions, and endpoint guidance.
    """
    input_root = str(settings.allowed_input_root) if settings.allowed_input_root else "(not set)"
    output_root = str(settings.allowed_output_root) if settings.allowed_output_root else "(not set)"
    return (
        "LPT.bin → CSV Converter API usage notes\n"
        "\n"
        "Endpoints:\n"
        "  - POST /convert           Convert using server-side filesystem paths\n"
        "  - POST /convert/upload    Upload a .bin file and download the resulting CSV\n"
        "  - POST /convert/advanced  Convert with custom struct formats\n"
        "  - GET  /formats           View default struct formats\n"
        "\n"
        "Production settings:\n"
        f"  - Max upload bytes: {settings.max_upload_bytes}\n"
        f"  - Temp dir: {settings.temp_dir}\n"
        f"  - Allowed input root: {input_root}\n"
        f"  - Allowed output root: {output_root}\n"
        "\n"
        "Recommendation:\n"
        "  Prefer /convert/upload for untrusted clients. Use /convert only when you control\n"
        "  the server filesystem and have configured allowed roots.\n"
    )


# PUBLIC_INTERFACE
@app.post(
    "/convert",
    response_model=ConversionResponse,
    responses={
        200: {"description": "Conversion successful", "model": ConversionResponse},
        400: {"description": "Invalid request or parsing error", "model": ErrorResponse},
        404: {"description": "Input file not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    tags=["conversion"],
    summary="Convert LPT.bin to CSV by path",
    description="Convert an LPT.bin file to CSV format using file system paths",
)
def convert_file(request: ConversionRequest):
    """
    Convert an LPT.bin file to CSV format using specified input/output paths.

    This endpoint is suitable when both the service and client have access to
    a shared file system. For uploads from client, use /convert/upload endpoint.

    Security:
        If `LPT_API_ALLOWED_INPUT_ROOT` and/or `LPT_API_ALLOWED_OUTPUT_ROOT` are set,
        the provided paths must resolve within those directories.

    Args:
        request: ConversionRequest containing input_path, output_path, and options

    Returns:
        ConversionResponse: Conversion results including record count and file paths

    Raises:
        HTTPException: If file not found, parsing fails, or other errors occur
    """
    try:
        input_path = resolve_and_validate_path(
            request.input_path, must_exist=True, allowed_root=settings.allowed_input_root
        )
        output_path = resolve_and_validate_path(
            request.output_path, must_exist=False, allowed_root=settings.allowed_output_root
        )

        logger.info("Converting %s to %s", input_path, output_path)

        config = ParserConfig(skip_header=request.skip_header)

        result = convert_lpt_bin_to_csv(str(input_path), str(output_path), config)
        return ConversionResponse(**result)

    except ValueError as e:
        # Includes allow-root violations and missing path errors from our validation.
        logger.error("Validation error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": "ValidationError", "message": str(e)},
        )
    except FileNotFoundError as e:
        logger.error("File not found: %s", e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "FileNotFoundError", "message": str(e)},
        )
    except LPTBinParserError as e:
        logger.error("Parsing error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "ParsingError",
                "message": f"Failed to parse LPT.bin file: {str(e)}",
            },
        )
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "InternalServerError",
                "message": "An unexpected error occurred during conversion",
                "details": str(e),
            },
        )


# PUBLIC_INTERFACE
@app.post(
    "/convert/upload",
    response_class=FileResponse,
    responses={
        200: {"description": "CSV file generated successfully", "content": {"text/csv": {}}},
        400: {"description": "Invalid file or parsing error", "model": ErrorResponse},
        413: {"description": "Uploaded file too large", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    tags=["conversion"],
    summary="Upload LPT.bin and download CSV",
    description="Upload an LPT.bin file and receive the converted CSV file in response",
)
async def convert_upload(
    file: UploadFile = File(..., description="LPT.bin file to convert"),
    skip_header: bool = Query(default=False, description="Whether to skip header parsing"),
):
    """
    Upload an LPT.bin file and receive the converted CSV file.

    This endpoint accepts a binary file upload, converts it to CSV, and returns
    the CSV file for download.

    Safety:
        - Streams upload to disk to avoid loading the entire file into memory.
        - Enforces `LPT_API_MAX_UPLOAD_BYTES` to protect the service.
        - Writes temp files under `LPT_API_TEMP_DIR` (or system temp).
        - Guarantees temp input and output files are cleaned up *after* the response is sent.

    Args:
        file: Uploaded LPT.bin file (multipart/form-data)
        skip_header: Whether to skip header parsing (query parameter)

    Returns:
        FileResponse: Converted CSV file for download

    Raises:
        HTTPException: If upload fails, parsing fails, or other errors occur
    """
    temp_input = None
    temp_output = None

    try:
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"success": False, "error": "ValidationError", "message": "No file provided"},
            )

        logger.info("Processing uploaded file: %s", file.filename)

        # Create temp file paths in our configured temp directory.
        temp_input = str((settings.temp_dir / f"upload_{os.getpid()}_{id(file)}.bin").resolve())
        temp_output = str((settings.temp_dir / f"output_{os.getpid()}_{id(file)}.csv").resolve())

        # Stream upload to temp input with size cap.
        await _stream_upload_to_disk(file, temp_input, settings.max_upload_bytes)

        # Convert
        config = ParserConfig(skip_header=skip_header)
        result = convert_lpt_bin_to_csv(temp_input, temp_output, config)
        logger.info("Conversion successful: %s records", result["records_converted"])

        output_filename = sanitize_download_filename(Path(file.filename).stem + ".csv")

        # Cleanup is guaranteed post-response via BackgroundTask.
        return FileResponse(
            path=temp_output,
            media_type="text/csv",
            filename=output_filename,
            background=BackgroundTask(_cleanup_files, [temp_input, temp_output]),
        )

    except HTTPException:
        # Ensure best-effort cleanup on raised HTTPException before response is created.
        _cleanup_files([temp_input or "", temp_output or ""])
        raise
    except LPTBinParserError as e:
        logger.error("Parsing error: %s", e)
        _cleanup_files([temp_input or "", temp_output or ""])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "ParsingError",
                "message": f"Failed to parse LPT.bin file: {str(e)}",
            },
        )
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        _cleanup_files([temp_input or "", temp_output or ""])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "InternalServerError",
                "message": "An unexpected error occurred during conversion",
                "details": str(e),
            },
        )


# PUBLIC_INTERFACE
@app.post(
    "/convert/advanced",
    response_model=ConversionResponse,
    responses={
        200: {"description": "Conversion successful", "model": ConversionResponse},
        400: {"description": "Invalid request or parsing error", "model": ErrorResponse},
        404: {"description": "Input file not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    tags=["conversion"],
    summary="Convert with custom parser configuration",
    description="Convert LPT.bin to CSV with custom struct format configuration",
)
def convert_advanced(request: ConversionRequest, parser_config: Optional[ParserConfigRequest] = None):
    """
    Convert LPT.bin file with advanced parser configuration.

    Security:
        Same path validation rules as /convert (optional allow-roots).

    Args:
        request: ConversionRequest with input/output paths
        parser_config: Optional custom parser configuration

    Returns:
        ConversionResponse: Conversion results

    Raises:
        HTTPException: If conversion fails
    """
    try:
        input_path = resolve_and_validate_path(
            request.input_path, must_exist=True, allowed_root=settings.allowed_input_root
        )
        output_path = resolve_and_validate_path(
            request.output_path, must_exist=False, allowed_root=settings.allowed_output_root
        )

        config_kwargs = {"skip_header": request.skip_header}

        if parser_config:
            if parser_config.header_format:
                config_kwargs["header_format"] = parser_config.header_format
            if parser_config.header_fields:
                config_kwargs["header_fields"] = parser_config.header_fields
            if parser_config.record_format:
                config_kwargs["record_format"] = parser_config.record_format
            if parser_config.record_fields:
                config_kwargs["record_fields"] = parser_config.record_fields
            if parser_config.skip_header:
                config_kwargs["skip_header"] = True

        config = ParserConfig(**config_kwargs)

        result = convert_lpt_bin_to_csv(str(input_path), str(output_path), config)
        return ConversionResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": "ValidationError", "message": str(e)},
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "FileNotFoundError", "message": str(e)},
        )
    except LPTBinParserError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "ParsingError",
                "message": f"Failed to parse LPT.bin file: {str(e)}",
            },
        )
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "InternalServerError",
                "message": "An unexpected error occurred during conversion",
                "details": str(e),
            },
        )


# PUBLIC_INTERFACE
@app.get(
    "/formats",
    tags=["conversion"],
    summary="Get default format information",
    description="Retrieve the default struct formats and field names used by the parser",
)
def get_format_info():
    """
    Get information about default binary format configuration.

    Returns default struct format strings and field names that can be used
    as a reference for custom configurations.

    Returns:
        dict: Default parser configuration details
    """
    from ..converter.lpt_converter import HEADER_FORMAT, HEADER_FIELDS, RECORD_FORMAT, RECORD_FIELDS

    return {
        "header": {
            "format": HEADER_FORMAT,
            "fields": HEADER_FIELDS,
            "description": "Default header format: 4 unsigned integers (little-endian)",
        },
        "record": {
            "format": RECORD_FORMAT,
            "fields": RECORD_FIELDS,
            "description": "Default record format: double, 2 floats, 2 unsigned ints, long long (little-endian)",
        },
        "notes": [
            "Formats use Python struct module notation",
            "<: little-endian, >: big-endian",
            "I: unsigned int (4 bytes), d: double (8 bytes), f: float (4 bytes), q: long long (8 bytes)",
            "Adjust these formats based on your actual LPT.bin specification",
        ],
    }
