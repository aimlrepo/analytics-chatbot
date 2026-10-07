import re
from datetime import datetime

import os
import psycopg
from psycopg.rows import dict_row

# Use PostgreSQL connection string matching agent.py and docker-compose
DB_URI = os.getenv("POSTGRES_URL", os.getenv("DATABASE_URL", "postgresql://postgres:postgrespassword@localhost:5432/l2l_chat_memory"))

def generate_thread_name(first_user_message: str = "") -> str:
    """
    Generates a timestamped thread title in the format: DDMonYY-HH:MM:SS-Summary
    Example: 26Sep26-13:33:00-Site-240-Dispatches
    """
    # 1. Date and Time prefix: DDMonYY-HH:MM:SS (e.g., 26Sep26-13:33:00)
    now = datetime.now()
    timestamp_prefix = now.strftime("%d%b%y-%H:%M:%S")
    
    # 2. Derive a short summary slug from the first prompt
    if first_user_message:
        # Strip non-alphanumeric characters except spaces
        clean_text = re.sub(r'[^\w\s]', '', first_user_message).strip()
        words = clean_text.split()[:3]
        summary_slug = "-".join([w.capitalize() for w in words])
    else:
        summary_slug = "NewChat"

    return f"{timestamp_prefix}-{summary_slug}"

def get_all_threads():
    """
    Fetches unique session thread IDs from PostgreSQL checkpoints table,
    excluding legacy test entries (None, session-1, and empty strings).
    Groups by thread_id and orders by latest checkpoint to display the most recently active sessions.
    """
    query = """
        SELECT thread_id, MAX(checkpoint_id) as latest_cp
        FROM checkpoints 
        WHERE thread_id IS NOT NULL 
          AND thread_id NOT IN ('None', 'session-1', '')
        GROUP BY thread_id 
        ORDER BY latest_cp DESC 
        LIMIT 20;
    """
    try:
        with psycopg.connect(DB_URI, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                threads = cur.fetchall()
                return threads
    except Exception as e:
        print(f"Error fetching threads from DB: {e}")
        return []

def extract_history_turns(messages):
    """
    Parses LangGraph / LangChain messages into sequential user-bot conversation turns,
    associating any tool-generated Plotly JSON with the corresponding turn.
    """
    turns = []
    current_turn = None
    
    for msg in messages:
        msg_type = getattr(msg, "type", None) or getattr(msg, "role", None)
        if msg_type == "system":
            continue
            
        if msg_type == "human":
            if current_turn:
                if current_turn.get("plotly_json") and (
                    "Plotly JSON string" in current_turn["bot_response"] 
                    or "Jupyter notebook" in current_turn["bot_response"]
                ):
                    current_turn["bot_response"] = "Here is the requested chart:"
                turns.append(current_turn)
            current_turn = {
                "user_message": msg.content,
                "bot_response": "",
                "plotly_json": None
            }
        elif msg_type == "tool":
            raw_content = str(msg.content)
            clean_json = re.sub(
                r"^```(?:plotly_json|json)?\s*|\s*```$", 
                "", 
                raw_content.strip(), 
                flags=re.MULTILINE
            )
            if '"data"' in clean_json and '"layout"' in clean_json:
                if current_turn is not None:
                    current_turn["plotly_json"] = clean_json
        elif msg_type == "ai":
            if current_turn is not None and msg.content:
                current_turn["bot_response"] = msg.content

    if current_turn:
        if current_turn.get("plotly_json") and (
            "Plotly JSON string" in current_turn["bot_response"] 
            or "Jupyter notebook" in current_turn["bot_response"]
        ):
            current_turn["bot_response"] = "Here is the requested chart:"
        turns.append(current_turn)

    return turns