---
allowed-tools: Bash(*), Read, Task(*), Skill(*)
description: Run ralph-wiggum verification loop until all tests pass and Git compatible
argument-hint: [component]
---

Run continuous verification loop until gitpy matches real Git behavior.

**Component**: $ARGUMENTS (or "all" for full verification)

## Invocation

Start ralph-wiggum verification loop:

```
/ralph-loop "Verify gitpy $ARGUMENTS against real Git:

Verification Steps:
1. Create test data with real Git in /tmp/git-test
2. Run gitpy against same data
3. Compare outputs (SHAs, formats, behavior)
4. If mismatch found:
   - Identify root cause
   - Fix the implementation
   - Re-run verification
5. Run full test suite: pytest tests/ -v

Reference Hashes (must match):
- Empty blob: e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
- Empty tree: 4b825dc642cb6eb9a060e54bf8d69288fbee4904
- 'hello\\n' blob: ce013625030ba8dba906f756967f9e9ca394464a

Success Criteria:
- All reference hashes match
- pytest tests/ passes 100%
- Real Git can read gitpy objects
- gitpy can read real Git objects

Output <promise>VERIFIED</promise> when all pass.
" --max-iterations 20 --completion-promise "VERIFIED"
```

## Component Options

- `blob` - Verify blob hashing and serialization
- `tree` - Verify tree format and sorting
- `commit` - Verify commit format
- `index` - Verify index binary format
- `refs` - Verify reference handling
- `all` - Full verification suite
