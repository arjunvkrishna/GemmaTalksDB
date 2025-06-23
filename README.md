# GemmaTalksDB 🗣️↔️🐘

**Talk to your PostgreSQL database in plain English. A fully containerized, local-first, Natural Language to SQL engine powered by Gemma, Ollama, and Docker.**

This project provides a complete, ready-to-use system that accepts natural language questions via an API, uses a local Large Language Model (LLM) to translate them into SQL queries, executes them against a PostgreSQL database, and returns the results.

---

## 🏛️ Architecture

The entire system is orchestrated with Docker Compose and consists of three main services that work together seamlessly:

1.  **`db` (PostgreSQL):** The database service that stores your data. It's automatically initialized with a sample schema and data on first startup.
2.  **`ollama` (Ollama + Gemma):** The LLM service. It downloads and serves the Gemma LLM, making it available for inference without any external API calls.
3.  **`app` (The GemmaTalksDB API):** A Python FastAPI application that acts as the brain of the operation. It receives user requests, orchestrates the prompt engineering, communicates with the LLM, executes the generated SQL, and returns the final result.

### System Flow

Here is how a request flows through the system:

```mermaid
graph TD
    A[👨‍💻 User] -- "POST /query with a question" --> B(🚀 GemmaTalksDB API);
    B -- "1. Fetch schema" --> C(🐘 PostgreSQL DB);
    C -- "2. Return schema" --> B;
    B -- "3. Send prompt (question + schema)" --> D(🧠 Ollama / Gemma LLM);
    D -- "4. Return generated SQL query" --> B;
    B -- "5. Execute SQL query" --> C;
    C -- "6. Return query results" --> B;
    B -- "7. Send JSON response" --> A;

✨ Features

    Conversational Queries: Ask questions in natural English instead of writing complex SQL.
    Local & Private: Runs entirely on your local machine. No data leaves your system, and no external API keys are needed.
    Fully Containerized: One command (docker-compose up) to set up and run the entire stack.
    Dynamic Schema Introspection: Automatically detects your database schema, making it adaptable to other tables.
    Advanced Prompt Engineering: Utilizes few-shot prompting to guide the LLM, improving accuracy and reducing errors.
    Extensible: Easy to modify, experiment with different LLMs (like Llama3, Mistral), or integrate into larger applications.

🛠️ Tech Stack

    Backend: Python, FastAPI
    Database: PostgreSQL
    LLM Serving: Ollama
    LLM Model: Google's Gemma
    Containerization: Docker & Docker Compose

🚀 Getting Started

Follow these steps to get the project up and running on your local machine.
Prerequisites

    Docker Desktop: Ensure you have Docker and Docker Compose installed and running. You can download it from the official Docker website.

Installation

    Clone the repository:
    Bash

git clone https://github.com/arjunvkrishna/GemmaTalksDB.git

Navigate to the project directory:
Bash

cd GemmaTalksDB

Build and run the services:
This command will build the API image, pull the Postgres and Ollama images, and start all three containers.
Bash

docker-compose up --build

Your terminal will now show a continuous stream of logs from all services.

Download the LLM Model (One-time setup):
The Ollama container starts empty. You need to tell it to download the Gemma model.
Open a new terminal window, navigate to the same project directory, and run:
Bash

    docker-compose exec ollama ollama pull gemma:2b

    Wait for the download to complete (it's about 1.7 GB).

The system is now fully operational!
💡 Usage

The API is available at http://localhost:8000. You can interact with it using any API client or the curl command.
Example 1: Asking for a manager
Bash

curl -X POST "http://localhost:8000/query" \
-H "Content-Type: application/json" \
-d '{"question": "Who is the manager of the Sales department?"}'

✅ Expected Success Response:
JSON

{
  "question": "Who is the manager of the Sales department?",
  "sql_query": "SELECT manager FROM departments WHERE department_name = 'Sales'",
  "result": [
    {
      "manager": "Charlie Brown"
    }
  ]
}

Example 2: Asking for an employee count
Bash

curl -X POST "http://localhost:8000/query" \
-H "Content-Type: application/json" \
-d '{"question": "How many employees are there in the Engineering department?"}'

✅ Expected Success Response:
JSON

{
  "question": "How many employees are there in the Engineering department?",
  "sql_query": "SELECT COUNT(e.employee_id) AS total_employees FROM employees e INNER JOIN departments d ON e.department_id = d.department_id WHERE d.department_name = 'Engineering'",
  "result": [
    {
      "total_employees": 3
    }
  ]
}

🧠 Prompt Engineering Journey

A key part of this project was refining the prompt sent to the LLM to improve its accuracy. We progressed through several versions:

    V1 (Basic): A simple request to convert a question to SQL. This often led to errors.
    V2 (Schema-Aware): We provided the database schema (table and column names) in the prompt. This improved results but still led to hallucinations (e.g., using id instead of department_id).
    V3 (Rich Schema & Strict Rules): The schema was formatted as CREATE TABLE statements, and stricter instructions were added. This solved most syntax errors but not all semantic ones.
    V4 (Few-Shot Prompt - Final Version): The prompt was enhanced with a concrete example (a "few-shot" example) of a similar question and the correct SQL. This provided a template for the LLM to follow, finally resolving the semantic ambiguity and producing the correct query consistently.

📈 Future Improvements

    Web Interface: Build a simple frontend using Streamlit or Gradio for a more user-friendly chat interface.
    Support for Other LLMs: Experiment with different models available on Ollama (like llama3 or mistral) by simply changing the model name in main.py.
    Enhanced Security: Implement a query sanitization layer or run the database user in a read-only mode for production-like environments.
    Conversation History: Allow the API to remember the context of previous questions in a conversation.

