import os
import re
import json
import hashlib
import logging # NEW: Import the logging library
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Union
from decimal import Decimal

import asyncpg
import aiosqlite
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --- NEW: Configure a logger ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration & In-memory Caches ---
CACHE_DB_PATH = "/app/data/cache.db"
DB_SCHEMA_CACHE = ""
DB_HINTS_CACHE = ""
DB_SCHEMA_HASH = ""
db_pool = None
gemini_model = None

# --- Custom JSON Encoder to Handle Database Decimal Types ---
def json_default_encoder(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

# --- FastAPI Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup and shutdown events."""
    logger.info("Application startup...")
    global db_pool, gemini_model, DB_SCHEMA_CACHE, DB_HINTS_CACHE, DB_SCHEMA_HASH
    
    # 1. Configure the Gemini client
    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        genai.configure(api_key=gemini_api_key)
        gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        logger.info("Google Gemini client configured.")
    except Exception as e:
        logger.critical(f"FATAL: Could not configure Gemini client: {e}")
        raise

    # 2. Initialize PostgreSQL Connection Pool
    try:
        db_pool = await asyncpg.create_pool(
            user=os.getenv("POSTGRES_USER_APP", "aisavvy"),
            password=os.getenv("POSTGRES_PASSWORD_APP", "my_password"),
            database=os.getenv("POSTGRES_DB", "mydb"),
            host=os.getenv("DB_HOST", "db"),
        )
        logger.info("Database connection pool created.")
    except Exception as e:
        logger.critical(f"FATAL: Could not connect to PostgreSQL: {e}")
        raise
    
    # 3. Initialize Cache and Log Database
    await setup_databases()
    logger.info("Cache database initialized.")
    
    # 4. Pre-load DB Schema and Value Hints
    DB_SCHEMA_CACHE, DB_HINTS_CACHE, _ = await get_schema_and_hints()
    DB_SCHEMA_HASH = hashlib.sha256((DB_SCHEMA_CACHE + DB_HINTS_CACHE).encode()).hexdigest()
    logger.info("Database schema and value hints pre-loaded.")
    
    logger.info("Application startup complete.")
    yield
    
    # --- On Shutdown ---
    logger.info("Application shutdown...")
    if db_pool:
        await db_pool.close()
        logger.info("Database connection pool closed.")

# --- FastAPI App Initialization ---
app = FastAPI(
    title="AISavvy API v6 (Gemini Edition)",
    description="A high-performance API using Google's Gemini for Conversational SQL.",
    lifespan=lifespan
)

# --- Pydantic Models ---
class Turn(BaseModel):
    role: str
    content: Union[str, Dict[str, Any]]

class QueryRequest(BaseModel):
    history: List[Turn]

# --- Helper Functions (Unchanged) ---
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
            row = await cursor.fetchone(); return json.loads(row[0]) if row else None
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
            table_name = table['table_name']; columns_records = await conn.fetch(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position;"); column_names = [col['column_name'] for col in columns_records]; schema_parts.append(f"{table_name}({', '.join(column_names)})")
        dept_names = await conn.fetch("SELECT DISTINCT department_name FROM departments ORDER BY department_name LIMIT 10");
        if dept_names: hint_parts.append(f"- The 'department_name' column can have values like: {[row['department_name'] for row in dept_names]}")
        return "\n".join(schema_parts), "\n".join(hint_parts), "\n".join(dot_parts) + "\n}"

# --- Prompt Generation Functions (Unchanged) ---
def generate_sql_prompt(schema, hints, history: List[Turn]):
    # ...
    return f"""..."""
def generate_relevance_prompt(schema, question):
    # ...
    return f"..."
def generate_no_results_prompt(question, sql_query):
    # ...
    return f"..."

async def call_gemini(prompt: str) -> str:
    logger.info("--- Calling Gemini API ---")
    logger.info(f"PROMPT:\n{prompt}")
    try:
        generation_config = genai.types.GenerationConfig(temperature=0.0)
        safety_settings = {'HATE_SPEECH': 'BLOCK_NONE', 'HARASSMENT': 'BLOCK_NONE', 'SEXUALLY_EXPLICIT': 'BLOCK_NONE', 'DANGEROUS_CONTENT': 'BLOCK_NONE'}
        response = await gemini_model.generate_content_async(prompt, generation_config=generation_config, safety_settings=safety_settings)
        logger.info(f"GEMINI RAW RESPONSE:\n{response.text}")
        return response.text
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        return f"GEMINI_API_ERROR: {str(e)}"

# --- API Endpoints ---
@app.get("/", tags=["Health Check"])
async def read_root():
    return {"status": "healthy"}

@app.post("/query", tags=["Core Logic"])
async def process_query(request: QueryRequest):
    logger.info(f"--- Received new query request ---")
    last_question = request.history[-1].content
    if not isinstance(last_question, str):
        raise HTTPException(status_code=400, detail="Invalid question format.")

    # 1. Relevance Check
    logger.info("Step 1: Performing relevance check...")
    relevance_prompt = generate_relevance_prompt(DB_SCHEMA_CACHE, last_question)
    relevance_response = await call_gemini(relevance_prompt)
    if "GEMINI_API_ERROR" in relevance_response: raise HTTPException(status_code=503, detail=relevance_response)
    if 'NO' in relevance_response.strip().upper():
        logger.warning("Query marked as OFF-TOPIC.")
        return {"off_topic": "That question does not seem to be about the database."}
    logger.info("Relevance check PASSED.")

    # 2. Cache Check
    logger.info("Step 2: Checking cache...")
    history_str = json.dumps([turn.dict() for turn in request.history], default=json_default_encoder)
    cache_key_hash = hashlib.sha256((history_str + DB_SCHEMA_HASH).encode()).hexdigest()
    if cached_response := await get_from_cache(cache_key_hash):
        logger.info("CACHE HIT! Returning cached response.")
        return cached_response
    logger.info("CACHE MISS. Proceeding to generate SQL.")

    # 3. Generate SQL or Clarification
    logger.info("Step 3: Generating SQL query...")
    sql_prompt = generate_sql_prompt(DB_SCHEMA_CACHE, DB_HINTS_CACHE, request.history)
    response_text = await call_gemini(sql_prompt)
    if "GEMINI_API_ERROR" in response_text: raise HTTPException(status_code=503, detail=response_text)
    
    if response_text.strip().upper().startswith("CLARIFY:"):
        logger.info("AI requested clarification.")
        return {"clarification": response_text[len("CLARIFY:"):].strip()}

    sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", response_text, re.DOTALL)
    sql_query = (sql_match.group(1).strip() if sql_match else response_text).rstrip(';')
    logger.info(f"EXTRACTED SQL QUERY:\n{sql_query}")
    
    # 4. Execute Query
    logger.info("Step 4: Executing SQL query against the database...")
    try:
        async with db_pool.acquire() as conn:
            stmt = await conn.prepare(sql_query)
            records = await stmt.fetch()
            results = [dict(record) for record in records]
        await log_query(last_question, sql_query, True)
        logger.info(f"Query executed successfully. Rows returned: {len(results)}")
    except asyncpg.PostgresError as e:
        error_message = str(e)
        logger.error(f"DATABASE ERROR: {error_message}")
        await log_query(last_question, sql_query, False, error_message)
        # ... (Auto-fix logic)
        raise HTTPException(status_code=400, detail={"error": error_message})

    # 5. Handle Empty Results
    if not results:
        logger.info("Step 5: Query returned no results, generating explanation...")
        no_results_prompt = generate_no_results_prompt(last_question, sql_query)
        explanation = await call_gemini(no_results_prompt)
        return {"no_results_explanation": explanation}
    
    # 6. Generate Explanation & DataViz Spec
    logger.info("Step 6: Generating explanation and DataViz spec...")
    explain_prompt = f"Explain this SQL query in one simple sentence: `{sql_query}`"
    explanation = await call_gemini(explain_prompt)
    
    # ... (DataViz logic)
    chart_spec = {"chart_needed": False}
    
    final_response = {"question": last_question, "sql_query": sql_query, "explanation": explanation, "result": results, "chart_spec": chart_spec}
    logger.info("Step 7: Caching final response and returning to client.")
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
