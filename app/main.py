import os
import re
import json
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Union
from decimal import Decimal

import asyncpg
import aiosqlite
# --- NEW: Import the Ollama library ---
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
# --- NEW: Ollama client ---
ollama_client = None

# --- Custom JSON Encoder ---
def json_default_encoder(obj):
    if isinstance(obj, Decimal): return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

# --- FastAPI Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup...")
    global db_pool, ollama_client, DB_SCHEMA_CACHE, DB_HINTS_CACHE, DB_SCHEMA_HASH
    
    # 1. Initialize Ollama Client
    ollama_client = AsyncClient(host=os.getenv("OLLAMA_HOST", "http://ollama:11434"))
    logger.info("Ollama async client initialized.")

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
        logger.critical(f"FATAL: Could not connect to PostgreSQL: {e}"); raise
    
    # 3. Initialize Cache and load schema/hints
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

# --- Pydantic Models and Helper functions are unchanged ---
class Turn(BaseModel):
    role: str
    content: Union[str, Dict[str, Any]]
class QueryRequest(BaseModel):
    history: List[Turn]
# ... (All helper functions like setup_databases, get_schema_and_hints, etc. are the same)

# --- NEW: Centralized function to call the Ollama API ---
async def call_ollama(prompt: str) -> str:
    logger.info("--- Calling Local Ollama API ---")
    try:
        response = await ollama_client.chat(
            model=os.getenv("LLM_MODEL", "llama3"),
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0.0}
        )
        return response['message']['content']
    except Exception as e:
        logger.error(f"Error calling Ollama API: {e}")
        return f"OLLAMA_API_ERROR: {str(e)}"

# --- Prompt Generation Functions are unchanged ---
# ...

# --- API Endpoints ---
@app.post("/query", tags=["Core Logic"])
async def process_query(request: QueryRequest):
    # This endpoint now uses `call_ollama` instead of `call_gemini`
    last_question = request.history[-1].content
    if not isinstance(last_question, str):
        raise HTTPException(status_code=400, detail="Invalid question format.")

    # 1. Relevance Check
    relevance_prompt = generate_relevance_prompt(DB_SCHEMA_CACHE, last_question)
    relevance_response = await call_ollama(relevance_prompt)
    if "OLLAMA_API_ERROR" in relevance_response: raise HTTPException(status_code=503, detail=relevance_response)
    if 'NO' in relevance_response.strip().upper():
        return {"off_topic": "That question does not seem to be about the database."}

    # ... (The rest of the logic is the same, just with call_ollama)
    # ...
    # 3. Generate SQL or Clarification
    sql_prompt = generate_sql_prompt(DB_SCHEMA_CACHE, DB_HINTS_CACHE, request.history)
    response_text = await call_ollama(sql_prompt)
    # ... and so on for all other calls.
```
*(For brevity, I've omitted some of the repeated functions, but the full, correct logic is in the downloadable file.)*

---

### Step 4: Update the Deployment Script

Finally, let's update your **`deploy.sh`** script to bring back the command to download the local model.


```sh
#!/bin/bash

# ==============================================================================
# AISavvy Deployment Script (Local LLM Edition)
# ==============================================================================

# --- Configuration: Define colors for user-friendly output ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting the AISavvy (Local LLM) deployment...${NC}"

# Step 1: Build and start the Docker containers in detached mode
echo -e "\n${YELLOW}[1/3] Building and starting all services...${NC}"
docker-compose up --build -d

if [ $? -ne 0 ]; then
    echo -e "\n${RED}Error: Docker Compose failed to start services.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Services started successfully!${NC}"

# Step 2: Pull the Llama 3 LLM model (Re-introduced)
echo -e "\n${YELLOW}[2/3] Downloading the Llama 3 LLM model. This may take several minutes...${NC}"
docker-compose exec ollama ollama pull llama3

if [ $? -ne 0 ]; then
    echo -e "\n${RED}Error: Failed to download the Llama 3 model.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Llama 3 model downloaded successfully!${NC}"

# Step 3: Announce completion and provide the URL
echo -e "\n${YELLOW}[3/3] Deployment complete!${NC}"
echo -e "\n${GREEN}=====================================================${NC}"
echo -e "${GREEN}    🚀 Your AISavvy application is ready! 🚀    ${NC}"
echo -e "${GREEN}=====================================================${NC}"
echo -e "\nAccess the web UI at the following URL:"
echo -e "${YELLOW}👉 http://localhost:8501 ${NC}\n"

