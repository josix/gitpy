#!/bin/bash
# Session summary hook - runs when Claude stops
# Provides a quick status check of the codebase

set -e
cd /home/user/gitpy

echo ""
echo "=== gitpy Session Summary ==="
echo ""

# Check for uncommitted changes
if [[ -n $(git status --porcelain 2>/dev/null) ]]; then
    echo "Uncommitted changes:"
    git status --short
    echo ""
fi

# Quick style check (silent, just report status)
if command -v ruff &> /dev/null; then
    LINT_ISSUES=$(ruff check gitpy tests 2>/dev/null | wc -l || echo "0")
    if [[ "$LINT_ISSUES" -gt 0 ]]; then
        echo "Style issues: $LINT_ISSUES (run: ruff check --fix)"
    else
        echo "Style: OK"
    fi
fi

# Check if tests exist and could be run
if [[ -d tests ]] && [[ $(find tests -name "test_*.py" 2>/dev/null | wc -l) -gt 0 ]]; then
    TEST_COUNT=$(find tests -name "test_*.py" | wc -l)
    echo "Test files: $TEST_COUNT"
fi

echo ""
echo "=== End Summary ==="
