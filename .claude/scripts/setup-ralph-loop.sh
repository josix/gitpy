#!/bin/bash
# setup-ralph-loop.sh - Initialize a self-referential development loop
# Based on the ralph-wiggum plugin pattern from Claude Code

set -e

CLAUDE_DIR="${CLAUDE_LOCAL_DIR:-.claude}"
STATE_FILE="$CLAUDE_DIR/ralph-loop.local.md"

# Default values
MAX_ITERATIONS=50
COMPLETION_PROMISE=""
PROMPT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --max-iterations)
            MAX_ITERATIONS="$2"
            shift 2
            ;;
        --completion-promise)
            COMPLETION_PROMISE="$2"
            shift 2
            ;;
        -h|--help)
            cat << 'EOF'
Usage: setup-ralph-loop.sh [OPTIONS] <prompt>

Start a self-referential development loop that feeds the same prompt
back to Claude repeatedly until completion criteria are met.

OPTIONS:
    --max-iterations N      Maximum iterations before stopping (default: 50)
    --completion-promise T  Text that signals completion (e.g., "DONE", "VERIFIED")
    -h, --help              Show this help message

EXAMPLE:
    setup-ralph-loop.sh --max-iterations 20 --completion-promise "TESTS_PASS" \
        "Implement the Blob class and make all tests pass"

The loop continues until:
    1. Max iterations reached
    2. Completion promise appears in output: <promise>YOUR_PROMISE</promise>
    3. Manually cancelled with /cancel-ralph

IMPORTANT: Only output the completion promise when the condition is
COMPLETELY and UNEQUIVOCALLY TRUE. Do not lie to escape the loop.
EOF
            exit 0
            ;;
        *)
            # Collect remaining args as prompt
            PROMPT="$PROMPT $1"
            shift
            ;;
    esac
done

PROMPT="${PROMPT# }"  # Trim leading space

# Validate inputs
if [[ -z "$PROMPT" ]]; then
    echo "Error: No prompt provided"
    echo "Usage: setup-ralph-loop.sh [OPTIONS] <prompt>"
    exit 1
fi

if ! [[ "$MAX_ITERATIONS" =~ ^[0-9]+$ ]]; then
    echo "Error: --max-iterations must be a non-negative integer"
    exit 1
fi

# Check for existing loop
if [[ -f "$STATE_FILE" ]]; then
    echo "Warning: A ralph loop is already active."
    echo "Use /cancel-ralph to cancel it first, or delete $STATE_FILE"
    exit 1
fi

# Create state file with frontmatter
mkdir -p "$CLAUDE_DIR"
cat > "$STATE_FILE" << EOF
---
iteration: 0
max_iterations: $MAX_ITERATIONS
completion_promise: "$COMPLETION_PROMISE"
started_at: $(date -Iseconds)
prompt: |
$(echo "$PROMPT" | sed 's/^/  /')
---

# Ralph Loop State

This file tracks the state of an active ralph-wiggum loop.
Delete this file or use /cancel-ralph to stop the loop.

## Current Status
- Iteration: 0 / $MAX_ITERATIONS
- Started: $(date)
- Completion Promise: ${COMPLETION_PROMISE:-"(none - will run until max iterations)"}

## Prompt
$PROMPT
EOF

# Output confirmation
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    RALPH LOOP INITIALIZED                      ║"
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║ Iterations: 0 / $MAX_ITERATIONS"
echo "║ Promise: ${COMPLETION_PROMISE:-"(none)"}"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "The loop will continue until:"
if [[ -n "$COMPLETION_PROMISE" ]]; then
    echo "  • You output: <promise>$COMPLETION_PROMISE</promise>"
fi
echo "  • Max iterations ($MAX_ITERATIONS) reached"
echo "  • You run /cancel-ralph"
echo ""
echo "⚠️  IMPORTANT: Only output the completion promise when the condition"
echo "   is COMPLETELY and UNEQUIVOCALLY TRUE."
echo ""
echo "Starting loop with prompt:"
echo "────────────────────────────────────────────────────────────────"
echo "$PROMPT"
echo "────────────────────────────────────────────────────────────────"
