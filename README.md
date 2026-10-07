### 1. Executive Summary                                                                     
                                                                                               
  The project is a production-ready, full-stack Manufacturing Analytics Assistant tailored for 
  Leading2Lean (L2L) dispatch and maintenance data. It enables factory managers and engineers  
  to query maintenance dispatches, downtime, and operational metrics using natural language,   
  returning both formatted tabular data and dynamic interactive charts.                        
  ──────                                                                                       
  ### 2. Key Achievements & Implemented Capabilities                                           
                                                                                               
  #### A. Two-Tier Data Architecture (BigQuery → DuckDB)                                       
                                                                                               
  • High-Performance Local OLAP: Implemented in cache.py, sync_bigquery_to_duckdb synchronizes 
  upstream cloud data (cons_kamos_l2l.f_l2l_dispatches in Google BigQuery) into a local        
  embedded DuckDB cache (data/l2l_analytics.duckdb).                                           
  • Cost & Speed Optimization: Prevents slow queries and expensive BigQuery charges by serving 
  agent SQL queries locally.                                                                   
  • Safe Execution: run_duckdb_safely connects in read-only mode and enforces a 10-second      
  timeout and 2GB memory cap.                                                                  
                                                                                               
  #### B. LangGraph ReAct Agent & Multi-Turn Memory                                            
                                                                                               
  • ReAct Graph Engine: Set up in agent.py with dynamic prompt injection                       
  (get_agent_system_prompt) that embeds schema knowledge, temporal context, and site mappings  
  (e.g., Site 240 → Stargard, Site 260 → Shanghai, Site 276 → Ottawa).                         
  • Persistent State & Sessions: Integrated with PostgreSQL via PostgresSaver (l2l_chat_memory 
  database), allowing conversation sessions to persist across restarts and reloads.            
  • Tools Implemented (tools.py):                                                              
      • query_l2l_database: Executes analytical SQL and renders Markdown tables.               
      • generate_l2l_chart: Directly compiles SQL results into responsive Plotly bar, line, pie,
      or scatter charts.                                                                       
                                                                                               
                                                                                               
  #### C. Hypermedia Frontend (FastAPI + HTMX + Tailwind + Plotly)                             
                                                                                               
  • No Node.js/React Build Dependency: Utilizes FastAPI server-side rendering with Jinja2 and  
  HTMX for reactive SPA-like interactions without frontend build tooling.                      
  • Interactive Chat UI:                                                                       
      • base.html: Dark-themed layout using Tailwind CSS CDN and Plotly.js.                    
      • chat_area.html: Message container and submission form.                                 
      • sidebar.html: Multi-thread navigation list with automated semantic naming (DDMonYY-    
      HH:MM:SS-<Slug>).                                                                        
      • chat_response_partial.html: HTMX response partial that swaps in bot answers, renders   
      Plotly charts on the fly, and uses Out-Of-Band (OOB) swaps to update active thread titles
      and refresh the sidebar.                                                                 
  • Session History Replay: src/utils/helpers.py:extract_history_turns parses stored           
  checkpointer turns so past threads reload with all interactive charts fully rendered.        
                                                                                               
  #### D. Model Provider Flexibility                                                           
                                                                                               
  • Configured via .env to switch seamlessly between OpenAI (gpt-4o) and Google GenAI (gemini- 
  1.5-pro).                                                                                    
                                                                                               
  #### E. External Protocol Support (Model Context Protocol)                                   
                                                                                               
  • mcp_server.py: Built with FastMCP to expose the DuckDB query tools over standard MCP,      
  enabling external MCP-compatible AI clients (Claude Desktop, IDE agents) to query the        
  manufacturing dataset.                                                                       
                                                                                               
  #### F. Guardrails & Containerized Infrastructure                                            
                                                                                               
  • Security & Rails: config.yml configures NeMo Guardrails to guard against prompt injection  
  and jailbreaks.                                                                              
  • Container Orchestration:                                                                   
      • Dockerfile: Python 3.11-slim container.                                                
      • docker-compose.yml: Coordinates the web application, DuckDB data volume, GCP           
      authentication credentials, and PostgreSQL 16 Alpine service.                            
                                                                                               
  ──────                                                                                       
  ### 3. Current Project Layout                                                                
                                                                                               
    C:\AI_dev\l2l-analytics-chatbot\                                                           
    ├── main.py                               # FastAPI routes & HTMX handlers                 
    ├── docker-compose.yml                    # Multi-container orchestration (App + Postgres  
  16)                                                                                          
    ├── Dockerfile                            # App container definition                       
    ├── requirements.txt                      # Project dependencies                           
    ├── config/config.yml                     # NeMo Guardrails configuration                  
    ├── data/l2l_analytics.duckdb             # Local OLAP DuckDB database cache               
    ├── src/                                                                                   
    │   ├── agent.py                          # LangGraph ReAct agent & PostgresSaver          
    │   ├── cache.py                          # BigQuery -> DuckDB sync & safe executor        
    │   ├── tools.py                          # DuckDB query & Plotly chart tools              
    │   ├── mcp_server.py                     # FastMCP server for external clients            
    │   ├── prompts/agent_prompt.py           # Dynamic system prompt & schema guidance        
    │   └── utils/helpers.py                  # Thread generation & history turn parser        
    └── templates/                            # HTMX + Tailwind Jinja2 templates               
