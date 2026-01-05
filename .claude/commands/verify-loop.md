---
allowed-tools: Bash(bash*), Bash(git*), Bash(uv*), Read
description: Verify Git compatibility in a loop until all pass
argument-hint: [component]
---

Start a ralph loop to verify gitpy against real Git until all checks pass.

Argument: $ARGUMENTS

## Setup

Initialize the verification loop:

```bash
bash .claude/scripts/setup-ralph-loop.sh \
    --max-iterations 20 \
    --completion-promise "VERIFIED" \
    "Verify gitpy $ARGUMENTS implementation against real Git.

Verification steps:
1. Create test data with real Git in /tmp/git-verify-test/
2. Extract internal data (objects, refs, index)
3. Parse/generate same data with gitpy
4. Compare SHA-1 hashes and content
5. Fix any discrepancies

Reference hashes that MUST match:
- Empty blob: e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
- Empty tree: 4b825dc642cb6eb9a060e54bf8d69288fbee4904
- 'hello\\n' blob: ce013625030ba8dba906f756967f9e9ca394464a

Only output <promise>VERIFIED</promise> when:
- All SHA-1 hashes match real Git
- All serialization roundtrips work
- Git can read gitpy output and vice versa"
```

## Components

- `blob` - Verify blob hashing and content
- `tree` - Verify tree serialization and sorting
- `commit` - Verify commit format
- `index` - Verify index binary format
- `refs` - Verify reference handling
- `all` - Verify all components

## Completion

Output `<promise>VERIFIED</promise>` only when all verification checks pass.
