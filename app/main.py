import os
import psycopg2
import ollama
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --- Configuration ---
DB_HOST = os.getenv("DB_HOST", "db")
DB_NAME = os.getenv("POSTGRES_DB", "mydb")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "my_password")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
LLM_MODEL = "gemma:2b"

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Natural Language to SQL API",
    description="An API to convert natural language questions into SQL queries and execute them against a PostgreSQL database.",
)

# --- Pydantic Model for Request Body ---
class QueryRequest(BaseModel):
    question: str

# --- Helper Functions ---
def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port="5432"
        )
        return conn
    except psycopg2.OperationalError as e:
        print(f"Error connecting to database: {e}")
        raise

# --- NEW: Richer Schema Generation ---
def get_db_schema(conn):
    """
    Fetches the database schema and formats it as CREATE TABLE statements
    for better LLM comprehension.
    """
    schema_str = ""
    with conn.cursor() as cur:
        # Get table names
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
        """)
        tables = [row[0] for row in cur.fetchall()]

        for table in tables:
            # Get column details
            cur.execute(f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = '{table}' ORDER BY ordinal_position;
            """)
            columns = cur.fetchall()
            schema_str += f"CREATE TABLE {table} (\n"
            for col in columns:
                col_name, data_type, is_nullable = col
                schema_str += f"  {col_name} {data_type}"
                if is_nullable == 'NO':
                    schema_str += " NOT NULL"
                schema_str += ",\n"
            
            # Get primary key
            cur.execute(f"""
                SELECT c.column_name
                FROM information_schema.key_column_usage AS c
                LEFT JOIN information_schema.table_constraints AS t
                ON t.constraint_name = c.constraint_name
                WHERE t.table_name = '{table}' AND t.constraint_type = 'PRIMARY KEY';
            """)
            pk = cur.fetchone()
            if pk:
                schema_str += f"  PRIMARY KEY ({pk[0]})\n"

            schema_str = schema_str.rstrip(',\n') + "\n);\n\n"

    return schema_str

# --- NEW: More Forceful Prompt Engineering ---
# Find this function in your main.py and replace it with the one below.
# The rest of the file is unchanged.

# --- FINAL VERSION: Adding a "Few-Shot" Example to the Prompt ---
def generate_prompt(schema, question):
    """
    Generates the final, most effective prompt by including a specific example
    to guide the LLM's reasoning.
    """
    prompt = f"""You are an expert PostgreSQL assistant. Your task is to convert a natural language question into a SQL query based on the provided database schema.

### Instructions:
1.  Carefully examine the `CREATE TABLE` statements below.
2.  Pay close attention to the exact column names, especially the primary keys (`department_id`, `employee_id`).
3.  **Only use the tables and columns provided in the schema.** Do not hallucinate or guess any table or column names.
4.  You must output only a single, valid PostgreSQL query and nothing else.

### Database Schema:
{schema}

### Example (Very Important!):
If the question is about a department's manager, the answer is in the 'manager' column of the 'departments' table.
Question: "Who is the manager of the Engineering department?"
SQL Query: SELECT manager FROM departments WHERE department_name = 'Engineering';

### Your Task:
Use the schema and the example above to answer the following question.

Question: "{question}"

### SQL Query:
"""
    return prompt.strip()


# --- API Endpoint (no changes needed here) ---
@app.post("/query")
async def process_query(request: QueryRequest):
    try:
        conn = get_db_connection()
        schema = get_db_schema(conn)
        prompt = generate_prompt(schema, request.question)
        print(f"--- Generated Prompt ---\n{prompt}\n------------------------")
        
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

        # Remove trailing semicolon if it exists, as some DB drivers dislike it
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
        
        conn.close()
        
        return {"question": request.question, "sql_query": sql_query, "result": results}

    except psycopg2.Error as e:
        print(f"Database Error: {e}")
        raise HTTPException(status_code=400, detail=f"Database Error: {str(e)}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.get("/")
def read_root():
    return {"message": "Welcome to the Natural Language to SQL API. Please POST your question to the /query endpoint."}