#!/bin/bash
# check-consistency.sh - Check for inconsistent references in the codebase
# Reports outdated tool references (poetry vs uv, old Python versions, etc.)

set -e

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

ISSUES_FOUND=0

# Check for poetry references (should be uv)
check_poetry() {
    local files
    files=$(grep -rl --include="*.py" --include="*.md" --include="*.yaml" --include="*.yml" --include="*.toml" --include="*.json" \
        -E "poetry (run|install|build|export)|Poetry" . 2>/dev/null \
        | grep -v ".git/" | grep -v "__pycache__" | grep -v ".venv/" || true)

    if [[ -n "$files" ]]; then
        echo -e "${YELLOW}Warning: Found 'poetry' references (should use 'uv'):${NC}" >&2
        echo "$files" | while read -r f; do
            echo "  - $f" >&2
        done
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
}

# Check for old Python version references
check_python_version() {
    local files
    files=$(grep -rl --include="*.py" --include="*.md" --include="*.yaml" --include="*.yml" --include="*.toml" --include="*.json" \
        -E "python.?(3\.[0-9]|3\.1[01])[^2]|Python 3\.[0-9][^2]|Python 3\.1[01][^2]" . 2>/dev/null \
        | grep -v ".git/" | grep -v "__pycache__" | grep -v ".venv/" || true)

    if [[ -n "$files" ]]; then
        echo -e "${YELLOW}Warning: Found old Python version references (should be 3.12+):${NC}" >&2
        echo "$files" | while read -r f; do
            echo "  - $f" >&2
        done
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
}

# Check for typing imports that should use builtins
check_typing_imports() {
    local files
    files=$(grep -rl --include="*.py" \
        -E "from typing import (List|Dict|Set|Tuple|Optional)" . 2>/dev/null \
        | grep -v ".git/" | grep -v "__pycache__" | grep -v ".venv/" || true)

    if [[ -n "$files" ]]; then
        echo -e "${YELLOW}Warning: Found old typing imports (use builtins in 3.12+):${NC}" >&2
        echo "$files" | while read -r f; do
            echo "  - $f" >&2
        done
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
}

# Check for uncommitted changes
check_uncommitted() {
    local status
    status=$(git status --porcelain 2>/dev/null || true)

    if [[ -n "$status" ]]; then
        local count
        count=$(echo "$status" | wc -l)
        echo -e "${YELLOW}Note: $count uncommitted change(s) in working directory${NC}" >&2
    fi
}

# Main
echo "" >&2
echo "╔════════════════════════════════════════════════════════════════╗" >&2
echo "║                    CONSISTENCY CHECK                           ║" >&2
echo "╚════════════════════════════════════════════════════════════════╝" >&2

check_poetry
check_python_version
check_typing_imports
check_uncommitted

if [[ $ISSUES_FOUND -eq 0 ]]; then
    echo -e "${GREEN}✓ No consistency issues found${NC}" >&2
else
    echo "" >&2
    echo -e "${YELLOW}Found $ISSUES_FOUND consistency issue(s) to review${NC}" >&2
fi

echo "" >&2
