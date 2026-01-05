---
allowed-tools: Bash(bash*), Read, Write
description: Start a self-referential development loop
argument-hint: "<prompt>" [--max-iterations N] [--completion-promise "TEXT"]
---

Start a Ralph Wiggum loop for iterative development.

Arguments: $ARGUMENTS

## How It Works

The ralph loop feeds the same prompt back repeatedly while your work
persists in files and git history. Each iteration, you can:
1. Review previous changes
2. Run tests to check progress
3. Fix issues found
4. Continue until done

## Usage

```bash
bash .claude/scripts/setup-ralph-loop.sh $ARGUMENTS
```

## Examples

```bash
# Implement until tests pass
bash .claude/scripts/setup-ralph-loop.sh --completion-promise "TESTS_PASS" \
    "Implement the Blob class from docs/design/phase1_object_model.md and make all tests pass"

# Fixed iterations
bash .claude/scripts/setup-ralph-loop.sh --max-iterations 10 \
    "Review and improve code quality"
```

## Completion

The loop ends when:
1. You output `<promise>COMPLETION_PROMISE</promise>` (if specified)
2. Max iterations reached
3. You run `/cancel-ralph`

## Important

**Only output the completion promise when the condition is COMPLETELY TRUE.**
Do not output the promise to escape the loop prematurely.
