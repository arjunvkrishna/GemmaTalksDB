import os
import re
import json
import hashlib
from contextlib import asynccontextmanager
from typing import List

import asyncpg
import aiosqlite
from ollama import AsyncClient
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --- NEW: Configuration for Cache ---
CACHE_DB_PATH = "/app/data/cache.db"

# --- In-memory caches for startup data ---
DB_SCHEMA_CACHE = ""
DB_SCHEMA_HASH = ""

# --- Async Clients ---
db_pool = None
ollama_client = None

# --- NEW: FastAPI Lifespan Manager for Startup/Shutdown Events ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # === On Startup ===
    print("Application startup...")
    global db_pool, ollama_client, DB_SCHEMA_CACHE, DB_SCHEMA_HASH

    # 1. Initialize DB Connection Pool
    try:
        db_pool = await asyncpg.create_pool(
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "my_password"),
            database=os.getenv("POSTGRES_DB", "mydb"),
            host=os.getenv("DB_HOST", "db"),
        )
        print("Database connection pool created.")
    except Exception as e:
        print(f"FATAL: Could not connect to PostgreSQL: {e}")
        # In a real app, you might want to exit or retry
        raise

    # 2. Initialize Ollama Client
    ollama_client = AsyncClient(host=os.getenv("OLLAMA_HOST", "http://ollama:11434"))
    print("Ollama async client initialized.")

    # 3. Pre-load DB Schema
    DB_SCHEMA_CACHE = await get_db_schema()
    DB_SCHEMA_HASH = hashlib.sha256(DB_SCHEMA_CACHE.encode()).hexdigest()
    print("Database schema pre-loaded and hashed.")
    print(f"Compressed Schema:\n{DB_SCHEMA_CACHE}")

    # 4. Initialize Cache DB
    await setup_cache_db()
    print("Cache database initialized.")
    
    yield # The application is now running

    # === On Shutdown ===
    print("Application shutdown...")
    if db_pool:
        await db_pool.close()
        print("Database connection pool closed.")

# --- FastAPI App Initialization with Lifespan Manager ---
app = FastAPI(
    title="GemmaTalksDB API v2",
    description="A high-performance API for converting natural language to SQL with caching and async I/O.",
    lifespan=lifespan
)

# --- Pydantic Models ---
class Turn(BaseModel):
    role: str
    content: str

class QueryRequest(BaseModel):
    history: List[Turn] = Field(..., description="The entire conversation history.")


# --- NEW: Caching Functions ---
async def setup_cache_db():
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                key TEXT PRIMARY KEY,
                response TEXT NOT NULL,
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
            (key, json.dumps(response)),
        )
        await db.commit()


# --- NEW: Schema Loading (now with Prompt Compression) ---
async def get_db_schema():
    """
    Fetches the schema and generates a compressed, token-efficient representation.
    """
    async with db_pool.acquire() as conn:
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
        """)
        
        schema_parts = []
        for table in tables:
            table_name = table['table_name']
            columns = await conn.fetch(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = '{table_name}' ORDER BY ordinal_position;
            """)
            column_names = ", ".join([col['column_name'] for col in columns])
            schema_parts.append(f"{table_name}({column_names})")
            
        return "\n".join(schema_parts)

# --- Prompt Generation (Unchanged logic, now uses cached schema) ---
def generate_prompt(schema, history):
    conversation_log = "\n".join(
        f"{turn.role}: {turn.content}" for turn in history[:-1]
    )
    last_question = history[-1].content
    
    prompt = f"""You are a world-class PostgreSQL query writer AI. Your task is to write a single, valid PostgreSQL query to answer the user's final question.

### IMMUTABLE RULES:
1.  **YOU MUST ONLY USE THE TABLES AND COLUMNS FROM THE COMPRESSED SCHEMA PROVIDED BELOW.**
2.  The schema is represented as `table_name(column1, column2)`.
3.  Analyze the `Conversation History` to resolve references (like "his", "her", "that").
4.  Your output **MUST BE ONLY THE SQL QUERY**. No explanations or markdown.

### COMPRESSED DATABASE SCHEMA:
{schema}

### CONVERSATION HISTORY:
{conversation_log if conversation_log else "No previous conversation."}

### FINAL USER QUESTION:
{last_question}

### SQL QUERY:
"""
    return prompt.strip()


# --- NEW: Fully Asynchronous API Endpoint ---
@app.post("/query")
async def process_query(request: QueryRequest):
    # 1. Generate Cache Key from history and schema hash
    history_str = json.dumps([turn.dict() for turn in request.history])
    cache_key_hash = hashlib.sha256((history_str + DB_SCHEMA_HASH).encode()).hexdigest()

    # 2. Check Cache First
    cached_response = await get_from_cache(cache_key_hash)
    if cached_response:
        print(f"CACHE HIT for key: {cache_key_hash}")
        return cached_response

    print(f"CACHE MISS for key: {cache_key_hash}")

    # 3. Generate Prompt
    prompt = generate_prompt(DB_SCHEMA_CACHE, request.history)

    # 4. Call LLM (Cache Miss)
    try:
        response = await ollama_client.chat(
            model=os.getenv("LLM_MODEL", "gemma:2b"),
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0.0}
        )
        raw_sql = response['message']['content'].strip()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {e}")

    # 5. Execute SQL against DB
    sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", raw_sql, re.DOTALL)
    sql_query = (sql_match.group(1).strip() if sql_match else raw_sql).rstrip(';')
    
    print(f"--- Extracted SQL ---\n{sql_query}\n---------------------")

    try:
        async with db_pool.acquire() as conn:
            stmt = await conn.prepare(sql_query)
            records = await stmt.fetch()
            results = [dict(record) for record in records] if records else []
    except asyncpg.PostgresError as e:
        raise HTTPException(status_code=400, detail=f"Database Error: {str(e)}")

    # 6. Format and Cache the Final Response
    final_response = {
        "question": request.history[-1].content,
        "sql_query": sql_query,
        "result": results
    }
    await set_to_cache(cache_key_hash, final_response)
    
    return final_response