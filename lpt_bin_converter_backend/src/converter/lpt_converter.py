"""
LPT.bin to CSV Converter Module

This module provides functionality to convert LPT.bin binary files to CSV format.
The binary format is configurable via struct format strings.

Binary File Structure (Default/Example):
- Header: 16 bytes
  - Magic number: 4 bytes (uint32)
  - Version: 4 bytes (uint32)
  - Record count: 4 bytes (uint32)
  - Reserved: 4 bytes (uint32)
- Records: Each record is fixed-size (default 32 bytes)
  - Timestamp: 8 bytes (double)
  - Value1: 4 bytes (float)
  - Value2: 4 bytes (float)
  - Status: 4 bytes (int32)
  - Flags: 4 bytes (uint32)
  - Reserved: 8 bytes (int64)

TODO: Adjust struct formats below once exact LPT.bin format is confirmed.
"""

import struct
import csv
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# TODO: Update these format strings based on actual LPT.bin specification
# Current format is example/placeholder
HEADER_FORMAT = '<IIII'  # Little-endian: 4 unsigned ints
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
HEADER_FIELDS = ['magic_number', 'version', 'record_count', 'reserved']

RECORD_FORMAT = '<dffIIq'  # Little-endian: double, 2 floats, 2 unsigned ints, long long
RECORD_SIZE = struct.calcsize(RECORD_FORMAT)
RECORD_FIELDS = ['timestamp', 'value1', 'value2', 'status', 'flags', 'reserved']


@dataclass
class ParserConfig:
    """Configuration for LPT.bin parser.
    
    Allows customization of struct formats and field names without code changes.
    """
    header_format: str = HEADER_FORMAT
    header_fields: List[str] = None
    record_format: str = RECORD_FORMAT
    record_fields: List[str] = None
    skip_header: bool = False
    chunk_size: int = 1000  # Number of records to process at once
    
    def __post_init__(self):
        if self.header_fields is None:
            self.header_fields = HEADER_FIELDS.copy()
        if self.record_fields is None:
            self.record_fields = RECORD_FIELDS.copy()


class LPTBinParserError(Exception):
    """Custom exception for LPT.bin parsing errors."""
    pass


# PUBLIC_INTERFACE
def parse_header(file_handle, config: ParserConfig) -> Dict:
    """
    Parse the header section of an LPT.bin file.
    
    Args:
        file_handle: Binary file handle positioned at start of header
        config: Parser configuration
        
    Returns:
        Dictionary containing header fields and values
        
    Raises:
        LPTBinParserError: If header cannot be parsed
    """
    try:
        header_size = struct.calcsize(config.header_format)
        header_bytes = file_handle.read(header_size)
        
        if len(header_bytes) < header_size:
            raise LPTBinParserError(
                f"Incomplete header: expected {header_size} bytes, got {len(header_bytes)}"
            )
        
        header_values = struct.unpack(config.header_format, header_bytes)
        header_dict = dict(zip(config.header_fields, header_values))
        
        logger.info(f"Parsed header: {header_dict}")
        return header_dict
        
    except struct.error as e:
        raise LPTBinParserError(f"Failed to parse header: {str(e)}")


# PUBLIC_INTERFACE
def parse_record(record_bytes: bytes, config: ParserConfig) -> Optional[Tuple]:
    """
    Parse a single record from LPT.bin file.
    
    Args:
        record_bytes: Raw bytes for one record
        config: Parser configuration
        
    Returns:
        Tuple of parsed values, or None if parsing fails
        
    Raises:
        LPTBinParserError: If record cannot be parsed
    """
    try:
        record_size = struct.calcsize(config.record_format)
        
        if len(record_bytes) < record_size:
            logger.warning(
                f"Incomplete record: expected {record_size} bytes, got {len(record_bytes)}"
            )
            return None
        
        values = struct.unpack(config.record_format, record_bytes[:record_size])
        return values
        
    except struct.error as e:
        raise LPTBinParserError(f"Failed to parse record: {str(e)}")


# PUBLIC_INTERFACE
def stream_records(file_handle, config: ParserConfig, max_records: Optional[int] = None):
    """
    Generator that streams records from LPT.bin file without loading entire file into memory.
    
    Args:
        file_handle: Binary file handle positioned after header
        config: Parser configuration
        max_records: Maximum number of records to read (None = all records)
        
    Yields:
        Tuples of parsed record values
    """
    record_size = struct.calcsize(config.record_format)
    records_read = 0
    
    while True:
        if max_records and records_read >= max_records:
            break
            
        record_bytes = file_handle.read(record_size)
        
        if not record_bytes:
            break  # EOF reached
        
        if len(record_bytes) < record_size:
            logger.warning(f"Incomplete record at end of file (byte {file_handle.tell()})")
            break
        
        try:
            record = parse_record(record_bytes, config)
            if record:
                yield record
                records_read += 1
        except LPTBinParserError as e:
            logger.error(f"Error parsing record {records_read + 1}: {str(e)}")
            # Continue to next record instead of failing entirely
            continue


# PUBLIC_INTERFACE
def convert_lpt_bin_to_csv(
    input_path: str,
    output_path: str,
    config: Optional[ParserConfig] = None
) -> Dict[str, any]:
    """
    Convert an LPT.bin file to CSV format.
    
    This function streams records from the binary file and writes them to CSV,
    avoiding loading the entire file into memory. Suitable for large files.
    
    Args:
        input_path: Path to input LPT.bin file
        output_path: Path to output CSV file
        config: Optional parser configuration. If None, uses default config.
        
    Returns:
        Dictionary containing conversion statistics:
        - success: bool
        - records_converted: int
        - input_file: str
        - output_file: str
        - message: str
        
    Raises:
        FileNotFoundError: If input file doesn't exist
        LPTBinParserError: If file parsing fails
        IOError: If file I/O operations fail
    """
    if config is None:
        config = ParserConfig()
    
    # Validate input file
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    if not input_file.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")
    
    # Prepare output directory
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Starting conversion: {input_path} -> {output_path}")
    
    records_converted = 0
    header_info = None
    
    try:
        with open(input_path, 'rb') as bin_file:
            # Parse header if not skipped
            if not config.skip_header:
                try:
                    header_info = parse_header(bin_file, config)
                except LPTBinParserError as e:
                    logger.warning(f"Header parsing failed: {str(e)}. Attempting to parse as raw records.")
                    bin_file.seek(0)  # Reset to start and skip header
                    config.skip_header = True
            
            # Open CSV file for writing
            with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
                writer = csv.writer(csv_file)
                
                # Write CSV header
                writer.writerow(config.record_fields)
                
                # Stream and convert records
                max_records = None
                if header_info and 'record_count' in header_info:
                    max_records = header_info['record_count']
                
                for record in stream_records(bin_file, config, max_records):
                    writer.writerow(record)
                    records_converted += 1
                    
                    # Log progress for large files
                    if records_converted % 10000 == 0:
                        logger.info(f"Converted {records_converted} records...")
        
        logger.info(f"Conversion complete: {records_converted} records written to {output_path}")
        
        return {
            'success': True,
            'records_converted': records_converted,
            'input_file': str(input_path),
            'output_file': str(output_path),
            'message': f'Successfully converted {records_converted} records'
        }
        
    except Exception as e:
        logger.error(f"Conversion failed: {str(e)}")
        
        # Clean up partial output file on error
        if output_file.exists():
            try:
                output_file.unlink()
                logger.info(f"Cleaned up partial output file: {output_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up output file: {cleanup_error}")
        
        raise
