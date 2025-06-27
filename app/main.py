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

# --- In-memory caches for startup data ---
DB_SCHEMA_CACHE = ""
DB_HINTS_CACHE = ""
DB_SCHEMA_HASH = ""
db_pool = None
ollama_client = None

# --- Custom JSON Encoder to Handle Database Decimal Types ---
def json_default_encoder(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

# --- FastAPI Lifespan Manager for Startup/Shutdown Events ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application startup...")
    global db_pool, ollama_client, DB_SCHEMA_CACHE, DB_HINTS_CACHE, DB_SCHEMA_HASH
    try:
        db_pool = await asyncpg.create_pool(
            user=os.getenv("POSTGRES_USER_APP", "aisavvy"),
            password=os.getenv("POSTGRES_PASSWORD_APP", "my_password"),
            database=os.getenv("POSTGRES_DB", "mydb"),
            host=os.getenv("DB_HOST", "db"),
        )
        print("Database connection pool created.")
    except Exception as e:
        print(f"FATAL: Could not connect to PostgreSQL: {e}")
        raise
    
    ollama_client = AsyncClient(host=os.getenv("OLLAMA_HOST", "http://ollama:11434"))
    await setup_databases()
    print("Cache database initialized.")
    
    DB_SCHEMA_CACHE, DB_HINTS_CACHE, _ = await get_schema_and_hints()
    DB_SCHEMA_HASH = hashlib.sha256((DB_SCHEMA_CACHE + DB_HINTS_CACHE).encode()).hexdigest()
    print("Database schema and value hints pre-loaded and hashed.")
    
    print("Application startup complete.")
    yield
    
    print("Application shutdown...")
    if db_pool:
        await db_pool.close()
        print("Database connection pool closed.")

app = FastAPI(
    title="AISavvy API v5",
    description="API for Conversational SQL with relevance and context handling.",
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
        await db.execute("CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, response TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS query_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT,
                sql_query TEXT,
                success BOOLEAN,
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

async def get_schema_and_hints():
    async with db_pool.acquire() as conn:
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")
        schema_parts, dot_parts, hint_parts = [], ["digraph ERD {", "graph [rankdir=LR];", "node [shape=plaintext];"], []
        
        for table in tables:
            table_name = table['table_name']
            columns_records = await conn.fetch(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position;")
            column_names = [col['column_name'] for col in columns_records]
            schema_parts.append(f"{table_name}({', '.join(column_names)})")

        dept_names = await conn.fetch("SELECT DISTINCT department_name FROM departments ORDER BY department_name LIMIT 10")
        if dept_names:
            values = [row['department_name'] for row in dept_names]
            hint_parts.append(f"- The 'department_name' column can have values like: {values}")

        return "\n".join(schema_parts), "\n".join(hint_parts), "\n".join(dot_parts) + "\n}"

# --- Prompt Generation Functions ---
def generate_sql_prompt(schema, hints, history: List[Turn]):
    # --- FIXED: The list comprehension now correctly handles Pydantic objects ---
    conversation_log = "\n".join([
        f"User: {turn.content}" if turn.role == 'user'
        else f"Assistant (Result): {json.dumps(turn.content['result'], default=json_default_encoder)}"
        for turn in history[:-1]
        if turn.role == 'user' or (isinstance(turn.content, dict) and 'result' in turn.content)
    ])
    
    last_question = history[-1].content
    
    return f"""You are a world-class PostgreSQL query writer AI.

### RULES:
1. If the user's question is ambiguous, respond ONLY with `CLARIFY: <your clarifying question>`.
2. If asked for a "total", "count", "average", etc., you MUST use the appropriate SQL aggregate function (`SUM`, `COUNT`, `AVG`).
3. For filtering, strictly use the values in HINTS when possible (e.g., use 'Engineering', not 'Engineering Department').
4. Your output MUST BE ONLY the SQL query or a `CLARIFY:` question.

### COMPRESSED DATABASE SCHEMA:
{schema}

### HINTS ON COLUMN VALUES:
{hints if hints else "No hints available."}

### QUERY EXAMPLES:
User: "Show departments that have more than 2 employees"
SQL: SELECT d.department_name FROM employees e JOIN departments d ON e.department_id = d.department_id GROUP BY d.department_name HAVING COUNT(e.employee_id) > 2;

### HISTORY:
{conversation_log if conversation_log else "No previous conversation."}

### FINAL QUESTION:
{last_question}

### RESPONSE:
"""

def generate_relevance_prompt(schema, question):
    return f"Is the following question related to querying a database with this schema? Schema: {schema}\nUser's Question: {question}\nAnswer ONLY with 'YES' or 'NO'."

def generate_no_results_prompt(question, sql_query):
    return f"The user asked: '{question}'. The query `{sql_query}` ran successfully but returned no rows. In one friendly sentence, explain why there were no results. Example: 'It appears there are no employees that match your criteria.' Respond ONLY with the sentence."

# --- API Endpoints ---
@app.get("/", tags=["Health Check"])
async def read_root():
    return {"status": "healthy"}

@app.post("/query", tags=["Core Logic"])
async def process_query(request: QueryRequest):
    last_question = request.history[-1].content
    if not isinstance(last_question, str):
        raise HTTPException(status_code=400, detail="Invalid question format.")

    # 1. Relevance Check
    relevance_prompt = generate_relevance_prompt(DB_SCHEMA_CACHE, last_question)
    try:
        relevance_response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': relevance_prompt}])
        if 'NO' in relevance_response['message']['content'].strip().upper():
            return {"off_topic": "That question does not seem to be about the database. Please ask a question related to employees or departments."}
    except Exception as e:
        print(f"Relevance check failed: {e}")

    # 2. Cache Check
    history_str = json.dumps([turn.dict() for turn in request.history], default=json_default_encoder)
    cache_key_hash = hashlib.sha256((history_str + DB_SCHEMA_HASH).encode()).hexdigest()
    cached_response = await get_from_cache(cache_key_hash)
    if cached_response:
        return cached_response

    # 3. Generate SQL or Clarification
    sql_prompt = generate_sql_prompt(DB_SCHEMA_CACHE, DB_HINTS_CACHE, request.history)
    try:
        llm_response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': sql_prompt}])
        response_text = llm_response['message']['content'].strip()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {e}")

    if response_text.upper().startswith("CLARIFY:"):
        return {"clarification": response_text[len("CLARIFY:"):].strip()}

    sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", response_text, re.DOTALL)
    sql_query = (sql_match.group(1).strip() if sql_match else response_text).rstrip(';')
    
    # 4. Execute Query
    results = []
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

    # 5. Handle Empty Results
    if not results:
        no_results_prompt = generate_no_results_prompt(last_question, sql_query)
        try:
            no_results_response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': no_results_prompt}])
            return {"no_results_explanation": no_results_response['message']['content'].strip()}
        except Exception:
            return {"no_results_explanation": "The query executed successfully but returned no data."}
    
    # 6. Generate Explanation & DataViz Spec
    explanation, chart_spec = "Could not generate explanation.", {"chart_needed": False}
    try:
        explain_prompt = f"In one simple, plain English sentence, explain what this SQL query does: `{sql_query}`"
        explain_response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': explain_prompt}])
        explanation = explain_response['message']['content'].strip()
    except Exception:
        pass

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
    _, _, erd_dot_string = await get_schema_and_hints()
    return {"dot_string": erd_dot_string}
