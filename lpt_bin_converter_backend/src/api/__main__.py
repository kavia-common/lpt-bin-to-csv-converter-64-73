"""
Uvicorn entrypoint for running the FastAPI application.

Usage:
    python -m src.api

Environment variables:
    - HOST (default: 0.0.0.0)
    - PORT (default: 3001)
    - LOG_LEVEL (default: INFO)
"""

from __future__ import annotations

import os

import uvicorn


# PUBLIC_INTERFACE
def main() -> None:
    """Run the FastAPI app using uvicorn with sensible defaults."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "3001"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    uvicorn.run("src.api.main:app", host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
