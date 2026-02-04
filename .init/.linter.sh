#!/bin/bash
cd /home/kavia/workspace/code-generation/lpt-bin-to-csv-converter-64-73/lpt_bin_converter_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

