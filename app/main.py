import os
import re
import json
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Union
from decimal import Decimal
from datetime import date, datetime

import asyncpg
import aiosqlite
from ollama import AsyncClient
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --- Configure a logger ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration & In-memory Caches ---
CACHE_DB_PATH = "/app/data/cache.db"
DB_SCHEMA_CACHE = ""
DB_HINTS_CACHE = ""
DB_SCHEMA_HASH = ""
db_pool = None
ollama_client = None

# --- Custom JSON Encoder ---
def json_default_encoder(obj):
    if isinstance(obj, Decimal): return float(obj)
    if isinstance(obj, (datetime, date)): return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

# --- FastAPI Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup...")
    global db_pool, ollama_client, DB_SCHEMA_CACHE, DB_HINTS_CACHE, DB_SCHEMA_HASH
    
    ollama_client = AsyncClient(host=os.getenv("OLLAMA_HOST", "http://ollama:11434"))
    logger.info("Ollama async client initialized.")

    try:
        db_pool = await asyncpg.create_pool(
            user=os.getenv("POSTGRES_USER_APP", "aisavvy"),
            password=os.getenv("POSTGRES_PASSWORD_APP", "my_password"),
            database=os.getenv("POSTGRES_DB", "mydb"),
            host=os.getenv("DB_HOST", "db"),
        )
        logger.info("Database connection pool created.")
    except Exception as e:
        logger.critical(f"FATAL: Could not connect to PostgreSQL: {e}"); raise
    
    await setup_databases()
    logger.info("Cache database initialized.")
    DB_SCHEMA_CACHE, DB_HINTS_CACHE, _ = await get_schema_and_hints()
    DB_SCHEMA_HASH = hashlib.sha256((DB_SCHEMA_CACHE + DB_HINTS_CACHE).encode()).hexdigest()
    logger.info("Database schema and value hints pre-loaded.")
    
    logger.info("Application startup complete.")
    yield
    
    logger.info("Application shutdown...")
    if db_pool: await db_pool.close()

