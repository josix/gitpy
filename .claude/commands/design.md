---
allowed-tools: Read, Glob
description: View design specifications for a phase
argument-hint: <phase_number|component>
---

Display the design specification for a gitpy component.

Argument: $ARGUMENTS

## Available Design Docs

| Phase | File | Components |
|-------|------|------------|
| 1 | `docs/design/phase1_object_model.md` | Blob, Tree, Commit, Tag |
| 2 | `docs/design/phase2_object_storage.md` | LooseObjectStore, ObjectDatabase, Repository |
| 3 | `docs/design/phase3_references.md` | RefManager, HEAD, Branch, Tag, Reflog |
| 4 | `docs/design/phase4_index.md` | Index, IndexEntry, read_tree, write_tree |
| 5-8 | `docs/design/phase5_8_commands.md` | Diff, Plumbing, Porcelain commands |

## Other Docs

- `docs/design/python312_features.md` - Python 3.12+ syntax guide
- `docs/design/implementation_agents.md` - Agent breakdown
- `docs/design/README.md` - Architecture overview

Read and summarize the relevant specification.
