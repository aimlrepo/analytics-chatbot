# Roadmap & Recommended Next Actions
**Project**: L2L Manufacturing Analytics Assistant (FastAPI + HTMX + DuckDB + TypeDB + LangGraph)  
**Date**: October 2026

---

## 1. Automated Testing & Verification Suite (High Priority)
- [ ] **JEV Fast-Router Test Suite (`tests/test_router.py`)**:
  - Test case-insensitivity on all patterns (greetings, analytical, causal, schema tokens).
  - Test ambiguity fallbacks to the supervisor agent.
- [ ] **Specialist Tool Mocks (`tests/test_tools.py`)**:
  - Unit test `query_l2l_database` and `generate_l2l_chart` with sample DuckDB queries.
  - Mock TypeDB session/transaction to test concept map extraction and circuit breakers.
- [ ] **End-to-End API Tests (`tests/test_api.py`)**:
  - Use `TestClient(app)` from Starlette/FastAPI.
  - Verify `/chat`, `/chat/new`, `/chat/history/{thread_id}`, `/sidebar`, `/sync-cache`, and `/sync-typedb`.

---

## 2. Streaming & UX Enhancement (Medium-High Priority)
- [ ] **LangGraph Streaming via SSE**:
  - Upgrade `/chat` from blocking `agent_app.invoke()` to streaming events (`agent_app.astream_events`).
  - Use Server-Sent Events (SSE) or HTMX WebSocket/SSE extension to stream tokens in real-time.
- [ ] **HTMX UI Polish**:
  - Add `hx-indicator` loading spinners/placeholders while queries/charts are being generated.
  - Add sidebar thread management: Delete thread button, rename thread option, and clear session history.
- [ ] **Dev Endpoint Segregation**:
  - Move isolated test endpoints (`/test-chart`, `/test-htmx-page`, `/test-htmx-response`) from `main.py` into a separate development router (`src/routes/dev.py`) enabled only when `DEBUG=True`.

---

## 3. Security, Guardrails & Sandboxing (Medium Priority)
- [ ] **SQL & TypeQL Sandboxing**:
  - Use `sqlglot` to parse generated SQL before execution and restrict commands strictly to read-only `SELECT` statements (blocking `ATTACH`, `COPY`, file operations).
  - Sanitize TypeQL input to prevent injection in `query_typedb`.
- [x] **Activate NeMo Guardrails** (Completed):
  - Integrated `src/guardrails.py` with fast heuristics and NeMo `self_check_input` rail.
  - Added entry-point `guardrails` node in `src/agent.py` guarding against jailbreaks and prompt injections.
- [ ] **API Authentication**:
  - Protect ETL triggers (`/sync-cache`, `/sync-typedb`) and user endpoints with API keys or OAuth2 tokens.

---

## 4. Ingestion & Pipeline Robustness (Medium Priority)
- [ ] **Incremental BigQuery Sync**:
  - Replace full table overwrite (`CREATE OR REPLACE TABLE`) in `src/cache_pyarrow.py` with an incremental sync using watermark timestamps (`WHERE dispatch_reported > (SELECT COALESCE(MAX(dispatch_reported), '1970-01-01') FROM f_l2l_dispatches)`).
- [ ] **Automated Background Sync**:
  - Add APScheduler or Celery/cron task to periodically trigger delta refreshes.

---

## 5. Enterprise Connectors & Ecosystem Integration (Upcoming)
- [ ] **Gemini Enterprise / Vertex AI Agent Builder OpenAPI Connector**:
  - Expose REST API endpoints in `main.py`:
    - `POST /api/v1/analytics/sql` (DuckDB queries over `f_l2l_dispatches` & `event_answers`).
    - `POST /api/v1/analytics/typedb` (TypeDB Knowledge Graph operational disruption & triage).
  - Export OpenAPI 3.0 specification (`/openapi.json`).
  - Register as an OpenAPI Tool in Vertex AI Agent Builder / Gemini Enterprise with authentication (API Key / Cloud IAM bearer token).
- [ ] **TypeDB 3.x Migration (Post-Demo)**:
  - Bump container to `vaticle/typedb:3.x` and driver to `typedb-driver>=3.0.0`.
  - Update `schema.tql` to replace rules with TypeDB 3 schema functions (`define function`).
  - Update `src/typedb_sync.py` and `src/prompts/typedb_prompt.py` to TypeQL 3 syntax.
