"""
API Models for LPT.bin to CSV Converter

Pydantic models for request validation and response schemas.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ConversionRequest(BaseModel):
    """Request model for file conversion by path."""

    input_path: str = Field(
        ...,
        description="Absolute or relative path to input LPT.bin file",
        examples=["/data/input.bin", "uploads/file.bin"],
    )

    output_path: str = Field(
        ...,
        description="Absolute or relative path to output CSV file",
        examples=["/data/output.csv", "results/file.csv"],
    )

    skip_header: bool = Field(
        default=False,
        description="Skip header parsing and treat entire file as records",
    )

    @field_validator("input_path", "output_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate that paths are not empty."""
        if not v or not v.strip():
            raise ValueError("Path cannot be empty")
        return v.strip()


class ParserConfigRequest(BaseModel):
    """Optional parser configuration for advanced users."""

    header_format: Optional[str] = Field(
        default=None,
        description="Struct format string for header (e.g., '<IIII')",
        examples=["<IIII", ">HHI"],
    )

    header_fields: Optional[List[str]] = Field(
        default=None,
        description="Field names for header values",
        examples=[["magic", "version", "count", "reserved"]],
    )

    record_format: Optional[str] = Field(
        default=None,
        description="Struct format string for records (e.g., '<dffIIq')",
        examples=["<dffIIq", ">ddII"],
    )

    record_fields: Optional[List[str]] = Field(
        default=None,
        description="Field names for CSV columns",
        examples=[["timestamp", "value1", "value2", "status", "flags", "reserved"]],
    )

    skip_header: bool = Field(default=False, description="Skip header parsing")


class ConversionResponse(BaseModel):
    """Response model for conversion operations."""

    success: bool = Field(..., description="Whether conversion was successful")

    records_converted: int = Field(
        ..., description="Number of records converted to CSV", examples=[1000, 50000]
    )

    input_file: str = Field(..., description="Path to input file that was converted")

    output_file: str = Field(..., description="Path to output CSV file")

    message: str = Field(
        ...,
        description="Human-readable status message",
        examples=["Successfully converted 1000 records"],
    )


class ErrorResponse(BaseModel):
    """Error response model."""

    success: bool = Field(default=False, description="Always false for errors")

    error: str = Field(
        ...,
        description="Error type or category",
        examples=["FileNotFoundError", "ParsingError", "ValidationError"],
    )

    message: str = Field(
        ...,
        description="Detailed error message",
        examples=["Input file not found: /path/to/file.bin"],
    )

    details: Optional[str] = Field(
        default=None, description="Additional error details or stack trace"
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(default="healthy", description="Service health status")

    message: str = Field(
        default="LPT.bin to CSV Converter API is running", description="Status message"
    )
