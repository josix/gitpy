#!/bin/bash
# Validate Python file after write/edit
# Called with file path as argument

FILE="$1"

if [[ -z "$FILE" ]] || [[ ! -f "$FILE" ]]; then
    exit 0
fi

# Only process Python files
if [[ "$FILE" != *.py ]]; then
    exit 0
fi

# Format with ruff
if command -v ruff &> /dev/null; then
    ruff format "$FILE" 2>/dev/null || true
    ruff check "$FILE" --fix --silent 2>/dev/null || true
fi

exit 0
