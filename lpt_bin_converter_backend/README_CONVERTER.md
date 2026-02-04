# LPT.bin to CSV Converter

A Python module and REST API for converting LPT.bin binary files to CSV format.

## Features

- **Streaming Processing**: Handles large files efficiently without loading entire file into memory
- **Configurable Parser**: Customize binary struct formats for different LPT.bin variants
- **Multiple Interfaces**: Use as Python module, CLI tool, or REST API
- **Error Handling**: Comprehensive validation and error messages
- **API Documentation**: Full Swagger/OpenAPI documentation

## Usage

### 1. As a Python Module

```python
from src.converter import convert_lpt_bin_to_csv, ParserConfig

# Basic conversion with defaults
result = convert_lpt_bin_to_csv('input.bin', 'output.csv')
print(f"Converted {result['records_converted']} records")

# Advanced: Custom parser configuration
config = ParserConfig(
    header_format='<IIII',
    record_format='<dffIIq',
    skip_header=False
)
result = convert_lpt_bin_to_csv('input.bin', 'output.csv', config)
```

### 2. As a CLI Tool

```bash
# Basic usage
python -m src.converter input.bin output.csv

# Skip header parsing
python -m src.converter --skip-header input.bin output.csv

# Verbose output
python -m src.converter -v input.bin output.csv

# Help
python -m src.converter --help
```

### 3. Via REST API

#### Convert by file path
```bash
curl -X POST "http://localhost:3001/convert" \
  -H "Content-Type: application/json" \
  -d '{
    "input_path": "data/input.bin",
    "output_path": "data/output.csv",
    "skip_header": false
  }'
```

#### Upload and convert
```bash
curl -X POST "http://localhost:3001/convert/upload" \
  -F "file=@input.bin" \
  -F "skip_header=false" \
  -o output.csv
```

#### Advanced conversion with custom format
```bash
curl -X POST "http://localhost:3001/convert/advanced" \
  -H "Content-Type: application/json" \
  -d '{
    "input_path": "input.bin",
    "output_path": "output.csv",
    "parser_config": {
      "record_format": "<ddII",
      "record_fields": ["time", "value", "status", "flags"]
    }
  }'
```

## Binary Format Configuration

The default parser assumes this structure:

### Header (16 bytes)
- Magic number: 4 bytes (uint32)
- Version: 4 bytes (uint32)
- Record count: 4 bytes (uint32)
- Reserved: 4 bytes (uint32)

### Records (32 bytes each)
- Timestamp: 8 bytes (double)
- Value1: 4 bytes (float)
- Value2: 4 bytes (float)
- Status: 4 bytes (int32)
- Flags: 4 bytes (uint32)
- Reserved: 8 bytes (int64)

### Customizing the Format

Update the format constants in `src/converter/lpt_converter.py`:

```python
# Example: Different header format
HEADER_FORMAT = '<HHI'  # 2 shorts, 1 int
HEADER_FIELDS = ['version', 'type', 'count']

# Example: Different record format
RECORD_FORMAT = '<ddII'  # 2 doubles, 2 ints
RECORD_FIELDS = ['timestamp', 'value', 'status', 'flags']
```

Or use `ParserConfig` at runtime for dynamic configuration.

### Struct Format Reference

Python struct format characters:
- `<`: little-endian, `>`: big-endian
- `b`: signed char (1 byte)
- `B`: unsigned char (1 byte)
- `h`: short (2 bytes)
- `H`: unsigned short (2 bytes)
- `i`: int (4 bytes)
- `I`: unsigned int (4 bytes)
- `q`: long long (8 bytes)
- `Q`: unsigned long long (8 bytes)
- `f`: float (4 bytes)
- `d`: double (8 bytes)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/convert` | POST | Convert by file path |
| `/convert/upload` | POST | Upload and convert |
| `/convert/advanced` | POST | Convert with custom config |
| `/formats` | GET | Get default format info |

Full API documentation available at: `http://localhost:3001/docs`

## Error Handling

The converter handles various error scenarios:

- **FileNotFoundError**: Input file doesn't exist
- **LPTBinParserError**: Binary parsing fails
- **ValueError**: Invalid paths or configuration
- **IOError**: File I/O failures

Partial output files are automatically cleaned up on error.

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/converter
```

### Logging

Enable verbose logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## TODO

- [ ] Determine exact LPT.bin format specification
- [ ] Update struct formats once format is confirmed
- [ ] Add unit tests for parser
- [ ] Add integration tests for API endpoints
- [ ] Consider adding format auto-detection
- [ ] Add support for multiple output formats (JSON, XML)

## Notes

The current implementation uses placeholder struct formats. Update `HEADER_FORMAT` and `RECORD_FORMAT` in `src/converter/lpt_converter.py` once the exact LPT.bin specification is available.
