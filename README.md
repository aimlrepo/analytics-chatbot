### 1. Executive Summary                                                                     
                                                                                                
The project is a production-ready, full-stack Manufacturing Analytics Assistant tailored for 
Leading2Lean (L2L) dispatch and maintenance data. It uses a **Hierarchical Multi-Agent Architecture**
combining high-performance local OLAP (DuckDB) and semantic Knowledge Graph reasoning (TypeDB).
Factory managers and engineers can query maintenance dispatches, downtime, operational metrics, 
and production orders using natural language, returning formatted tables, interactive charts, 
and multi-hop causal root-cause explanations.

──────                                                                                       
### 2. Key Achievements & Implemented Capabilities                                           

#### A. Multi-Site Curated Data Architecture (BigQuery → DuckDB & TypeDB)

• High-Performance Local OLAP: Implemented in `src/cache_pyarrow.py`, `sync_bigquery_to_duckdb` 
synchronizes upstream cloud data from `k-bicloud-curated-0001-p.l2l` into DuckDB cache (`cache.duckdb`):
  1. `f_l2l_dispatches`: Unified across Sites 240 (Stargard), 260 (Shanghai), and 276 (Ottawa).
  2. `event_answers`: Production order event answers linked via `f_l2l_dispatches.id = event_answers.dispatch`.
• Semantic Knowledge Graph Ingestion: `src/typedb_sync.py` projects DuckDB relational records into TypeDB:
  - Asset containment hierarchy: `site -> area -> line -> machine`.
  - N-ary hyper-relation: `maintenance_dispatch` binding machines, active orders, root cause reasons, and trade skills.
  - Deductive inference rules (`transitive_plant_containment`).

#### B. Hierarchical Multi-Agent Architecture (LangGraph Subgraphs)

• **Supervisor Router Agent** (`src/agent.py`):
  - Uses structured intent classification to route user questions to the optimal specialist sub-agent.
  - Handles greetings and direct conversational responses.
• **DuckDB Specialist Subgraph** (`src/subgraphs/duckdb_agent.py`):
  - Specialized in analytical SQL queries, aggregations (SUM, AVG, COUNT), and interactive Plotly visualization.
  - Bound tools: `query_l2l_database`, `generate_l2l_chart`.
• **TypeDB Specialist Subgraph** (`src/subgraphs/typedb_agent.py`):
  - Specialized in multi-hop causal paths, production order blast radius, and prescriptive fault triage.
  - Bound tools: `query_typedb` (with compiler-checked error self-correction).
• **Persistent State & Sessions**: Integrated with PostgreSQL via `PostgresSaver` (`l2l_chat_memory` database).

#### C. Hypermedia Frontend (FastAPI + HTMX + Tailwind + Plotly)

• Reactive SPA-like interactions without Node.js or React build dependencies.
• Multi-thread sidebar navigation with automatic semantic naming.
• Dynamic on-the-fly Plotly chart rendering.

#### D. Model Provider Flexibility

• Configured via `.env` to switch between OpenAI (`gpt-4o`) and Google GenAI (`gemini-1.5-pro`).

#### E. Model Context Protocol (MCP)

• `src/mcp_server.py`: Exposes both DuckDB SQL and TypeDB Knowledge Graph query tools to external MCP clients (Claude Desktop, IDE agents).

──────                                                                                       
### 3. Current Project Layout                                                                

```text
C:\AI_dev\l2l-analytics-chatbot\
├── main.py                               # FastAPI routes & HTMX handlers
├── docker-compose.yml                    # Multi-container orchestration (App + Postgres + TypeDB)
├── Dockerfile                            # App container definition
├── requirements.txt                      # Project dependencies
├── typedb/
│   └── schema.tql                        # TypeDB PER schema & inference rules
├── src/
│   ├── agent.py                          # Multi-Agent Supervisor Graph (LangGraph)
│   ├── llm.py                            # Centralized LLM factory (OpenAI / Gemini)
│   ├── tools.py                          # DuckDB & TypeDB execution tools
│   ├── typedb_sync.py                    # DuckDB -> TypeDB sync ETL
│   ├── cache_pyarrow.py                  # PyArrow streaming BigQuery -> DuckDB sync
│   ├── mcp_server.py                     # FastMCP server
│   ├── subgraphs/
│   │   ├── duckdb_agent.py               # DuckDB OLAP Specialist Subgraph
│   │   └── typedb_agent.py               # TypeDB KG Specialist Subgraph
│   ├── prompts/
│   │   ├── supervisor_prompt.py          # Supervisor routing prompt
│   │   ├── duckdb_prompt.py              # DuckDB system prompt
│   │   └── typedb_prompt.py              # TypeDB system prompt
│   └── utils/helpers.py                  # Thread generation & history turn parser
└── templates/                            # HTMX + Tailwind Jinja2 templates
```
