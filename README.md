### 1. Executive Summary                                                                     
                                                                                               
The project is a production-ready, full-stack Manufacturing Analytics Assistant tailored for 
Leading2Lean (L2L) dispatch and maintenance data. It enables factory managers and engineers  
to query maintenance dispatches, downtime, operational metrics, and production orders using   
natural language, returning both formatted tabular data and dynamic interactive charts.       

──────                                                                                       
### 2. Key Achievements & Implemented Capabilities                                           

#### A. Multi-Site Curated Data Architecture (BigQuery → DuckDB via PyArrow)

• High-Performance Local OLAP: Implemented in `src/cache_pyarrow.py`, `sync_bigquery_to_duckdb` 
synchronizes upstream cloud data from `k-bicloud-curated-0001-p.l2l` into a local embedded DuckDB cache (`cache.duckdb`):
  1. `f_l2l_dispatches`: Unified `UNION ALL` across all three plant sites:
     - `dispatches_240` (Stargard, Site 240)
     - `dispatches_260` (Shanghai, Site 260)
     - `dispatches_276` (Ottawa, Site 276)
     Includes both internal surrogate key `id` and human-facing `dispatchnumber`.
  2. `event_answers`: Production order event answers from `event_answers`.
• Relational Modeling: Links production orders to dispatches via `f_l2l_dispatches.id = event_answers.dispatch`.
• Zero-Copy Streaming: Streams chunk-by-chunk using PyArrow RecordBatches directly into DuckDB tables.
• Cost & Speed Optimization: Prevents slow queries and expensive BigQuery charges by serving agent SQL queries locally.

#### B. LangGraph ReAct Agent & Multi-Turn Memory                                            

• ReAct Graph Engine: Set up in `src/agent.py` with dynamic prompt injection (`get_agent_system_prompt`) 
that embeds schema knowledge for both dispatches and production orders, temporal context, and site mappings 
(e.g., Site 240 → Stargard, Site 260 → Shanghai, Site 276 → Ottawa).
• Persistent State & Sessions: Integrated with PostgreSQL via PostgresSaver (`l2l_chat_memory` database), 
allowing conversation sessions to persist across restarts and reloads.
• Tools Implemented (`src/tools.py`):
    • `query_l2l_database`: Executes analytical SQL across both tables and renders Markdown tables.
    • `generate_l2l_chart`: Directly compiles SQL results into responsive Plotly bar, line, pie, or scatter charts.

#### C. Hypermedia Frontend (FastAPI + HTMX + Tailwind + Plotly)                             

• No Node.js/React Build Dependency: Utilizes FastAPI server-side rendering with Jinja2 and 
HTMX for reactive SPA-like interactions without frontend build tooling.
• Interactive Chat UI:
    • `base.html`: Dark-themed layout using Tailwind CSS CDN and Plotly.js.
    • `chat_area.html`: Message container and submission form.
    • `sidebar.html`: Multi-thread navigation list with automated semantic naming (`DDMonYY-HH:MM:SS-<Slug>`).
    • `chat_response_partial.html`: HTMX response partial that swaps in bot answers, renders 
    Plotly charts on the fly, and uses Out-Of-Band (OOB) swaps to update active thread titles and refresh the sidebar.
• Session History Replay: `src/utils/helpers.py:extract_history_turns` parses stored 
checkpointer turns so past threads reload with all interactive charts fully rendered.

#### D. Model Provider Flexibility                                                           

• Configured via `.env` to switch seamlessly between OpenAI (`gpt-4o`) and Google GenAI (`gemini-1.5-pro`).

#### E. External Protocol Support (Model Context Protocol)                                   

• `src/mcp_server.py`: Built with FastMCP to expose DuckDB dispatches and production order query 
tools over standard MCP, enabling external MCP-compatible AI clients (Claude Desktop, IDE agents) to query the dataset.

#### F. Guardrails & Containerized Infrastructure                                            

• Security & Rails: `config.yml` configures NeMo Guardrails to guard against prompt injection and jailbreaks.
• Container Orchestration:
    • `Dockerfile`: Python 3.11-slim container.
    • `docker-compose.yml`: Coordinates the web application, DuckDB data volume, GCP authentication credentials, and PostgreSQL 16 Alpine service.

──────                                                                                       
### 3. Current Project Layout                                                                

```text
C:\AI_dev\l2l-analytics-chatbot\
├── main.py                               # FastAPI routes & HTMX handlers
├── docker-compose.yml                    # Multi-container orchestration (App + Postgres 16)
├── Dockerfile                            # App container definition
├── requirements.txt                      # Project dependencies
├── config/config.yml                     # NeMo Guardrails configuration
├── data/cache.duckdb                     # Local OLAP DuckDB database cache
├── src/
│   ├── agent.py                          # LangGraph ReAct agent & PostgresSaver
│   ├── cache_pyarrow.py                  # PyArrow streaming BigQuery -> DuckDB sync (Sites 240, 260, 276 & Event Answers)
│   ├── tools.py                          # DuckDB query & Plotly chart tools
│   ├── mcp_server.py                     # FastMCP server for external clients
│   ├── prompts/agent_prompt.py           # Dynamic system prompt, dual schemas & join rules
│   └── utils/helpers.py                  # Thread generation & history turn parser
└── templates/                            # HTMX + Tailwind Jinja2 templates
```
