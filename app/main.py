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

# --- Configuration & In-memory Caches ---
CACHE_DB_PATH = "/app/data/cache.db"
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
    """
    Handles application startup and shutdown events. This function runs only once.
    """
    print("Application startup...")
    global db_pool, ollama_client, DB_SCHEMA_CACHE, DB_HINTS_CACHE, DB_SCHEMA_HASH
    
    # 1. Initialize PostgreSQL Connection Pool
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

    # 2. Initialize Ollama Client
    ollama_client = AsyncClient(host=os.getenv("OLLAMA_HOST", "http://ollama:11434"))
    print("Ollama async client initialized.")
    
    # 3. Initialize Cache and Log Database
    await setup_databases()
    print("Cache database initialized.")
    
    # 4. Pre-load DB Schema and Value Hints
    DB_SCHEMA_CACHE, DB_HINTS_CACHE, _ = await get_schema_and_hints()
    DB_SCHEMA_HASH = hashlib.sha256((DB_SCHEMA_CACHE + DB_HINTS_CACHE).encode()).hexdigest()
    print("Database schema and value hints pre-loaded and hashed.")
    
    print("Application startup complete.")
    yield
    
    # --- On Shutdown ---
    print("Application shutdown...")
    if db_pool:
        await db_pool.close()
        print("Database connection pool closed.")

# --- FastAPI App Initialization ---
app = FastAPI(
    title="AISavvy API v5",
    description="A feature-rich API for Conversational SQL with relevance checking and contextual explanations.",
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
        await db.execute("INSERT OR REPLACE INTO llm_cache (key, response) VALUES (?, ?)", (key, json.dumps(response, default=json_default_encoder)))
        await db.commit()

async def log_query(question, sql, success, error=""):
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        await db.execute("INSERT INTO query_log (question, sql_query, success, error_message) VALUES (?, ?, ?, ?)", (question, sql, success, error))
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
def generate_sql_prompt(schema, hints, history):
    conversation_log = "\n".join([f"User: {turn['content']}" if turn['role'] == 'user' else f"Assistant (Result): {json.dumps(turn['content']['result'], default=json_default_encoder)}" for turn in history[:-1] if isinstance(turn.get('content'), dict) and 'result' in turn['content'] or turn['role'] == 'user'])
    last_question = history[-1]['content']
    
    return f"""You are a world-class PostgreSQL query writer AI.
### RULES:
1. If the user's question is ambiguous, respond ONLY with `CLARIFY: <your clarifying question>`.
2. If asked for a "total", "count", "average", etc., you MUST use the appropriate SQL aggregate function.
3. For filtering, strictly use the values provided in the HINTS section when possible (e.g., use 'Engineering', not 'Engineering Department').
4. Your output MUST BE ONLY the SQL query or a `CLARIFY:` question.
### SCHEMA:
{schema}
### HINTS ON COLUMN VALUES:
{hints if hints else "No hints available."}
### EXAMPLES:
User: "Show departments with more than 2 employees"
SQL: SELECT d.department_name FROM employees e JOIN departments d ON e.department_id = d.department_id GROUP BY d.department_name HAVING COUNT(e.employee_id) > 2;
### HISTORY:
{conversation_log if conversation_log else "No previous conversation."}
### FINAL QUESTION:
{last_question}
### RESPONSE:
"""

def generate_relevance_prompt(schema, question):
    return f"Is the following question related to querying a database with the schema provided? Schema: {schema}\nUser's Question: {question}\nAnswer ONLY with 'YES' or 'NO'."

def generate_no_results_prompt(question, sql_query):
    return f"The user asked: '{question}'. The query `{sql_query}` ran successfully but returned no rows. In one friendly sentence, explain why there were no results. Example: 'It appears there are no employees that match your criteria in the Marketing department.' Respond ONLY with the single explanatory sentence."

# --- API Endpoints ---
@app.get("/", tags=["Health Check"])
async def read_root():
    return {"status": "healthy", "message": "Welcome to the AISavvy API"}

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
        # Auto-fix logic can be triggered here if needed
        raise HTTPException(status_code=400, detail={"error": error_message})

    # 5. Handle Empty Results
    if not results:
        no_results_prompt = generate_no_results_prompt(last_question, sql_query)
        try:
            no_results_response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': no_results_prompt}])
            return {"no_results_explanation": no_results_response['message']['content'].strip()}
        except Exception:
            return {"no_results_explanation": "The query executed successfully but returned no data."}
    
    # 6. Generate Explanation & DataViz Spec (Simplified for now)
    explanation = "An explanation for this query."
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
