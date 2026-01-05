---
allowed-tools: Bash(git*), Bash(python*), Read
description: Verify gitpy compatibility with real Git
argument-hint: <component>
---

Verify that gitpy's implementation matches real Git behavior.

Component to verify: $ARGUMENTS

## Verification Steps

1. **Create test data with real Git**:
   ```bash
   cd /tmp && rm -rf git-test && mkdir git-test && cd git-test
   git init
   echo "test content" > test.txt
   git add test.txt
   git commit -m "test commit"
   ```

2. **Extract Git's internal data**:
   - List objects: `git rev-list --objects --all`
   - Show object: `git cat-file -p <sha>`
   - Show type: `git cat-file -t <sha>`
   - Dump index: `git ls-files --stage`

3. **Compare with gitpy**:
   - Parse the same objects with gitpy
   - Verify SHA-1 hashes match
   - Verify serialization roundtrip

4. **Report compatibility**:
   - Objects that match
   - Any discrepancies found
   - Suggested fixes

## Components

- `blob` - Verify blob hashing
- `tree` - Verify tree serialization
- `commit` - Verify commit format
- `index` - Verify index binary format
- `refs` - Verify reference handling
