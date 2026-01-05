---
allowed-tools: Bash(rm*), Bash(cat*), Bash(test*), Read
description: Cancel an active Ralph loop
---

Cancel the currently active Ralph Wiggum loop.

## Process

1. Check if a loop is active (`.claude/ralph-loop.local.md` exists)
2. If active, show current iteration and remove the state file
3. If not active, report that no loop is running

## Command

```bash
if [[ -f .claude/ralph-loop.local.md ]]; then
    echo "Cancelling ralph loop..."
    cat .claude/ralph-loop.local.md | head -20
    rm .claude/ralph-loop.local.md
    echo "Loop cancelled."
else
    echo "No active ralph loop found."
fi
```

Run the above command to cancel any active loop.
