# .agent/ — RailSathi AI Project Brain

This directory contains the persistent project memory and management infrastructure for **RailSathi AI**.

## Quick Start (Session Bootstrap)

Read these files in order:

1. [PROJECT_BRAIN.md](./PROJECT_BRAIN.md) — Compact project summary
2. [CONSTRAINTS.md](./CONSTRAINTS.md) — Hard rules (load before decisions)
3. [CURRENT_STATE.json](./CURRENT_STATE.json) — Machine-readable state
4. [TASKS.md](./TASKS.md) — Actionable work items
5. [ARCHITECTURE.md](./ARCHITECTURE.md) — Verified architecture (read relevant sections)

## Directory Layout

```
.agent/
├── README.md              ← You are here
├── PROJECT_BRAIN.md       ← Authoritative project summary
├── ARCHITECTURE.md        ← Verified architecture documentation
├── DECISIONS.md           ← Architectural decision records
├── CONSTRAINTS.md         ← Hard rules and boundaries
├── CURRENT_STATE.json     ← Machine-readable project state
├── TASKS.md               ← Actionable work items
├── ISSUES.md              ← Known bugs, risks, open questions
├── TEST_STATUS.md         ← Test suites, results, coverage
├── diagrams/
│   ├── PROJECT_TREE.md    ← Mermaid component tree
│   └── DATA_FLOW.md       ← Mermaid request lifecycle
└── sessions/
    ├── SESSION_INDEX.md   ← Session log index
    ├── SESSION_TEMPLATE.md← Template for session records
    └── *.md               ← Individual session records
```

## Rules

- **Append-only sessions**: Never rewrite or delete historical session records.
- **Evidence-based**: All claims must cite code, commands, tests, or Git evidence.
- **Concise**: Optimize for quick context loading; don't copy source code into docs.
- **Constraints first**: Always read CONSTRAINTS.md before making decisions.
