"""
FastAPI Application for LPT.bin to CSV Converter

Provides REST API endpoints for converting LPT.bin binary files to CSV format.
Includes file upload support, path-based conversion, and comprehensive API documentation.
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import logging
import tempfile
import os
from pathlib import Path
from typing import Optional

from .models import (
    ConversionRequest,
    ConversionResponse,
    ErrorResponse,
    HealthResponse,
    ParserConfigRequest
)
from ..converter.lpt_converter import (
    convert_lpt_bin_to_csv,
    ParserConfig,
    LPTBinParserError
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenAPI metadata
openapi_tags = [
    {
        "name": "health",
        "description": "Health check and service status endpoints"
    },
    {
        "name": "conversion",
        "description": "LPT.bin to CSV conversion operations"
    }
]

# Initialize FastAPI app with metadata
app = FastAPI(
    title="LPT.bin to CSV Converter API",
    description="""
    Convert LPT.bin binary files to CSV format.
    
    ## Features
    
    * **Path-based conversion**: Convert files by specifying input/output paths
    * **File upload**: Upload LPT.bin files directly and get CSV back
    * **Streaming**: Efficient processing of large files without loading entire file into memory
    * **Configurable parsing**: Customize binary struct formats for different LPT.bin variants
    * **Error handling**: Comprehensive error messages and validation
    
    ## Binary Format
    
    The default parser assumes:
    - **Header**: 16 bytes (magic number, version, record count, reserved)
    - **Records**: 32 bytes each (timestamp, values, status, flags)
    
    You can customize the struct format using advanced conversion endpoints.
    
    ## Usage Notes
    
    For path-based conversion, ensure the service has read access to input paths 
    and write access to output directories. For production use, consider using 
    the file upload endpoint for better security.
    """,
    version="1.0.0",
    openapi_tags=openapi_tags
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# PUBLIC_INTERFACE
@app.get(
    "/",
    response_model=HealthResponse,
    tags=["health"],
    summary="Health Check",
    description="Check if the API service is running and healthy"
)
def health_check():
    """
    Verify that the LPT.bin to CSV Converter API is operational.
    
    Returns:
        HealthResponse: Service status information
    """
    return HealthResponse(
        status="healthy",
        message="LPT.bin to CSV Converter API is running"
    )


# PUBLIC_INTERFACE
@app.post(
    "/convert",
    response_model=ConversionResponse,
    responses={
        200: {
            "description": "Conversion successful",
            "model": ConversionResponse
        },
        400: {
            "description": "Invalid request or parsing error",
            "model": ErrorResponse
        },
        404: {
            "description": "Input file not found",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse
        }
    },
    tags=["conversion"],
    summary="Convert LPT.bin to CSV by path",
    description="Convert an LPT.bin file to CSV format using file system paths"
)
def convert_file(request: ConversionRequest):
    """
    Convert an LPT.bin file to CSV format using specified input/output paths.
    
    This endpoint is suitable when both the service and client have access to 
    a shared file system. For uploads from client, use /convert/upload endpoint.
    
    Args:
        request: ConversionRequest containing input_path, output_path, and options
        
    Returns:
        ConversionResponse: Conversion results including record count and file paths
        
    Raises:
        HTTPException: If file not found, parsing fails, or other errors occur
    """
    try:
        logger.info(f"Converting {request.input_path} to {request.output_path}")
        
        # Create parser config
        config = ParserConfig(skip_header=request.skip_header)
        
        # Perform conversion
        result = convert_lpt_bin_to_csv(
            request.input_path,
            request.output_path,
            config
        )
        
        return ConversionResponse(**result)
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "FileNotFoundError",
                "message": str(e)
            }
        )
        
    except LPTBinParserError as e:
        logger.error(f"Parsing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "ParsingError",
                "message": f"Failed to parse LPT.bin file: {str(e)}"
            }
        )
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "ValidationError",
                "message": str(e)
            }
        )
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "InternalServerError",
                "message": "An unexpected error occurred during conversion",
                "details": str(e)
            }
        )


# PUBLIC_INTERFACE
@app.post(
    "/convert/upload",
    response_class=FileResponse,
    responses={
        200: {
            "description": "CSV file generated successfully",
            "content": {"text/csv": {}}
        },
        400: {
            "description": "Invalid file or parsing error",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse
        }
    },
    tags=["conversion"],
    summary="Upload LPT.bin and download CSV",
    description="Upload an LPT.bin file and receive the converted CSV file in response"
)
async def convert_upload(
    file: UploadFile = File(..., description="LPT.bin file to convert"),
    skip_header: bool = False
):
    """
    Upload an LPT.bin file and receive the converted CSV file.
    
    This endpoint accepts a binary file upload, converts it to CSV, and returns 
    the CSV file for download. Temporary files are automatically cleaned up.
    
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
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error": "ValidationError",
                    "message": "No file provided"
                }
            )
        
        logger.info(f"Processing uploaded file: {file.filename}")
        
        # Create temporary files
        with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as temp_in:
            temp_input = temp_in.name
            # Read and write uploaded file
            content = await file.read()
            temp_in.write(content)
        
        temp_output = tempfile.mktemp(suffix='.csv')
        
        # Create parser config
        config = ParserConfig(skip_header=skip_header)
        
        # Perform conversion
        result = convert_lpt_bin_to_csv(temp_input, temp_output, config)
        
        logger.info(f"Conversion successful: {result['records_converted']} records")
        
        # Generate output filename
        output_filename = Path(file.filename).stem + '.csv'
        
        # Return CSV file
        return FileResponse(
            path=temp_output,
            media_type='text/csv',
            filename=output_filename,
            background=None  # We'll clean up manually after response
        )
        
    except LPTBinParserError as e:
        logger.error(f"Parsing error: {e}")
        # Clean up temp files on error
        if temp_input and os.path.exists(temp_input):
            os.unlink(temp_input)
        if temp_output and os.path.exists(temp_output):
            os.unlink(temp_output)
            
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "ParsingError",
                "message": f"Failed to parse LPT.bin file: {str(e)}"
            }
        )
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        # Clean up temp files on error
        if temp_input and os.path.exists(temp_input):
            os.unlink(temp_input)
        if temp_output and os.path.exists(temp_output):
            os.unlink(temp_output)
            
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "InternalServerError",
                "message": "An unexpected error occurred during conversion",
                "details": str(e)
            }
        )
    finally:
        # Clean up input file (output file is handled by FileResponse)
        if temp_input and os.path.exists(temp_input):
            try:
                os.unlink(temp_input)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up temp input: {cleanup_error}")


