# DECISIONS — RailSathi AI

## Decision Log

### DEC-001 — Project Brain Directory Structure
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Use `.agent/` directory at repository root for project memory and management infrastructure.
- **Context**: The instruction specifies `.agent/` structure. Repository was empty — no existing conventions to conflict with.
- **Alternatives**: `.project/`, `.memory/`, root-level files — none had precedent in this repo.
- **Rationale**: Follows the specified structure exactly. Clean namespace, won't conflict with common tooling directories.
- **Consequences**: All project state, decisions, tasks, and session logs live under `.agent/`.
- **Related files**: `.agent/*`

---

### DEC-002 — Fresh Repository Initialization
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Initialize a fresh Git repository on `master` branch since the directory was completely empty.
- **Context**: Directory `d:\hackathons and projects\RailSaathi` contained no files and no `.git/` directory.
- **Alternatives**: Wait for user to initialize — would block all work.
- **Rationale**: Git is required for change tracking per project rules. `git init` is non-destructive on an empty directory.
- **Consequences**: Branch is `master` (Git default). No commits yet. Will need initial commit after bootstrap approval.
- **Related files**: `.git/`

---

### DEC-003 — Target Technology Stack
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Target stack: React+Vite+Tailwind (frontend), Python+Flask (backend), Gemini API (LLM), JSON/SQLite (knowledge), pytest (testing).
- **Context**: Specified in master engineering instruction. Environment verified: Node v24.13.1, Python 3.14.0.
- **Alternatives**: None proposed — this is the specified stack.
- **Rationale**: Matches instruction requirements and available toolchain.
- **Consequences**: May need to verify Python 3.14 compatibility with Flask and other dependencies before implementation.
- **Related files**: None yet — no dependencies installed.
