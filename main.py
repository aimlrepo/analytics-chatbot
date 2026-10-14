import os
import uuid
import logging
import re
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Import helper functions from dedicated utils module
from src.utils.helpers import generate_thread_name, get_all_threads, extract_history_turns

# 1. Configure global root logging settings
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Set specific third-party library log levels if needed
logging.getLogger("nemoguardrails").setLevel(logging.DEBUG)

# 2. Instantiate local module logger for main.py
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request, Form, HTTPException, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from langchain_core.messages import HumanMessage

from src.agent import agent_app, POSTGRES_URL
from src.cache_pyarrow import sync_bigquery_to_duckdb

app = FastAPI(title="L2L Analytics Chatbot")

# Setup templates and static directories
templates = Jinja2Templates(directory="templates")
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

#added by Manish to test Plotly CDN
import pandas as pd
import plotly.express as px
@app.get("/test-chart", response_class=HTMLResponse)
async def test_chart():
    # 1. Create test dataframe and Plotly figure
    df = pd.DataFrame({
        "Category": ["A", "B", "C", "D"],
        "Values": [10, 25, 15, 30]
    })
    fig = px.bar(df, x="Category", y="Values", title="Sanity Check Chart")
    fig.update_layout(template="plotly_dark")
    plotly_json = fig.to_json()

    # 2. Return complete standalone HTML document with Plotly CDN in head
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Plotly Test Harness</title>
        <script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
        <script src="https://unpkg.com/htmx.org@1.9.10"></script>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-900 text-white p-8">
        <h1 class="text-xl font-bold mb-4">Stage 1: Isolated Plotly.js Test</h1>
        <div id="test-canvas" style="min-height: 400px; width: 100%;" class="bg-gray-800 rounded p-2"></div>

        <script>
            (function() {{
                const figure = {plotly_json};
                const container = document.getElementById('test-canvas');
                Plotly.newPlot(container, figure.data, figure.layout, {{ responsive: true }});
            }})();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
@app.get("/test-htmx-page", response_class=HTMLResponse)
async def test_htmx_page():
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Stage 2: HTMX Plotly Test</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://unpkg.com/htmx.org@1.9.10"></script>
        <script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
    </head>
    <body class="bg-gray-900 text-white p-8">
        <h1 class="text-xl font-bold mb-4">Stage 2: Testing HTMX Dynamic Injection</h1>
        
        <button hx-get="/test-htmx-response" 
                hx-target="#chat-messages" 
                hx-swap="beforeend"
                class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded">
            Simulate Bot Sending Chart Response
        </button>

        <div id="chat-messages" class="mt-6 space-y-4"></div>
    </body>
    </html>
    """)

@app.get("/test-htmx-response", response_class=HTMLResponse)
async def test_htmx_response():
    # Simulated chart JSON data from database
    df = pd.DataFrame({
        "dispatchtype": ["PQT fault", "Forklift Check", "PDM", "Code Yellow", "PQT Missing"],
        "count": [6237, 2666, 1691, 1369, 741]
    })
    fig = px.bar(df, x="dispatchtype", y="count", title="Top 5 Dispatch Types - Shanghai")
    fig.update_layout(template="plotly_dark", margin=dict(l=20, r=20, t=40, b=20))
    json_payload = fig.to_json()

    # Exact HTML structure as chat_response_partial.html
    return HTMLResponse(content=f"""
    <div class="bg-gray-800 border border-gray-700 text-gray-100 p-4 rounded-lg max-w-2xl shadow">
        <p class="font-bold mb-2">Bot Response:</p>
        <p>Here is the requested chart for Shanghai:</p>
        
        <div class="plotly-canvas mt-3 w-full" style="min-height: 350px;"></div>
        
        <script>
            (function() {{
                const canvases = document.querySelectorAll('.plotly-canvas');
                const latestCanvas = canvases[canvases.length - 1];
                const figure = {json_payload};
                Plotly.newPlot(latestCanvas, figure.data, figure.layout, {{ responsive: true }});
            }})();
        </script>
    </div>
    """)

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Renders the main layout shell using base.html."""
    threads = get_all_threads()
    return templates.TemplateResponse(
        "base.html",
        {
            "request": request,
            "threads": threads,
            "active_thread_id": None,
            "history": []
        }
    )