# PUBLIC_INTERFACE
@app.post(
    "/convert/advanced",
    response_model=ConversionResponse,
    responses={
        200: {
            "description": "Conversion successful",
            "model": ConversionResponse
        },
        400: {
            "description": "Invalid request or parsing error",
            "model": ErrorResponse
        },
        404: {
            "description": "Input file not found",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse
        }
    },
    tags=["conversion"],
    summary="Convert with custom parser configuration",
    description="Convert LPT.bin to CSV with custom struct format configuration"
)
def convert_advanced(
    request: ConversionRequest,
    parser_config: Optional[ParserConfigRequest] = None
):
    """
    Convert LPT.bin file with advanced parser configuration.
    
    This endpoint allows you to specify custom struct format strings and field names
    for different variants of LPT.bin files. Useful when the default format doesn't match.
    
    Args:
        request: ConversionRequest with input/output paths
        parser_config: Optional custom parser configuration
        
    Returns:
        ConversionResponse: Conversion results
        
    Raises:
        HTTPException: If conversion fails
    """
    try:
        # Build parser config from request
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
        
        # Perform conversion
        result = convert_lpt_bin_to_csv(
            request.input_path,
            request.output_path,
            config
        )
        
        return ConversionResponse(**result)
        
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "FileNotFoundError",
                "message": str(e)
            }
        )
        
    except LPTBinParserError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "ParsingError",
                "message": f"Failed to parse LPT.bin file: {str(e)}"
            }
        )
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "InternalServerError",
                "message": "An unexpected error occurred during conversion",
                "details": str(e)
            }
        )


# PUBLIC_INTERFACE
@app.get(
    "/formats",
    tags=["conversion"],
    summary="Get default format information",
    description="Retrieve the default struct formats and field names used by the parser"
)
def get_format_info():
    """
    Get information about default binary format configuration.
    
    Returns default struct format strings and field names that can be used 
    as a reference for custom configurations.
    
    Returns:
        dict: Default parser configuration details
    """
    from ..converter.lpt_converter import (
        HEADER_FORMAT,
        HEADER_FIELDS,
        RECORD_FORMAT,
        RECORD_FIELDS
    )
    
    return {
        "header": {
            "format": HEADER_FORMAT,
            "fields": HEADER_FIELDS,
            "description": "Default header format: 4 unsigned integers (little-endian)"
        },
        "record": {
            "format": RECORD_FORMAT,
            "fields": RECORD_FIELDS,
            "description": "Default record format: double, 2 floats, 2 unsigned ints, long long (little-endian)"
        },
        "notes": [
            "Formats use Python struct module notation",
            "<: little-endian, >: big-endian",
            "I: unsigned int (4 bytes), d: double (8 bytes), f: float (4 bytes), q: long long (8 bytes)",
            "Adjust these formats based on your actual LPT.bin specification"
        ]
    }
