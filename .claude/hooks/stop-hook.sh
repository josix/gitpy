#!/bin/bash
# stop-hook.sh - Stop hook for session cleanup and ralph-wiggum loops
# Runs consistency checks and handles self-referential loops

set -e

CLAUDE_DIR="${CLAUDE_LOCAL_DIR:-.claude}"
STATE_FILE="$CLAUDE_DIR/ralph-loop.local.md"
SCRIPT_DIR="$(cd "$(dirname "$0")/../scripts" 2>/dev/null && pwd)"

# Run consistency check on session end (non-blocking)
run_consistency_check() {
    if [[ -x "$SCRIPT_DIR/check-consistency.sh" ]]; then
        bash "$SCRIPT_DIR/check-consistency.sh" || true
    fi
}

# If no active loop, run checks and allow normal exit
if [[ ! -f "$STATE_FILE" ]]; then
    run_consistency_check >&2
    echo '{"decision": "allow"}'
    exit 0
fi

# Parse state file frontmatter
parse_frontmatter() {
    local key="$1"
    sed -n '/^---$/,/^---$/p' "$STATE_FILE" | grep "^$key:" | head -1 | sed "s/^$key: *//" | tr -d '"'
}

# Get current state
ITERATION=$(parse_frontmatter "iteration")
MAX_ITERATIONS=$(parse_frontmatter "max_iterations")
COMPLETION_PROMISE=$(parse_frontmatter "completion_promise")

# Validate iteration is numeric
if ! [[ "$ITERATION" =~ ^[0-9]+$ ]]; then
    echo "Warning: Corrupted state file (invalid iteration). Removing..." >&2
    rm -f "$STATE_FILE"
    echo '{"decision": "allow"}'
    exit 0
fi

# Extract prompt from state file (everything after the second ---)
PROMPT=$(sed -n '/^## Prompt$/,$ p' "$STATE_FILE" | tail -n +2)

# Check if completion promise was output in the last message
# Look for <promise>COMPLETION_PROMISE</promise> pattern
if [[ -n "$COMPLETION_PROMISE" ]]; then
    # Check the transcript or last output for the promise
    TRANSCRIPT_FILE="${CLAUDE_TRANSCRIPT_FILE:-}"
    if [[ -n "$TRANSCRIPT_FILE" && -f "$TRANSCRIPT_FILE" ]]; then
        # Extract last assistant message and check for promise
        LAST_MESSAGE=$(tail -100 "$TRANSCRIPT_FILE" 2>/dev/null | grep -o "<promise>.*</promise>" | tail -1 || true)
        if [[ "$LAST_MESSAGE" == "<promise>$COMPLETION_PROMISE</promise>" ]]; then
            echo "╔════════════════════════════════════════════════════════════════╗" >&2
            echo "║                    LOOP COMPLETE! ✓                            ║" >&2
            echo "╠════════════════════════════════════════════════════════════════╣" >&2
            echo "║ Completion promise detected: $COMPLETION_PROMISE" >&2
            echo "║ Total iterations: $ITERATION" >&2
            echo "╚════════════════════════════════════════════════════════════════╝" >&2
            rm -f "$STATE_FILE"
            echo '{"decision": "allow"}'
            exit 0
        fi
    fi
fi

# Check max iterations
NEXT_ITERATION=$((ITERATION + 1))
if [[ $NEXT_ITERATION -gt $MAX_ITERATIONS ]]; then
    echo "╔════════════════════════════════════════════════════════════════╗" >&2
    echo "║                    MAX ITERATIONS REACHED                      ║" >&2
    echo "╠════════════════════════════════════════════════════════════════╣" >&2
    echo "║ Completed $MAX_ITERATIONS iterations without completion promise" >&2
    echo "╚════════════════════════════════════════════════════════════════╝" >&2
    rm -f "$STATE_FILE"
    echo '{"decision": "allow"}'
    exit 0
fi

# Update iteration count in state file
sed -i "s/^iteration: .*/iteration: $NEXT_ITERATION/" "$STATE_FILE"
sed -i "s/Iteration: .*/Iteration: $NEXT_ITERATION \/ $MAX_ITERATIONS/" "$STATE_FILE"

# Block exit and feed prompt back
echo "" >&2
echo "╔════════════════════════════════════════════════════════════════╗" >&2
echo "║                    RALPH LOOP ITERATION $NEXT_ITERATION / $MAX_ITERATIONS" >&2
echo "╚════════════════════════════════════════════════════════════════╝" >&2
echo "" >&2

# Construct the response to feed back
SYSTEM_MSG="[Ralph Loop - Iteration $NEXT_ITERATION/$MAX_ITERATIONS]

Your previous work is preserved in files and git history.
Review what you've done and continue working on the task.

"

if [[ -n "$COMPLETION_PROMISE" ]]; then
    SYSTEM_MSG+="When the task is COMPLETELY done, output: <promise>$COMPLETION_PROMISE</promise>

IMPORTANT: Only output the promise when the condition is COMPLETELY TRUE.
Do not output the promise to escape the loop prematurely.

"
fi

SYSTEM_MSG+="Continue with:
$PROMPT"

# Output JSON to block exit and provide new prompt
# Note: The exact format depends on Claude Code's hook API
cat << EOF
{
  "decision": "block",
  "message": $(echo "$SYSTEM_MSG" | jq -Rs .)
}
EOF