@app.post("/chat/new", response_class=HTMLResponse)
async def create_new_chat(request: Request, response: Response):
    new_thread_id = generate_thread_name()
    
    # Tell HTMX client to reload the sidebar automatically
    response.headers["HX-Trigger"] = "refreshSidebar"
    
    return templates.TemplateResponse(
        "chat_area.html",
        {
            "request": request, 
            "active_thread_id": new_thread_id,
            "history": []
        }
    )


@app.get("/chat/history/{thread_id}", response_class=HTMLResponse)
async def get_chat_history(request: Request, response: Response, thread_id: str):
    """Loads and renders the full chat history of an existing session thread."""
    history = []
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = agent_app.get_state(config)
        messages = state.values.get("messages", []) if state and hasattr(state, "values") and state.values else []
        history = extract_history_turns(messages)
    except Exception as e:
        logger.error(f"Error fetching history for thread '{thread_id}': {e}", exc_info=True)

    # Trigger sidebar refresh so the selected thread is visually active
    response.headers["HX-Trigger"] = "refreshSidebar"

    return templates.TemplateResponse(
        "chat_area.html",
        {
            "request": request,
            "active_thread_id": thread_id,
            "history": history
        }
    )


@app.post("/chat", response_class=HTMLResponse)
async def chat_endpoint(
    request: Request, 
    response: Response,
    user_input: str = Form(..., alias="message"),
    thread_id: Optional[str] = Form(None)
):
    clean_thread_id = (thread_id or "").strip()
    is_new_session = not clean_thread_id or clean_thread_id in ("None", "session-1") or clean_thread_id.endswith("-NewChat")

    if is_new_session:
        clean_thread_id = generate_thread_name(user_input)
        # First query in session established/named the thread -> trigger sidebar refresh
        response.headers["HX-Trigger"] = "refreshSidebar"

    config = {"configurable": {"thread_id": clean_thread_id}}

    bot_text = ""
    plotly_json = None

    try:
        # 1. Run the LangGraph agent workflow
        response_state = agent_app.invoke(
            {"messages": [("user", user_input)]}, 
            config=config
        )

        messages = response_state.get("messages", [])

        # 2. Capture final AI text response
        if messages and messages[-1].type == "ai":
            bot_text = messages[-1].content

        # 3. Locate the last human turn in state memory
        last_user_idx = -1
        for idx in range(len(messages) - 1, -1, -1):
            if messages[idx].type == "human":
                last_user_idx = idx
                break

        # 4. Extract ToolMessage ONLY from the current turn
        if last_user_idx != -1:
            current_turn_messages = messages[last_user_idx + 1:]
            for msg in current_turn_messages:
                if msg.type == "tool":
                    raw_content = str(msg.content)
                    
                    # Strip markdown triple backticks if present
                    clean_json = re.sub(
                        r"^```(?:plotly_json|json)?\s*|\s*```$", 
                        "", 
                        raw_content.strip(), 
                        flags=re.MULTILINE
                    )
                    
                    if '"data"' in clean_json and '"layout"' in clean_json:
                        plotly_json = clean_json
                        logger.info(f"Successfully extracted Plotly JSON for current turn (length: {len(plotly_json)})")
                        break

        # 5. Clean up redundant LLM boilerplate text when a chart is present
        if plotly_json and ("Plotly JSON string" in bot_text or "Jupyter notebook" in bot_text):
            bot_text = "Here is the requested chart:"

    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
        bot_text = f"An error occurred while processing your request: {str(e)}"

    return templates.TemplateResponse(
        "components/chat_response_partial.html",
        {
            "request": request,
            "user_message": user_input,
            "bot_response": bot_text,
            "plotly_json": plotly_json,
            "active_thread_id": clean_thread_id
        }
    )

@app.get("/sidebar", response_class=HTMLResponse)
async def get_sidebar(
    request: Request, 
    thread_id: Optional[str] = None, 
    active_thread_id: Optional[str] = None
):
    current_active_id = thread_id or active_thread_id
    threads = get_all_threads()
    return templates.TemplateResponse(
        "sidebar.html",
        {
            "request": request,
            "threads": threads,
            "active_thread_id": current_active_id
        }
    )

@app.post("/sync-cache")
async def sync_cache_endpoint():
    """Triggers cache refresh from BigQuery to local DuckDB via PyArrow streaming."""
    try:
        result = sync_bigquery_to_duckdb()
        return {
            "status": "success",
            "message": "DuckDB cache synced successfully via PyArrow.",
            "details": result
        }
    except Exception as e:
        logging.exception(f"Cache sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cache sync failed: {str(e)}")