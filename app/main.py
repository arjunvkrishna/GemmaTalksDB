import os
import re
import json
import hashlib
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Union
from decimal import Decimal

import asyncpg
import aiosqlite
from ollama import AsyncClient
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --- Configuration ---
CACHE_DB_PATH = "/app/data/cache.db"
DB_SCHEMA_CACHE = ""
DB_SCHEMA_HASH = ""
db_pool = None
ollama_client = None

# --- Custom JSON Encoder for Decimal Types ---
def json_default_encoder(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

# --- FastAPI Lifespan Manager for Startup/Shutdown Events ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup and shutdown events."""
    print("Application startup...")
    global db_pool, ollama_client, DB_SCHEMA_CACHE, DB_SCHEMA_HASH
    
    # 1. Initialize DB Connection Pool
    try:
        db_pool = await asyncpg.create_pool(
            user=os.getenv("POSTGRES_USER", "postgres"), password=os.getenv("POSTGRES_PASSWORD", "my_password"),
            database=os.getenv("POSTGRES_DB", "mydb"), host=os.getenv("DB_HOST", "db"),
        )
        print("Database connection pool created.")
    except Exception as e:
        print(f"FATAL: Could not connect to PostgreSQL: {e}")
        raise

    # 2. Initialize Ollama Client
    ollama_client = AsyncClient(host=os.getenv("OLLAMA_HOST", "http://ollama:11434"))
    print("Ollama async client initialized.")
    
    # 3. Initialize Cache DB
    await setup_databases()
    print("Cache database initialized.")
    
    # 4. Pre-load DB Schema
    DB_SCHEMA_CACHE, _ = await get_db_schema_and_erd()
    DB_SCHEMA_HASH = hashlib.sha256(DB_SCHEMA_CACHE.encode()).hexdigest()
    print("Database schema pre-loaded and hashed.")
    
    print("Application startup complete.")
    yield
    
    print("Application shutdown...")
    if db_pool:
        await db_pool.close()
        print("Database connection pool closed.")

# --- FastAPI App Initialization ---
app = FastAPI(
    title="AISavvy API",
    description="A feature-rich API for conversational SQL with advanced features.",
    lifespan=lifespan
)

# --- Pydantic Models ---
class Turn(BaseModel):
    role: str
    content: Union[str, Dict[str, Any]]

class QueryRequest(BaseModel):
    history: List[Turn]

# --- Helper Functions ---
async def setup_databases():
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, response TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS query_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                sql_query TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def get_from_cache(key: str):
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        async with db.execute("SELECT response FROM llm_cache WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else None

async def set_to_cache(key: str, response: dict):
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO llm_cache (key, response) VALUES (?, ?)",
            (key, json.dumps(response, default=json_default_encoder)),
        )
        await db.commit()

async def log_query(question, sql, success, error=""):
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        await db.execute(
            "INSERT INTO query_log (question, sql_query, success, error_message) VALUES (?, ?, ?, ?)",
            (question, sql, success, error)
        )
        await db.commit()

async def get_db_schema_and_erd():
    async with db_pool.acquire() as conn:
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")
        schema_parts, dot_parts = [], ["digraph ERD {", "graph [rankdir=LR, layout=neato, splines=polyline];", "node [shape=box, style=rounded];", "edge [arrowhead=none];"]
        for table in tables:
            table_name = table['table_name']
            columns = await conn.fetch(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position;")
            column_names = ", ".join([col['column_name'] for col in columns])
            schema_parts.append(f"{table_name}({column_names})")
            dot_parts.append(f'"{table_name}";')
        return "\n".join(schema_parts), "\n".join(dot_parts) + "\n}"

def generate_prompt(schema, history):
    conversation_log = ""
    for turn in history[:-1]:
        if turn.role == 'user':
            conversation_log += f"User: {turn.content}\n"
        elif turn.role == 'assistant' and isinstance(turn.content, dict) and 'result' in turn.content:
            result_str = json.dumps(turn.content['result'], default=json_default_encoder)
            conversation_log += f"Assistant (Result): {result_str}\n"

    last_question = history[-1].content
    prompt = f"""You are a world-class PostgreSQL query writer AI. Your task is to write a single, valid PostgreSQL query to answer the user's final question.

### IMMUTABLE RULES:
1.  If the user's question is ambiguous, respond ONLY with a clarifying question prefixed with `CLARIFY:`.
2.  If the user asks for a "total", "count", "average", etc., you MUST use the appropriate SQL aggregate function (`SUM`, `COUNT`, `AVG`).
3.  Your output **MUST BE ONLY THE SQL QUERY** or a `CLARIFY:` question.

### COMPRESSED DATABASE SCHEMA:
{schema}

### QUERY EXAMPLES:
User Question: "Show departments that have more than 2 employees"
Correct SQL: SELECT d.department_name FROM employees e JOIN departments d ON e.department_id = d.department_id GROUP BY d.department_name HAVING COUNT(e.employee_id) > 2;

### CONVERSATION HISTORY:
{conversation_log if conversation_log else "No previous conversation."}

### FINAL USER QUESTION:
{last_question}

### RESPONSE (SQL Query or CLARIFY: question):
"""
    return prompt.strip()

# --- API Endpoints ---
@app.get("/", tags=["Health Check"])
async def read_root():
    return {"status": "healthy", "message": "Welcome to the AISavvy API"}

@app.post("/query", tags=["Core Logic"])
async def process_query(request: QueryRequest):
    last_question = request.history[-1].content
    history_str = json.dumps([turn.dict() for turn in request.history], default=json_default_encoder)
    cache_key_hash = hashlib.sha256((history_str + DB_SCHEMA_HASH).encode()).hexdigest()

    cached_response = await get_from_cache(cache_key_hash)
    if cached_response:
        return cached_response

    prompt = generate_prompt(DB_SCHEMA_CACHE, request.history)
    try:
        llm_response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': prompt}])
        response_text = llm_response['message']['content'].strip()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {e}")

    if response_text.upper().startswith("CLARIFY:"):
        return {"clarification": response_text[len("CLARIFY:"):].strip()}

    sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", response_text, re.DOTALL)
    sql_query = (sql_match.group(1).strip() if sql_match else response_text).rstrip(';')
    
    explanation = "Could not generate explanation."
    try:
        explain_prompt = f"In one simple, plain English sentence, explain what this SQL query does: `{sql_query}`"
        explain_response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': explain_prompt}])
        explanation = explain_response['message']['content'].strip()
    except Exception:
        pass

    try:
        async with db_pool.acquire() as conn:
            stmt = await conn.prepare(sql_query)
            records = await stmt.fetch()
            results = [dict(record) for record in records]
        await log_query(last_question, sql_query, True)
    except asyncpg.PostgresError as e:
        error_message = str(e)
        await log_query(last_question, sql_query, False, error_message)
        suggested_fix = "Could not generate a fix."
        try:
            fix_prompt = f"The following SQL query failed: `{sql_query}`. The database error was: `{error_message}`. Based on the user's question: `{last_question}` and the schema: `{DB_SCHEMA_CACHE}`, provide a corrected SQL query. Respond with ONLY the corrected SQL query."
            fix_response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': fix_prompt}])
            suggested_fix = fix_response['message']['content'].strip()
        except Exception:
            pass
        raise HTTPException(status_code=400, detail={"error": error_message, "suggested_fix": suggested_fix})

    chart_spec = None
    if results:
        try:
            viz_prompt = f"Given the user's question: '{last_question}' and these resulting data columns: {list(results[0].keys())}. Should this be visualized? If yes, suggest a chart type (bar, line, or pie) and columns for x/y axes. Respond ONLY with a single, valid JSON object like {{\"chart_needed\": true, \"chart_type\": \"bar\", \"x_column\": \"name\", \"y_column\": \"salary\"}} or {{\"chart_needed\": false}}."
            viz_response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': viz_prompt}])
            chart_spec = json.loads(viz_response['message']['content'].strip())
        except Exception:
            chart_spec = {"chart_needed": False}
    
    final_response = {"question": last_question, "sql_query": sql_query, "explanation": explanation, "result": results, "chart_spec": chart_spec}
    await set_to_cache(cache_key_hash, final_response)
    return final_response

@app.get("/history", tags=["UI Features"])
async def get_history():
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM query_log ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

@app.get("/schema/erd", tags=["UI Features"])
async def get_schema_erd():
    _, erd_dot_string = await get_db_schema_and_erd()
    return {"dot_string": erd_dot_string}