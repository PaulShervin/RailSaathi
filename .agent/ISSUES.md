# ISSUES — RailSathi AI

## Open Issues

### ISSUE-001: Gemini API Key Not Configured in Environment
- **Severity**: Low (DevMock handles offline mode)
- **Discovered**: 2026-10-10 (Session 001)
- **Description**: `GEMINI_API_KEY` is not populated in `.env`.
- **Impact**: Backend runs with `DevMockGeminiClient` supporting all tool invocations and full UI experience. When live quota is desired, user sets `GEMINI_API_KEY`.
- **Resolution**: User to provide key when live Gemini API queries are required.

## Closed Issues

### ISSUE-002: Python 3.14 Compatibility Risk
- **Severity**: Resolved
- **Discovered**: 2026-10-10 (Session 001)
- **Resolution**: Verified all dependencies (`google-genai` 2.29, `flask` 3.1.3, `pydantic` 2.14, `pytest` 9.1.1) install and run cleanly on Python 3.14.7.
- **Closed**: 2026-10-10 (Session 003)

### ISSUE-003: RollDown Native Binding on Linux
- **Severity**: Resolved
- **Discovered**: 2026-10-10 (Session 003)
- **Description**: Frontend `node_modules` had Windows binaries previously.
- **Resolution**: Ran `npm install` in `frontend/` on Linux; Vite 8.3 production build now executes in 168ms with 0 errors.
- **Closed**: 2026-10-10 (Session 003)
