"""
CLI entry point for LPT.bin to CSV converter.

Usage:
    python -m src.converter.lpt_converter <input_file> <output_file>
    python -m src.converter.lpt_converter --help

Examples:
    python -m src.converter.lpt_converter data/input.bin output.csv
    python -m src.converter.lpt_converter --skip-header data/input.bin output.csv
"""

import argparse
import logging
import sys

from .lpt_converter import LPTBinParserError, ParserConfig, convert_lpt_bin_to_csv


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Convert LPT.bin binary files to CSV format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.bin output.csv
  %(prog)s --skip-header data/input.bin data/output.csv
  %(prog)s -v input.bin output.csv  # Verbose output
        """,
    )

    parser.add_argument("input_file", type=str, help="Path to input LPT.bin file")

    parser.add_argument("output_file", type=str, help="Path to output CSV file")

    parser.add_argument(
        "--skip-header",
        action="store_true",
        help="Skip header parsing and treat entire file as records",
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger = logging.getLogger(__name__)

    # Create parser config
    config = ParserConfig(skip_header=args.skip_header)

    try:
        logger.info("Converting %s to %s", args.input_file, args.output_file)

        result = convert_lpt_bin_to_csv(args.input_file, args.output_file, config)

        print("\n✓ Conversion successful!")
        print(f"  Records converted: {result['records_converted']}")
        print(f"  Output file: {result['output_file']}")

        return 0

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        print(f"\n✗ Error: {e}", file=sys.stderr)
        return 1

    except LPTBinParserError as e:
        logger.error(f"Parsing error: {e}")
        print(f"\n✗ Parsing error: {e}", file=sys.stderr)
        return 2

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\n✗ Unexpected error: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
