---
allowed-tools: Bash(bash*), Read, Write, Edit, Glob, Grep, Bash(uv*), Bash(git*)
description: Implement a phase with ralph-wiggum loop until complete
argument-hint: <phase_number|component>
---

Start a ralph loop to implement a gitpy component until tests pass.

Argument: $ARGUMENTS

## Setup

Initialize the implementation loop:

```bash
bash .claude/scripts/setup-ralph-loop.sh \
    --max-iterations 30 \
    --completion-promise "PHASE_COMPLETE" \
    "Implement Phase $ARGUMENTS from the design specifications.

Read docs/design/ for the relevant design doc.
Follow the specification exactly.

Use Python 3.12+ features:
- type X = ... for type aliases
- Self for return types
- match/case for pattern matching
- @dataclass(slots=True) for data classes
- list[X] not List[X], X | None not Optional[X]

Steps each iteration:
1. Read the design spec if not already done
2. Implement or fix code based on spec
3. Run tests: uv run pytest tests/ -v
4. If tests pass, output: <promise>PHASE_COMPLETE</promise>
5. If tests fail, analyze and fix

Reference hashes (must match real Git):
- Empty blob: e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
- Empty tree: 4b825dc642cb6eb9a060e54bf8d69288fbee4904

Only output <promise>PHASE_COMPLETE</promise> when ALL tests pass."
```

## Phases

| Phase | Design Doc | Components |
|-------|------------|------------|
| 1 | phase1_object_model.md | Blob, Tree, Commit, Tag |
| 2 | phase2_object_storage.md | LooseObjectStore, ObjectDatabase |
| 3 | phase3_references.md | RefManager, HEAD, Branch |
| 4 | phase4_index.md | Index, IndexEntry |
| 5-8 | phase5_8_commands.md | Diff, Commands |

## Completion

The loop ends when you output `<promise>PHASE_COMPLETE</promise>` after all tests pass.
