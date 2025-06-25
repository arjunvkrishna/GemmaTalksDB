import os
import re
import json
import hashlib
from contextlib import asynccontextmanager
from typing import List, Optional

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

# --- NEW: Lifespan Manager for Startup/Shutdown Events ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application startup...")
    global db_pool, ollama_client, DB_SCHEMA_CACHE, DB_SCHEMA_HASH
    try:
        db_pool = await asyncpg.create_pool(
            user=os.getenv("POSTGRES_USER", "postgres"), password=os.getenv("POSTGRES_PASSWORD", "my_password"),
            database=os.getenv("POSTGRES_DB", "mydb"), host=os.getenv("DB_HOST", "db"),
        )
        print("Database connection pool created.")
    except Exception as e:
        print(f"FATAL: Could not connect to PostgreSQL: {e}")
        raise
    
    ollama_client = AsyncClient(host=os.getenv("OLLAMA_HOST", "http://ollama:11434"))
    DB_SCHEMA_CACHE, _ = await get_db_schema_and_erd()
    DB_SCHEMA_HASH = hashlib.sha256(DB_SCHEMA_CACHE.encode()).hexdigest()
    await setup_databases()
    print("Startup complete.")
    yield
    print("Application shutdown...")
    if db_pool:
        await db_pool.close()
        print("Database connection pool closed.")
app = FastAPI(
    title="AISavvy API",
    description="A feature-rich API for conversational SQL with caching, history, and visualization.",
    lifespan=lifespan
)

# --- Pydantic Models ---
class Turn(BaseModel):
    role: str
    content: str

class QueryRequest(BaseModel):
    history: List[Turn]

# --- Database and Cache Setup ---
async def setup_databases():
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, response TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        # NEW: Table for query history
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

# --- Caching Functions (Unchanged) ---
async def get_from_cache(key: str):
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        async with db.execute("SELECT response FROM llm_cache WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else None

async def set_to_cache(key: str, response: dict):
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO llm_cache (key, response) VALUES (?, ?)", (key, json.dumps(response)))
        await db.commit()

# --- NEW: Query Logging Function ---
async def log_query(question, sql, success, error=""):
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        await db.execute(
            "INSERT INTO query_log (question, sql_query, success, error_message) VALUES (?, ?, ?, ?)",
            (question, sql, success, error)
        )
        await db.commit()

# --- Schema and Prompt Functions ---
async def get_db_schema_and_erd():
    async with db_pool.acquire() as conn:
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")
        schema_parts = []
        dot_parts = ["digraph ERD {", "graph [rankdir=LR, layout=neato];", "node [shape=box];"]
        for table in tables:
            table_name = table['table_name']
            dot_parts.append(f'"{table_name}";')
            columns = await conn.fetch(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position")
            column_names = ", ".join([col['column_name'] for col in columns])
            schema_parts.append(f"{table_name}({column_names})")
        return "\n".join(schema_parts), "\n".join(dot_parts) + "\n}"

def generate_prompt(schema, history, question_override=None):
    # This function is now more generic for different tasks
    # ... (The "golden prompt" from the previous step is still excellent here)
    conversation_log = "\n".join(f"{turn.role}: {turn.content}" for turn in history[:-1])
    last_question = question_override or history[-1].content
    
    prompt = f"""You are a world-class PostgreSQL query writer AI. Your task is to write a single, valid PostgreSQL query to answer the user's final question.

### IMMUTABLE RULES:
1.  **YOU MUST ONLY USE TABLES AND COLUMNS FROM THE COMPRESSED SCHEMA PROVIDED BELOW.**
2.  The schema is represented as `table_name(column1, column2)`.
3.  Analyze the `Conversation History` to resolve references (like "his", "her", "that").
4.  Your output **MUST BE ONLY THE SQL QUERY**. No explanations or markdown.

### COMPRESSED DATABASE SCHEMA:
{schema}

### CONVERSATION HISTORY:
{conversation_log if conversation_log else "No previous conversation."}

### FINAL USER QUESTION (Your Task):
{last_question}

### SQL QUERY:
"""
    return prompt.strip()

# --- Main API Endpoint ---
@app.post("/query")
async def process_query(request: QueryRequest):
    last_question = request.history[-1].content
    cache_key_hash = hashlib.sha256((json.dumps([t.dict() for t in request.history]) + DB_SCHEMA_HASH).encode()).hexdigest()

    cached_response = await get_from_cache(cache_key_hash)
    if cached_response:
        return cached_response

    prompt = generate_prompt(DB_SCHEMA_CACHE, request.history)
    try:
        llm_response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': prompt}])
        raw_sql = llm_response['message']['content'].strip()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {e}")

    sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", raw_sql, re.DOTALL)
    sql_query = (sql_match.group(1).strip() if sql_match else raw_sql).rstrip(';')
    
    # --- SQL Auto-Fix and Execution Logic ---
    try:
        async with db_pool.acquire() as conn:
            stmt = await conn.prepare(sql_query)
            records = await stmt.fetch()
            results = [dict(record) for record in records]
        await log_query(last_question, sql_query, True)
        success = True
        suggested_fix = ""
    except asyncpg.PostgresError as e:
        success = False
        error_message = str(e)
        await log_query(last_question, sql_query, False, error_message)
        
        # --- NEW: SQL Auto-Fix Assistant ---
        fix_prompt = f"The following SQL query failed: `{sql_query}`. The database returned this error: `{error_message}`. Based on the user's question: `{last_question}` and the schema: `{DB_SCHEMA_CACHE}`, please provide a corrected SQL query. Respond with ONLY the corrected SQL query."
        try:
            fix_response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': fix_prompt}])
            suggested_fix = fix_response['message']['content'].strip()
        except Exception:
            suggested_fix = "Could not generate a fix."
        raise HTTPException(status_code=400, detail={"error": error_message, "suggested_fix": suggested_fix})

    # --- NEW: DataViz Intent Detection ---
    chart_spec = None
    if success and results:
        viz_prompt = f"Given the user's question: '{last_question}' and these resulting data columns: {list(results[0].keys())}. Should this result be visualized with a chart? If yes, what is the best chart type (bar, line, or pie) and which columns should be on the x and y axes? Respond ONLY with a single, valid JSON object like {{\"chart_needed\": true, \"chart_type\": \"bar\", \"x_column\": \"column_name\", \"y_column\": \"column_name\"}} or {{\"chart_needed\": false}}."
        try:
            viz_response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': viz_prompt}])
            chart_spec = json.loads(viz_response['message']['content'].strip())
        except Exception:
            chart_spec = {"chart_needed": False}
    
    final_response = {"question": last_question, "sql_query": sql_query, "result": results, "chart_spec": chart_spec}
    await set_to_cache(cache_key_hash, final_response)
    return final_response

# --- NEW: Endpoints for UI Features ---
@app.get("/history")
async def get_history():
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM query_log ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

@app.get("/schema/erd")
async def get_schema_erd():
    _, erd_dot_string = await get_db_schema_and_erd()
    return {"dot_string": erd_dot_string}