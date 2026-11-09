# AGENTS.md

Project documentation lives in the sibling `../Petz5Reframed-Docs` repository
(`C:\GitHub\Petz5Reframed-Docs` in this workspace). Read its `README.md`,
`implementation-status.md` and `completion-plan.md` for project context.
Update documentation there, including the original-game bug-fix record;
do not recreate a `docs` directory in this code repository.
Keep external research as attributed written findings with verification limits.
Do not store imported spreadsheets, their cell exports, or outside reference
images in the documentation repository. Native analysis inventories are separate
from community reference data and must not embed imported workbook values.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

## Mods catalog and engine validation

Read `README.md`, `CONTRIBUTING.md` and `tooling/ENGINE-CONTRACT.md` before
changing catalog tooling or compatibility workflows. The design lives in
`../Petz5Reframed-Docs/mods.md`; runtime adapters live in `../Petz5Reframed`.

- Treat submitted packs as untrusted data. PR validation runs trusted
  base-revision tooling and schemas, not submitted code or workflows. Never
  expose registry or artifact credentials to submitted code.
- Preserve deterministic packages, bounded reads, path/link protections and exact
  hash inventories. Structural validation does not establish gameplay support;
  installability requires the corresponding engine adapter and runtime checks.
- Pin engine compatibility to a trusted commit, artifact run and contract hash.
  Preserve identity checks when adding container-based validation; a mutable
  `main` image tag alone does not identify an approved engine build.
- `ENGINE_ARTIFACT_READ_TOKEN` supports private engine ZIP downloads. GHCR access
  is separate: grant this repository Read under the package's Manage Actions
  access, then use `packages: read` with its automatic `GITHUB_TOKEN` for pulls.
  Pull jobs do not need publishing permissions or a shared publishing secret.
- Keep repository and package visibility unchanged unless explicitly requested.
  Report publication and runtime compatibility only from verified results.
- For tooling changes, run `python -I -m unittest discover -s tests -v` and
  `python -I tooling/catalog.py validate-repository .`. Keep dependencies explicit
  and verify dependency changes in an isolated environment.
