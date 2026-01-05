---
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(*), Task(*), Skill(*)
description: Implement a gitpy phase using ralph-wiggum loop until complete
argument-hint: <phase_number>
---

Implement a gitpy component using the ralph-wiggum verification loop.

**Phase to implement**: $ARGUMENTS

## Invocation

Start the ralph-wiggum loop for automated implementation:

```
/ralph-loop "Implement gitpy Phase $ARGUMENTS following these steps:

1. Read the design spec from docs/design/phase${ARGUMENTS}*.md
2. Read docs/design/python312_features.md for syntax requirements
3. Create the module structure in gitpy/
4. Implement all classes following the spec exactly
5. Write comprehensive tests in tests/
6. Run: ruff format <files> && ruff check <files> --fix
7. Run: mypy <files>
8. Run: pytest tests/<module> -v
9. If tests fail, analyze and fix
10. Verify Git compatibility using known hashes

Success criteria:
- All classes from spec implemented
- All tests passing
- ruff and mypy clean
- Git compatibility verified

Output <promise>PHASE_COMPLETE</promise> when all criteria met.
" --max-iterations 30 --completion-promise "PHASE_COMPLETE"
```

## Phase Reference

| Phase | Spec File | Components |
|-------|-----------|------------|
| 1 | `phase1_object_model.md` | Blob, Tree, Commit, Tag |
| 2 | `phase2_object_storage.md` | LooseObjectStore, ObjectDatabase |
| 3 | `phase3_references.md` | RefManager, HEAD, Branch |
| 4 | `phase4_index.md` | Index, IndexEntry |

## Verification Hashes

- Empty blob: `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391`
- Empty tree: `4b825dc642cb6eb9a060e54bf8d69288fbee4904`
- `"hello\n"` blob: `ce013625030ba8dba906f756967f9e9ca394464a`
