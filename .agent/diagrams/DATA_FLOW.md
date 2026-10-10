# DATA FLOW — RailSathi AI

> Last updated: 2026-10-10
> All stages are **PLANNED** — no application code implemented yet.

## Request Lifecycle

```mermaid
sequenceDiagram
    participant P as Passenger
    participant FE as Frontend<br/>(React)
    participant API as Flask API
    participant CTRL as Agent Controller
    participant LLM as Gemini LLM
    participant TOOL as Ticketing Tool
    participant KS as Knowledge Store
    participant LOG as Trace Logger

    P->>FE: Types question
    FE->>API: POST /api/chat
    API->>CTRL: Validate & forward request
    
    Note over CTRL: Check call budget<br/>Initialize trace

    CTRL->>LLM: Send question + system prompt + tool schemas
    LLM-->>CTRL: Function call request (tool + args)

    Note over CTRL: Validate tool name<br/>Validate arguments<br/>Check budget remaining

    CTRL->>TOOL: Execute approved tool call
    TOOL->>KS: Query knowledge
    KS-->>TOOL: Evidence + source metadata
    TOOL-->>CTRL: Structured result + sources

    Note over CTRL: Log tool call + result

    CTRL->>LLM: Return tool result for synthesis
    LLM-->>CTRL: Synthesized answer with source citations

    Note over CTRL: Grounding check:<br/>- Evidence supports claims?<br/>- Sources cited?<br/>- No invented rules?

    CTRL-->>API: Response + sources + trace ID
    API-->>FE: JSON response
    FE-->>P: Display answer with source links

    CTRL->>LOG: Write full execution trace

    Note over CTRL: Budget exceeded?<br/>→ Return partial + explanation
    Note over CTRL: No evidence found?<br/>→ Return insufficient-info response
    Note over CTRL: API error?<br/>→ Return error, no unbounded retry
```

## Error & Abstention Flows

```mermaid
flowchart TD
    Q["Passenger Question"] --> VALIDATE["Validate Input"]
    VALIDATE -->|Invalid| REJECT["Return validation error"]
    VALIDATE -->|Valid| INTENT["LLM: Interpret intent"]
    
    INTENT --> TOOLCALL["LLM requests tool call"]
    TOOLCALL --> TVALID{"Tool & args\nvalid?"}
    
    TVALID -->|No| ARGERR["Reject: invalid tool/args"]
    TVALID -->|Yes| BUDGET{"Budget\nremaining?"}
    
    BUDGET -->|No| PARTIAL["Return partial result\n+ budget explanation"]
    BUDGET -->|Yes| EXEC["Execute tool"]
    
    EXEC --> RESULT{"Result\nstatus?"}
    
    RESULT -->|Error/Timeout| APIERR["Return error status\nNo unbounded retry"]
    RESULT -->|Empty| NODATA["Return insufficient-info\nresponse"]
    RESULT -->|Success| EVIDENCE{"Evidence\nsupports answer?"}
    
    EVIDENCE -->|Contradictory| CONFLICT["Acknowledge contradiction\nDo not pick arbitrarily"]
    EVIDENCE -->|Stale| STALE["Answer + staleness warning"]
    EVIDENCE -->|Sufficient| SYNTH["Synthesize answer\nCite sources"]
    
    SYNTH --> GROUND{"Grounding\ncheck passed?"}
    GROUND -->|No| REVISE["Revise or abstain"]
    GROUND -->|Yes| RESPOND["Return sourced answer"]

    style REJECT fill:#ffcdd2
    style ARGERR fill:#ffcdd2
    style PARTIAL fill:#fff9c4
    style APIERR fill:#ffcdd2
    style NODATA fill:#fff9c4
    style CONFLICT fill:#fff9c4
    style STALE fill:#fff9c4
    style REVISE fill:#fff9c4
    style RESPOND fill:#c8e6c9
```

## Dependency Diagram

```mermaid
graph LR
    subgraph "Frontend"
        FE["React App"]
    end

    subgraph "Backend"
        APP["Flask app.py"]
        CTRL["agent/controller.py"]
        LLM_MOD["agent/llm.py"]
        T_CLASS["tools/ticket_class.py"]
        T_STATUS["tools/reservation_status.py"]
        T_BOOK["tools/booking_guidance.py"]
        T_CANCEL["tools/cancellation_refund.py"]
        KS_MOD["knowledge/store.py"]
        LOG_MOD["logging/tracer.py"]
    end

    subgraph "External"
        GEMINI["Gemini API"]
    end

    FE -->|HTTP| APP
    APP -->|imports| CTRL
    CTRL -->|imports| LLM_MOD
    CTRL -->|imports| T_CLASS
    CTRL -->|imports| T_STATUS
    CTRL -->|imports| T_BOOK
    CTRL -->|imports| T_CANCEL
    CTRL -->|imports| LOG_MOD
    LLM_MOD -->|calls| GEMINI
    T_CLASS -->|imports| KS_MOD
    T_STATUS -->|imports| KS_MOD
    T_BOOK -->|imports| KS_MOD
    T_CANCEL -->|imports| KS_MOD
```
