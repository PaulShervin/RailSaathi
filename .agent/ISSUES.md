# ISSUES — RailSathi AI

## Open Issues

### ISSUE-001: Gemini API Key Not Configured
- **Severity**: Blocker (for LLM features)
- **Discovered**: 2026-10-10 (Session 001)
- **Description**: No `GEMINI_API_KEY` or `GOOGLE_API_KEY` environment variable found.
- **Impact**: Cannot develop or test LLM integration (TASK-006).
- **Resolution**: User to create `.env` file with `GEMINI_API_KEY=<key>`. Non-blocking for backend skeleton, tools, and knowledge work.

### ISSUE-002: Python 3.14 Compatibility Risk
- **Severity**: Low (risk)
- **Discovered**: 2026-10-10 (Session 001)
- **Description**: Python 3.14.0 is very recent. Some dependencies (Flask, google-generativeai, etc.) may not officially support it yet.
- **Impact**: Potential import errors or test failures during dependency installation.
- **Resolution**: Verify compatibility during TASK-002. Fall back to venv with older Python if necessary.

## Closed Issues

_None yet._
