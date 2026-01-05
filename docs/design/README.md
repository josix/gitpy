# gitpy Design Documentation

This directory contains detailed design specifications for implementing Git's core functionality in Python.

## Document Index

| Phase | Document | Description |
|-------|----------|-------------|
| 1 | [Object Model](phase1_object_model.md) | Blob, Tree, Commit, Tag objects and SHA-1 hashing |
| 2 | [Object Storage](phase2_object_storage.md) | Loose objects, compression, repository initialization |
| 3 | [References](phase3_references.md) | HEAD, branches, tags, reflog, revision parsing |
| 4 | [Index](phase4_index.md) | Staging area, binary format, status tracking |
| 5-8 | [Commands](phase5_8_commands.md) | Diff engine, plumbing/porcelain commands, merge |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI (gitpy)                              │
├─────────────────────────────────────────────────────────────────┤
│                    Porcelain Commands                           │
│  init │ add │ commit │ status │ log │ diff │ branch │ checkout │
├─────────────────────────────────────────────────────────────────┤
│                    Plumbing Commands                            │
│  hash-object │ cat-file │ ls-tree │ write-tree │ commit-tree   │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   References    │      Index      │         Diff Engine         │
│  HEAD, branches │  staging area   │   Myers algorithm, hunks    │
│  tags, reflog   │  binary format  │   unified format            │
├─────────────────┴─────────────────┴─────────────────────────────┤
│                      Object Database                            │
│              loose objects │ compression │ SHA-1                │
├─────────────────────────────────────────────────────────────────┤
│                       Object Model                              │
│                 Blob │ Tree │ Commit │ Tag                      │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Priority

### Tier 1: Foundation (Must Have)
- Object model (blob, tree, commit)
- Object storage with compression
- Basic references (HEAD, branches)
- Index read/write

### Tier 2: Core Commands (Should Have)
- `init`, `add`, `commit`, `status`
- `log`, `diff`
- `branch`, `checkout`

### Tier 3: Extended (Nice to Have)
- Tags (annotated)
- Reflog
- Merge
- Remote operations

## Key Design Decisions

### 1. Content-Addressable Storage
All objects are identified by SHA-1 hash of their contents, enabling:
- Automatic deduplication
- Integrity verification
- Immutability guarantees

### 2. Separation of Concerns
- **Objects**: Immutable data structures
- **References**: Mutable pointers to objects
- **Index**: Staging area between working directory and repository
- **Commands**: Operations on the above

### 3. Git Compatibility
Binary formats (index, packfiles) match Git exactly for interoperability.

### 4. Minimal Dependencies
Core implementation uses Python standard library only:
- `hashlib` for SHA-1
- `zlib` for compression
- `struct` for binary parsing

## Testing Strategy

Each phase includes:
1. **Unit tests**: Individual component testing
2. **Integration tests**: Command workflows
3. **Compatibility tests**: Verify against real Git
4. **Property tests**: Serialization roundtrips (hypothesis)

## Getting Started

1. Read Phase 1 (Object Model) first
2. Each phase builds on previous phases
3. Implementation code goes in `gitpy/` package
4. Tests go in `tests/` directory

## Contributing

When implementing a phase:
1. Follow the specification exactly
2. Write tests before or alongside code
3. Verify compatibility with real Git
4. Update documentation as needed
