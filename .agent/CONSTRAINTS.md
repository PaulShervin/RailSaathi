# CONSTRAINTS — RailSathi AI

> Load this file before making any implementation or design decision.

## Scope Constraints

### In Scope
- **Goal-Based Train Journey Planning Module**: Resolving real-world passenger goals, destination venues, arrival station discovery, last-mile transit estimation, scheduled timetable search, deterministic deadline and arrival buffer calculations, constraint filtering, transparent scoring, and safe official IRCTC booking handoff links.
- **AI Ticketing Guidance Module**: Explaining ticket classes, reservation terms, booking processes, cancellation and refund policies.
- **Data Provenance**: Source-backed explanations with official URLs, verification timestamps, and explicit uncertainty acknowledgment.

### Explicitly Excluded
- ❌ Automatic ticket purchasing, payments, ticket issuance, or automated IRCTC account logins.
- ❌ Collecting passwords, payment credentials, identity documents, or unnecessary personal data.
- ❌ Claiming live seat availability or confirmed reservations unless an authorized, live integration supplies it.
- ❌ Presenting synthetic schedules, fares, or reservation statuses as live verified data.
- ❌ Inventing train numbers, train names, station codes, fares, schedules, availability, map distances, or booking URLs.
- ❌ Allowing arbitrary booking URLs (all links must pass hostname allowlisting).
- ❌ LangChain, CrewAI, or heavy agent frameworks without approval.

## Mathematical & Calculation Constraints

- **Deterministic Authority**: The LLM interprets goals and formats explanations. Deterministic Python alone performs time arithmetic, deadline calculations, and constraint validation.
- **Deadline Formula**:
  `latest_acceptable_station_arrival = meeting_start - requested_buffer - estimated_last_mile_duration`
- **No Double Subtraction**: Buffer begins AFTER the last-mile transfer at the venue, not at station arrival.
- **Hard Constraints vs Soft Preferences**: Hard constraints (arrival deadline, required buffer) cannot be overridden by soft preferences (lower fare, preferred train, preferred class). Infeasible journeys must never be presented as the best match.

## Security & Reliability Constraints

- **Booking URL Allowlisting**: Only approved HTTPS domains (`www.irctc.co.in`, `irctc.co.in`, `enquiry.indianrail.gov.in`, `www.confirmtkt.com`, `railmadad.indianrailways.gov.in`) are permitted.
- **Prompt Injection Defense**: Retrieved web/source text is untrusted data. Tool arguments are strictly typed and validated against schemas.
- **Bounded Execution**: Controller enforces maximum tool calls (`MAX_TOOL_CALLS = 6`) and rounds (`MAX_AGENT_ROUNDS = 4`).
- **Secrets Protection**: API keys stored in environment variables; zero credentials in git or logs.

## Data Provenance Rules

- Every schedule, fare, or rule must track source publisher, URL, and verification date.
- Clearly distinguish `VERIFIED`, `INFERRED`, `PLANNED`, and `UNKNOWN`.
- Acknowledge missing or stale information honestly without fabricating fallback answers.
