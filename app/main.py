import os
import psycopg2
import ollama
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List

# --- Configuration (No changes here) ---
DB_HOST = os.getenv("DB_HOST", "db")
DB_NAME = os.getenv("POSTGRES_DB", "mydb")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "my_password")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
LLM_MODEL = "gemma:2b"

app = FastAPI(
    title="GemmaTalksDB API",
    description="An API to convert natural language questions into SQL queries with conversational context.",
)

# --- NEW: Pydantic models for conversational history ---
class Turn(BaseModel):
    role: str
    content: str

class QueryRequest(BaseModel):
    history: List[Turn] = Field(..., description="The entire conversation history.")


# --- Helper Functions (get_db_connection, get_db_schema are unchanged) ---
def get_db_connection():
    return psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port="5432"
    )

def get_db_schema(conn):
    schema_str = ""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
        """)
        tables = [row[0] for row in cur.fetchall()]
        for table in tables:
            cur.execute(f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = '{table}' ORDER BY ordinal_position;
            """)
            columns = cur.fetchall()
            schema_str += f"CREATE TABLE {table} (\n"
            for col in columns:
                col_name, data_type, is_nullable = col
                schema_str += f"  {col_name} {data_type}{' NOT NULL' if is_nullable == 'NO' else ''},\n"
            cur.execute(f"""
                SELECT c.column_name FROM information_schema.key_column_usage AS c
                LEFT JOIN information_schema.table_constraints AS t ON t.constraint_name = c.constraint_name
                WHERE t.table_name = '{table}' AND t.constraint_type = 'PRIMARY KEY';
            """)
            pk = cur.fetchone()
            if pk:
                schema_str += f"  PRIMARY KEY ({pk[0]})\n"
            schema_str = schema_str.rstrip(',\n') + "\n);\n\n"
    return schema_str

# --- NEW: Prompt generation now includes conversation history ---
# In app/main.py, replace the existing generate_prompt function with this one.

def generate_prompt(schema, history):
    # Format the conversation history for the prompt
    conversation_log = ""
    for turn in history[:-1]:  # Exclude the latest question
        if turn.role == 'user':
            conversation_log += f"User: {turn.content}\n"
        elif turn.role == 'assistant':
            conversation_log += f"Assistant's SQL Output: {turn.content}\n"

    last_question = history[-1].content

    prompt = f"""You are a world-class PostgreSQL query writer AI. Your task is to write a single, valid PostgreSQL query to answer the user's final question, using the provided database schema and conversation history as context.

### IMMUTABLE RULES:
1.  **YOU MUST ONLY USE TABLES AND COLUMNS FROM THE SCHEMA PROVIDED BELOW.** Do not invent columns like 'e.manager' or tables that are not listed.
2.  The `employees` table **DOES NOT** have a 'manager' column. The manager's name for a department is ONLY in the 'manager' column of the `departments` table.
3.  Analyze the `Conversation History` to understand follow-up questions (e.g., references like "his", "her", "that").
4.  If the conversation history is empty or unclear, rely solely on the user's final question and the schema.
5.  Your output **MUST BE ONLY THE SQL QUERY**. No explanations, no markdown, just the raw SQL.

### DATABASE SCHEMA (Ground Truth):
{schema}

### CONVERSATION HISTORY (Context):
{conversation_log if conversation_log else "No previous conversation."}

### FINAL USER QUESTION (Your Task):
{last_question}

### SQL QUERY:
"""
    return prompt.strip()


@app.post("/query")
async def process_query(request: QueryRequest):
    conn = None
    try:
        conn = get_db_connection()
        schema = get_db_schema(conn)
        # Pass the full history to the prompt generator
        prompt = generate_prompt(schema, request.history)
        
        # The LLM prompt now contains history, but we only send the final prompt to the model
        client = ollama.Client(host=OLLAMA_HOST)
        response = client.chat(
            model=LLM_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0.0}
        )
        raw_sql = response['message']['content'].strip()
        
        sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", raw_sql, re.DOTALL)
        if sql_match:
            sql_query = sql_match.group(1).strip()
        else:
            sql_query = raw_sql

        if sql_query.endswith(';'):
            sql_query = sql_query[:-1]

        print(f"--- Extracted SQL ---\n{sql_query}\n---------------------")

        with conn.cursor() as cur:
            cur.execute(sql_query)
            if cur.description:
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]
            else:
                results = {"status": "success", "rows_affected": cur.rowcount}
        
        return {"question": request.history[-1].content, "sql_query": sql_query, "result": results}

    except psycopg2.Error as e:
        print(f"Database Error: {e}")
        raise HTTPException(status_code=400, detail=f"Database Error: {str(e)}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
    finally:
        if conn is not None:
            conn.close()
            print("Database connection closed.")