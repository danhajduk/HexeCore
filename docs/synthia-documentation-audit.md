# synthia-documentation-audit

Purpose: Run a repeatable documentation audit for Synthia repos after major changes or every few days to keep README files, architecture docs, task docs, API notes, and examples aligned with the actual codebase.

## When to use
Use this skill when:
- a major feature, refactor, or architecture change was completed
- API routes, config schemas, manifests, addon contracts, or folder layout changed
- a repo has gone more than a few days without a documentation pass
- before tagging a release or publishing a repo change publicly
- after Codex completed multiple tasks and docs may have drifted

Do not use this skill for direct feature implementation unless the task explicitly includes documentation cleanup.

## Primary goals
1. Detect documentation drift.
2. Update or create missing core docs.
3. Archive or remove stale documentation.
4. Ensure examples match the current implementation.
5. Leave behind a clear audit summary.

## Audit scope
Check these areas first:
- `README.md`
- `docs/`
- `CHANGELOG.md` if present
- `NEXT_TASK.md`, `New_tasks.txt`, roadmap files, or planning docs
- addon manifests and addon SDK docs
- API docs and example payloads
- docker, compose, env, and install instructions
- architecture diagrams or folder trees

## Required workflow

### 1) Inspect the repo before editing
Review at minimum:
- top-level folder structure
- active entrypoints
- config models / schemas
- API routers and exposed endpoints
- manifests, service definitions, compose files
- frontend route registration if applicable
- current docs that describe the above

### 2) Compare docs against code
Look for mismatches such as:
- wrong file paths
- outdated route paths
- missing required fields in payload examples
- old environment variables
- stale screenshots or UI descriptions
- docs describing removed features
- roadmap items marked done but not actually implemented
- implemented features not documented anywhere

### 3) Classify documentation state
Use these buckets:
- `accurate`
- `needs-update`
- `missing`
- `stale-remove-or-archive`

### 4) Fix the highest-value docs first
Priority order:
1. broken setup/install/run instructions
2. incorrect API or config docs
3. wrong architecture descriptions
4. missing addon/integration developer guidance
5. roadmap/task status cleanup
6. cosmetic wording cleanup

### 5) Prefer small truthful docs over big vague docs
Rules:
- do not invent features
- do not describe “planned” work as if it exists
- clearly label roadmap/future items
- prefer code-verified examples
- keep examples copy-pasteable
- keep names and paths exact

### 6) Produce an audit summary
At the end, append or provide a summary with:
- files reviewed
- files updated
- stale docs archived/removed
- unresolved gaps
- recommended next doc tasks

## Documentation standards

### README minimum standard
Each repo README should clearly state:
- what the repo is
- what role it plays in Synthia
- current status/stability
- key features that actually exist
- local run/dev instructions
- config location and major env vars
- link to deeper docs if needed

### Architecture docs minimum standard
Architecture docs should include:
- major components
- data flow
- trust boundaries where relevant
- external dependencies
- important storage/state locations
- extension points such as addons, workers, or bridges

### API docs minimum standard
For each important endpoint, verify:
- method
- route
- required headers
- request schema
- response shape
- auth requirements
- one valid example

### Addon/integration docs minimum standard
Verify:
- folder structure
- manifest schema
- backend registration pattern
- frontend registration pattern
- config expectations
- lifecycle hooks if supported
- example minimal addon

## Synthia-specific checks
When auditing Synthia repos, pay extra attention to:
- addon manifest fields and compatibility fields
- frontend addon sync/symlink behavior
- gitignore coverage for generated addon frontend links and runtime files
- MQTT topics, reserved namespaces, and routing expectations
- HA/Home Assistant integration boundaries
- Docker compose service names, ports, volumes, and env vars
- state file locations
- security/trust token headers and onboarding flow
- whether completed tasks and roadmap docs reflect real code status

## Output format
When this skill finishes, return:

### Documentation Audit Summary
- Scope:
- Verified against code:
- Updated files:
- Stale/archived files:
- Remaining gaps:
- Recommended follow-up:

If no changes were needed, explicitly say:
`Documentation audit completed. No significant drift found.`

## Guardrails
- Never claim code exists unless verified in the repo.
- Never keep outdated examples just because they look useful.
- If a doc cannot be verified, mark it as unverified or future/planned.
- Prefer deleting stale claims over preserving misleading docs.
- Keep terminology consistent across repos.

## Suggested cadence
Run this skill:
- after every major architecture or API change
- after every 5 to 10 implementation tasks
- before releases
- once every few days during active development
