import os
import re
import json
import hashlib
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Union
from decimal import Decimal

import asyncpg
import aiosqlite
# --- NEW: Import Google's library ---
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --- Configuration & In-memory Caches ---
CACHE_DB_PATH = "/app/data/cache.db"
DB_SCHEMA_CACHE = ""
DB_HINTS_CACHE = ""
DB_SCHEMA_HASH = ""
db_pool = None
# --- NEW: Gemini Model client ---
gemini_model = None

# --- Custom JSON Encoder ---
def json_default_encoder(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

# --- FastAPI Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application startup...")
    global db_pool, gemini_model, DB_SCHEMA_CACHE, DB_HINTS_CACHE, DB_SCHEMA_HASH
    
    # 1. Configure the Gemini client
    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        genai.configure(api_key=gemini_api_key)
        gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        print("Google Gemini client configured.")
    except Exception as e:
        print(f"FATAL: Could not configure Gemini client: {e}")
        raise

    # 2. Initialize PostgreSQL Connection Pool
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
    
    # 3. Initialize Cache and load schema/hints
    await setup_databases()
    print("Cache database initialized.")
    DB_SCHEMA_CACHE, DB_HINTS_CACHE, _ = await get_schema_and_hints()
    DB_SCHEMA_HASH = hashlib.sha256((DB_SCHEMA_CACHE + DB_HINTS_CACHE).encode()).hexdigest()
    print("Database schema and value hints pre-loaded.")
    
    print("Application startup complete.")
    yield
    
    print("Application shutdown...")
    if db_pool:
        await db_pool.close()
        print("Database connection pool closed.")

app = FastAPI(
    title="AISavvy API v6 (Gemini Edition)",
    description="A high-performance API using Google's Gemini for Conversational SQL.",
    lifespan=lifespan
)

# --- Pydantic Models and Helper functions are unchanged ---
class Turn(BaseModel):
    role: str
    content: Union[str, Dict[str, Any]]
class QueryRequest(BaseModel):
    history: List[Turn]
# ... (setup_databases, get_from_cache, set_to_cache, log_query, get_schema_and_hints)
# ... are the same as before. For brevity they are omitted here.

# --- NEW: Centralized function to call the Gemini API ---
async def call_gemini(prompt: str) -> str:
    """Calls the Gemini API and returns the text response."""
    try:
        response = await gemini_model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        # Return a specific error string that the main logic can check for
        return f"GEMINI_API_ERROR: {str(e)}"

# --- Prompt Generation Functions are unchanged ---
# ... (generate_sql_prompt, generate_relevance_prompt, generate_no_results_prompt)
# ... are the same as before.

# --- API Endpoints ---
@app.get("/", tags=["Health Check"])
async def read_root():
    return {"status": "healthy"}

@app.post("/query", tags=["Core Logic"])
async def process_query(request: QueryRequest):
    last_question = request.history[-1].content
    if not isinstance(last_question, str):
        raise HTTPException(status_code=400, detail="Invalid question format.")

    # --- Step 1: Relevance Check using Gemini ---
    relevance_prompt = generate_relevance_prompt(DB_SCHEMA_CACHE, last_question)
    relevance_response = await call_gemini(relevance_prompt)
    if "GEMINI_API_ERROR" in relevance_response:
        raise HTTPException(status_code=503, detail=relevance_response)
    if 'NO' in relevance_response.strip().upper():
        return {"off_topic": "That question does not seem to be about the database. Please ask a question related to employees or departments."}

    # --- Step 2: Cache Check (unchanged) ---
    history_str = json.dumps([turn.dict() for turn in request.history], default=json_default_encoder)
    cache_key_hash = hashlib.sha256((history_str + DB_SCHEMA_HASH).encode()).hexdigest()
    cached_response = await get_from_cache(cache_key_hash)
    if cached_response:
        return cached_response

    # --- Step 3: Generate SQL or Clarification using Gemini ---
    sql_prompt = generate_sql_prompt(DB_SCHEMA_CACHE, DB_HINTS_CACHE, request.history)
    response_text = await call_gemini(sql_prompt)
    if "GEMINI_API_ERROR" in response_text:
        raise HTTPException(status_code=503, detail=response_text)
    
    if response_text.strip().upper().startswith("CLARIFY:"):
        return {"clarification": response_text[len("CLARIFY:"):].strip()}

    sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", response_text, re.DOTALL)
    sql_query = (sql_match.group(1).strip() if sql_match else response_text).rstrip(';')
    
    # --- Step 4: Execute Query (unchanged) ---
    results = []
    try:
        async with db_pool.acquire() as conn:
            stmt = await conn.prepare(sql_query)
            records = await stmt.fetch()
            results = [dict(record) for record in records]
        await log_query(last_question, sql_query, True)
    except asyncpg.PostgresError as e:
        # --- Auto-fix now uses Gemini ---
        error_message = str(e)
        await log_query(last_question, sql_query, False, error_message)
        fix_prompt = f"The following SQL query failed: `{sql_query}`. The database error was: `{error_message}`. Based on the user's question: `{last_question}` and the schema: `{DB_SCHEMA_CACHE}`, provide a corrected SQL query. Respond with ONLY the corrected SQL query."
        suggested_fix = await call_gemini(fix_prompt)
        raise HTTPException(status_code=400, detail={"error": error_message, "suggested_fix": suggested_fix})

    # --- Step 5: Handle Empty Results using Gemini ---
    if not results:
        no_results_prompt = generate_no_results_prompt(last_question, sql_query)
        explanation = await call_gemini(no_results_prompt)
        return {"no_results_explanation": explanation}
    
    # --- Step 6: Generate Explanation & DataViz Spec using Gemini ---
    explain_prompt = f"In one simple, plain English sentence, explain what this SQL query does: `{sql_query}`"
    explanation = await call_gemini(explain_prompt)
    
    viz_prompt = f"Given the user's question: '{last_question}' and these resulting data columns: {list(results[0].keys())}. Should this be visualized? If yes, suggest a chart type (bar, line, or pie) and columns for x/y axes. Respond ONLY with a single, valid JSON object like {{\"chart_needed\": true, \"chart_type\": \"bar\", \"x_column\": \"name\", \"y_column\": \"salary\"}} or {{\"chart_needed\": false}}."
    viz_response = await call_gemini(viz_prompt)
    try:
        chart_spec = json.loads(viz_response.strip())
    except json.JSONDecodeError:
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
