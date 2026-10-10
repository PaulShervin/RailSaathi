# TASKS — RailSathi AI

## Active Tasks

### TASK-001: Repository Audit & Project Brain Bootstrap
- **Status**: IN PROGRESS
- **Priority**: Critical
- **Description**: Inspect empty repo, initialize Git, create `.agent/` project brain infrastructure, create Mermaid diagrams, record initial state.
- **Acceptance criteria**:
  - [x] Repository inspected
  - [x] Git initialized
  - [x] Environment verified
  - [x] `.agent/` structure created
  - [x] All Project Brain files populated
  - [x] Mermaid diagrams created
  - [x] Initial session logged
  - [ ] Initial commit made (awaiting approval)
  - [ ] User review of audit report

## Planned Tasks (Milestone 1: Backend Skeleton)

### TASK-002: Backend Project Setup
- **Status**: PLANNED
- **Priority**: High
- **Description**: Create `backend/` directory, Flask app skeleton, requirements.txt, .env.example, basic health endpoint.
- **Depends on**: TASK-001 complete, user approval

### TASK-003: Knowledge Schema Design
- **Status**: PLANNED
- **Priority**: High
- **Description**: Design JSON/SQLite schema for ticketing knowledge with source attribution fields.
- **Depends on**: TASK-002

### TASK-004: First Ticketing Tool — `explain_ticket_class`
- **Status**: PLANNED
- **Priority**: High
- **Description**: Implement the first read-only tool that retrieves ticket class information from the knowledge store.
- **Depends on**: TASK-003

### TASK-005: Agent Controller Skeleton
- **Status**: PLANNED
- **Priority**: High
- **Description**: Deterministic controller with call budget, tool validation, trace logging, error handling.
- **Depends on**: TASK-004

### TASK-006: Gemini API Integration
- **Status**: PLANNED
- **Priority**: High
- **Description**: Connect agent controller to Gemini API with function calling.
- **Depends on**: TASK-005, BLOCK-001 resolved

## Planned Tasks (Milestone 2: Full Tool Suite)

### TASK-007: Remaining Ticketing Tools
- **Status**: PLANNED
- **Description**: `explain_reservation_status`, `get_booking_guidance`, `get_cancellation_refund_info`

### TASK-008: Source Attribution & Freshness System
- **Status**: PLANNED
- **Description**: Implement freshness checks, staleness warnings, source URL validation.

## Planned Tasks (Milestone 3: Frontend)

### TASK-009: Frontend Setup
- **Status**: PLANNED
- **Description**: React + Vite + Tailwind CSS project, chat interface.

### TASK-010: Frontend-Backend Integration
- **Status**: PLANNED
- **Description**: Connect chat UI to `/api/chat` endpoint.

## Planned Tasks (Milestone 4: Testing & Polish)

### TASK-011: Comprehensive Test Suite
- **Status**: PLANNED
- **Description**: Unit, integration, grounding, and failure-case tests.
