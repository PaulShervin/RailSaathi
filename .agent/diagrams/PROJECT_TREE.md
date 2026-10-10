# PROJECT TREE — RailSathi AI

> Last updated: 2026-10-10
> Legend: 🟢 IMPLEMENTED & VERIFIED | 🟡 PARTIAL | ⚪ PLANNED | 🔴 BLOCKED

```mermaid
graph TB
    subgraph "RailSathi AI Architecture"
        direction TB

        subgraph "Frontend 🟢"
            UI["Goal-Based Journey Planner & Chat UI<br/>React 18 + Vite 8 + Custom Design System<br/>🟢 IMPLEMENTED<br/><i>frontend/src/</i>"]
        end

        subgraph "Backend API 🟢"
            API["Flask 3.1 REST API Layer<br/>🟢 IMPLEMENTED<br/><i>backend/app.py</i>"]

            subgraph "Journey Planning Core 🟢"
                MOD["Data Models & Schemas<br/>Pydantic 2.14<br/>🟢 IMPLEMENTED<br/><i>backend/journey/models.py</i>"]
                LOC["Location Resolution & Last-Mile<br/>🟢 IMPLEMENTED<br/><i>backend/journey/location.py</i>"]
                TT["Timetable & Fares Service<br/>🟢 IMPLEMENTED<br/><i>backend/journey/timetable.py</i>"]
                FEAS["Feasibility & Deadline Engine<br/>🟢 IMPLEMENTED<br/><i>backend/journey/feasibility.py</i>"]
                RANK["Ranking & Trade-off Engine<br/>🟢 IMPLEMENTED<br/><i>backend/journey/ranking.py</i>"]
                BOOK["Booking Handoff Allowlist<br/>🟢 IMPLEMENTED<br/><i>backend/journey/booking.py</i>"]
                PLAN["Journey Planner Orchestrator<br/>🟢 IMPLEMENTED<br/><i>backend/journey/planner.py</i>"]
            end

            subgraph "Agent & Controller 🟢"
                CTRL["Deterministic Agent Controller<br/>Budget & Trace Tracking<br/>🟢 IMPLEMENTED<br/><i>backend/agent/controller.py</i>"]
                LLM["Gemini Client & DevMock Fallback<br/>🟢 IMPLEMENTED<br/><i>backend/agent/llm.py & mock_llm.py</i>"]
                REG["Unified Tool Registry (13 Tools)<br/>🟢 IMPLEMENTED<br/><i>backend/tools/registry.py</i>"]
            end

            subgraph "Knowledge Store 🟢"
                KS["SQLite FTS5 Knowledge Base<br/>🟢 IMPLEMENTED<br/><i>backend/knowledge/railsaathi.db</i>"]
                RET["FTS5 Keyword & Abbrev Retrieval<br/>🟢 IMPLEMENTED<br/><i>backend/knowledge/retrieval.py</i>"]
            end
        end

        subgraph "Testing Suite 🟢"
            TESTS["67 Automated Tests (100% Passing)<br/>- API Endpoints (test_api.py, test_journey_api.py)<br/>- Feasibility & Calculations (test_journey_planner.py)<br/>- 10 Mandatory E2E Scenarios (test_e2e_scenarios.py)<br/>- Controller & Retrieval Tests<br/>🟢 IMPLEMENTED<br/><i>tests/</i>"]
        end

        subgraph "Project Brain 🟢"
            PB[".agent/<br/>Canonical Persistent Agent Memory<br/>🟢 SYNCHRONIZED"]
        end
    end

    UI --> API
    API --> PLAN
    API --> CTRL
    PLAN --> LOC
    PLAN --> TT
    PLAN --> FEAS
    PLAN --> RANK
    PLAN --> BOOK
    CTRL --> LLM
    CTRL --> REG
    REG --> KS

    style UI fill:#c8e6c9,stroke:#2e7d32
    style API fill:#c8e6c9,stroke:#2e7d32
    style MOD fill:#c8e6c9,stroke:#2e7d32
    style LOC fill:#c8e6c9,stroke:#2e7d32
    style TT fill:#c8e6c9,stroke:#2e7d32
    style FEAS fill:#c8e6c9,stroke:#2e7d32
    style RANK fill:#c8e6c9,stroke:#2e7d32
    style BOOK fill:#c8e6c9,stroke:#2e7d32
    style PLAN fill:#c8e6c9,stroke:#2e7d32
    style CTRL fill:#c8e6c9,stroke:#2e7d32
    style LLM fill:#c8e6c9,stroke:#2e7d32
    style REG fill:#c8e6c9,stroke:#2e7d32
    style KS fill:#c8e6c9,stroke:#2e7d32
    style RET fill:#c8e6c9,stroke:#2e7d32
    style TESTS fill:#c8e6c9,stroke:#2e7d32
    style PB fill:#c8e6c9,stroke:#2e7d32
```