# --- FastAPI App Initialization ---
app = FastAPI(title="AISavvy API v7 (Local LLM Edition)", lifespan=lifespan)

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
            CREATE TABLE IF NOT EXISTS query_log (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, sql_query TEXT, success BOOLEAN, error_message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
        """)
        await db.commit()
async def get_from_cache(key: str):
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        c = await db.execute("SELECT response FROM llm_cache WHERE key = ?", (key,)); row = await c.fetchone(); return json.loads(row[0]) if row else None
async def set_to_cache(key: str, response: dict):
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO llm_cache (key, response) VALUES (?, ?)", (key, json.dumps(response, default=json_default_encoder))); await db.commit()
async def log_query(question, sql, success, error=""):
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        await db.execute("INSERT INTO query_log (question, sql_query, success, error_message) VALUES (?, ?, ?, ?)",(question, sql, success, error)); await db.commit()
async def get_schema_and_hints():
    async with db_pool.acquire() as conn:
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"); schema_parts, dot_parts, hint_parts = [], ["digraph ERD {", "graph [rankdir=LR];", "node [shape=plaintext];"], []
        for table in tables:
            table_name = table['table_name']
            columns_records = await conn.fetch(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position;"); column_names = [col['column_name'] for col in columns_records]; schema_parts.append(f"{table_name}({', '.join(column_names)})")
            
            label = f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0"><TR><TD BGCOLOR="lightblue"><B>{table_name}</B></TD></TR>'
            for col in columns_records:
                label += f'<TR><TD PORT="{col["column_name"]}" ALIGN="LEFT">{col["column_name"]} <FONT COLOR="grey50">({col["data_type"]})</FONT></TD></TR>'
            label += '</TABLE>>'
            dot_parts.append(f'  "{table_name}" [shape=none, margin=0, label={label}];')

        dot_parts.append('"employee":"department_id" -> "departments":"department_id";')
        dot_parts.append('"chef":"employee_id" -> "employee":"employee_id";')
        dot_parts.append('"salary":"employee_id" -> "employee":"employee_id";')
        dot_parts.append('"sales":"employee_id" -> "employee":"employee_id";')
        dot_parts.append('"purchase":"product_id" -> "kitchen_products":"product_id";')
        
        dept_names = await conn.fetch("SELECT DISTINCT department_name FROM departments ORDER BY department_name LIMIT 10")
        if dept_names: hint_parts.append(f"- The 'department_name' column can have values like: {[row['department_name'] for row in dept_names]}")
        return "\n".join(schema_parts), "\n".join(hint_parts), "\n".join(dot_parts) + "\n}"

# --- Prompt Generation Functions ---
def generate_sql_prompt(schema, hints, history: List[Turn]):
    conversation_log = "\n".join([f"User: {turn.content}" if turn.role == 'user' else f"Assistant (Result): {json.dumps(turn.content['result'], default=json_default_encoder)}" for turn in history[:-1] if turn.role == 'user' or (isinstance(turn.content, dict) and 'result' in turn.content)])
    last_question = history[-1].content
    return f"""You are a world-class PostgreSQL query writer AI. Your output MUST BE ONLY the SQL query or a `CLARIFY:` question. No other text or markdown.
### SCHEMA:
{schema}
### HINTS:
{hints if hints else "No hints available."}
### EXAMPLES:
User: "Show departments that have more than 2 employees"
SQL: SELECT d.department_name FROM employees e JOIN departments d ON e.department_id = d.department_id GROUP BY d.department_name HAVING COUNT(e.employee_id) > 2;
### HISTORY:
{conversation_log if conversation_log else "No history."}
### FINAL QUESTION:
{last_question}
### RESPONSE:
"""
def generate_relevance_prompt(schema, question):
    return f"Is this question related to the database schema? Schema: {schema}\nQuestion: {question}\nAnswer ONLY 'YES' or 'NO'."
def generate_no_results_prompt(question, sql_query):
    return f"The user asked: '{question}'. The query `{sql_query}` returned no rows. In one friendly sentence, explain why. Respond ONLY with the sentence."
def generate_summary_prompt(question, result_data):
    return f"""The user asked: "{question}". The data result is:
{json.dumps(result_data, indent=2, default=json_default_encoder)}
Write a short, friendly summary of this data. Respond ONLY with the summary sentence."""

async def call_ollama(prompt: str) -> str:
    logger.info("--- Calling Local Ollama API ---")
    try:
        response = await ollama_client.chat(model=os.getenv("LLM_MODEL", "llama3"), messages=[{'role': 'user', 'content': prompt}], options={'temperature': 0.0})
        return response['message']['content']
    except Exception as e:
        logger.error(f"Error calling Ollama API: {e}"); return f"OLLAMA_API_ERROR: {str(e)}"

# --- API Endpoints ---
@app.get("/")
async def read_root(): return {"status": "healthy"}

@app.post("/query", tags=["Core Logic"])
async def process_query(request: QueryRequest):
    last_question = request.history[-1].content
    if not isinstance(last_question, str): raise HTTPException(status_code=400, detail="Invalid question format.")
    
    relevance_prompt = generate_relevance_prompt(DB_SCHEMA_CACHE, last_question)
    relevance_response = await call_ollama(relevance_prompt)
    if "OLLAMA_API_ERROR" in relevance_response: raise HTTPException(status_code=503, detail=relevance_response)
    if 'NO' in relevance_response.strip().upper(): return {"off_topic": "That question does not seem to be about the database."}
    
    history_str = json.dumps([turn.dict() for turn in request.history], default=json_default_encoder)
    cache_key_hash = hashlib.sha256((history_str + DB_SCHEMA_HASH).encode()).hexdigest()
    if cached_response := await get_from_cache(cache_key_hash): return cached_response
    
    sql_prompt = generate_sql_prompt(DB_SCHEMA_CACHE, DB_HINTS_CACHE, request.history)
    response_text = await call_ollama(sql_prompt)
    if "OLLAMA_API_ERROR" in response_text: raise HTTPException(status_code=503, detail=response_text)
    
    if response_text.strip().upper().startswith("CLARIFY:"):
        return {"clarification": response_text[len("CLARIFY:"):].strip()}
    
    sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", response_text, re.DOTALL); sql_query = (sql_match.group(1).strip() if sql_match else response_text).rstrip(';')
    
    try:
        async with db_pool.acquire() as conn:
            stmt = await conn.prepare(sql_query); records = await stmt.fetch(); results = [dict(record) for record in records]
        await log_query(last_question, sql_query, True)
    except asyncpg.PostgresError as e:
        error_message = str(e); await log_query(last_question, sql_query, False, error_message)
        fix_prompt = f"The SQL query `{sql_query}` failed with the error: `{error_message}`. Based on the question: `{last_question}` and schema: `{DB_SCHEMA_CACHE}`, provide a corrected SQL query. Respond ONLY with the SQL."
        suggested_fix = await call_ollama(fix_prompt)
        raise HTTPException(status_code=400, detail={"error": error_message, "suggested_fix": suggested_fix})
    
    if not results:
        no_results_prompt = generate_no_results_prompt(last_question, sql_query); explanation = await call_ollama(no_results_prompt)
        return {"no_results_explanation": explanation}
    
    summary_prompt = generate_summary_prompt(last_question, results)
    summary = await call_ollama(summary_prompt)
    
    chart_spec = {"chart_needed": False}
    if len(results) > 1:
        try:
            viz_prompt = f"Given the question: '{last_question}' and data columns: {list(results[0].keys())}, should this be a chart? If yes, suggest a chart type (bar, line, pie) and columns for x/y axes. Respond ONLY with a valid JSON object like {{\"chart_needed\": true, \"chart_type\": \"bar\", \"x_column\": \"name\", \"y_column\": \"salary\"}} or {{\"chart_needed\": false}}."
            viz_response = await call_ollama(viz_prompt); chart_spec = json.loads(viz_response.strip())
        except Exception: pass
    
    final_response = {"question": last_question, "sql_query": sql_query, "summary": summary, "result": results, "chart_spec": chart_spec}
    await set_to_cache(cache_key_hash, final_response)
    return final_response

@app.get("/history")
async def get_history():
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        db.row_factory = aiosqlite.Row; c = await db.execute("SELECT * FROM query_log ORDER BY created_at DESC"); rows = await c.fetchall(); return [dict(row) for row in rows]

@app.get("/schema/erd")
async def get_schema_erd():
    _, _, erd_dot_string = await get_schema_and_hints(); return {"dot_string": erd_dot_string}
