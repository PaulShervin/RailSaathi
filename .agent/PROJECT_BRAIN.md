# PROJECT BRAIN — RailSathi AI

> Last updated: 2026-10-10

## Project Identity

**RailSathi AI** — Intelligent Indian Railways Ticketing Guidance

A tool-using GenAI application that explains railway ticket classes, reservation terminology, booking procedures, and cancellation/refund guidance using source-backed information.

The AI guides passengers — it does not impersonate railway authorities or perform actual transactions.

## Current Scope

The **AI Ticketing Guidance Module**, supporting:

1. Explaining ticket classes (SL, 3A, 2A, etc.)
2. Explaining reservation terminology (CNF, RAC, WL)
3. Guiding through the official booking process
4. Retrieving cancellation and refund guidance
5. Source-backed explanations with URLs and verification dates
6. Asking clarifying questions when needed
7. Acknowledging missing/stale/ambiguous information honestly

See [CONSTRAINTS.md](./CONSTRAINTS.md) for explicit exclusions.

## Confirmed Technology Stack

| Layer | Technology | Status |
|---|---|---|
| Frontend | React + Vite + Tailwind CSS | PLANNED |
| Backend | Python + Flask | PLANNED |
| LLM | Gemini API (function/tool calling) | PLANNED (API key not yet configured) |
| Knowledge | Structured JSON and/or SQLite | PLANNED |
| Agent Controller | Deterministic Python, tool execution control | PLANNED |
| Testing | Automated (tools, controller, grounding, failures) | PLANNED |

## Implemented Components

**None** — Repository was empty at project start (2026-10-10).

## Current Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) — All components are currently PLANNED.

## Critical Constraints

- No actual ticket purchasing, payments, or booking submission
- No collection of passwords, payment credentials, or identity documents
- No synthetic data presented as live railway data
- No invented rules, URLs, or policy dates
- No LangChain, CrewAI, vector DBs, or embeddings without approval
- Must remain a tool-using agent, not a static FAQ
- See [CONSTRAINTS.md](./CONSTRAINTS.md) for full list

## Important Decisions

| ID | Decision | Date |
|---|---|---|
| DEC-001 | Use `.agent/` directory structure for project brain | 2026-10-10 |
| DEC-002 | Repository initialized fresh on `master` branch | 2026-10-10 |

See [DECISIONS.md](./DECISIONS.md) for full records.

## Current Status

- **Phase**: Project bootstrap and audit
- **Branch**: `master` (no commits yet)
- **Blockers**: Gemini API key not configured in environment
- **Next Action**: Review audit report → approve first implementation milestone

## Known Risks

1. **No Gemini API key** — LLM integration cannot be tested until configured
2. **Python 3.14** — Very new; some dependencies may not yet support it

## Next Recommended Action

Await user review of this audit and bootstrap. Then proceed to **Milestone 1**: Backend skeleton (Flask app, knowledge schema, first tool).

## Detailed Files

- [ARCHITECTURE.md](./ARCHITECTURE.md) — Full architecture
- [DECISIONS.md](./DECISIONS.md) — Decision log
- [CONSTRAINTS.md](./CONSTRAINTS.md) — Hard rules
- [TASKS.md](./TASKS.md) — Work items
- [ISSUES.md](./ISSUES.md) — Known issues
- [TEST_STATUS.md](./TEST_STATUS.md) — Test status
- [diagrams/PROJECT_TREE.md](./diagrams/PROJECT_TREE.md) — Component tree
- [diagrams/DATA_FLOW.md](./diagrams/DATA_FLOW.md) — Request lifecycle
- [sessions/SESSION_INDEX.md](./sessions/SESSION_INDEX.md) — Session log
