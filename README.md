# AISavvy 🧠↔️📊

**An intelligent, conversational data platform. Chat with your PostgreSQL database, visualize results, and get AI-powered assistance, all running locally with Docker.**

AISavvy is a full-featured application that transforms how you interact with your data. It provides a multi-page web interface to ask questions in plain English, get back not just data but also charts, see a complete history of your interactions, visualize your database schema, and even get AI-powered suggestions to fix failed queries.

---

## ✨ Features

AISavvy is more than just a Text-to-SQL tool; it's a complete data intelligence platform with a rich feature set:

* **Conversational AI for SQL:** Engage in a continuous dialogue with your data. The AI understands context from previous questions.
* **Interactive Data Visualization:** Automatically detects when a chart is appropriate and generates bar, line, or pie charts from your query results using Altair.
* **AI-Powered SQL Auto-Fix:** If a generated query fails, the AI analyzes the error and suggests a corrected version of the SQL.
* **Persistent Query History & Export:** A dedicated page shows a complete log of all questions, the generated SQL, and their success status. You can export this history as a `.csv` or `.sql` file.
* **Database Schema Visualizer:** Automatically generates and displays an Entity-Relationship Diagram (ERD) of your database schema using Graphviz.
* **High-Performance Backend:** Built with FastAPI using fully `async` I/O for database and LLM calls, ensuring high throughput.
* **LLM Response Caching:** Uses a local SQLite database to cache responses, providing instantaneous answers to repeated questions and reducing computational load.
* **Local & Private:** Runs entirely on your local machine with **Ollama** and **Llama 3**. No data leaves your system.
* **Fully Containerized:** The entire multi-service platform is defined and orchestrated with Docker Compose for a simple, one-command setup.

---

## 🛠️ Tech Stack

* **Backend:** Python, FastAPI, AsyncPG, AIOSQLite
* **Frontend:** Streamlit, Pandas, Altair
* **Database:** PostgreSQL
* **LLM Serving:** Ollama
* **LLM Model:** Llama 3 (default)
* **Containerization:** Docker & Docker Compose

---

## 🚀 Getting Started

The entire application can be deployed with a single script.

### Prerequisites

* **Docker Desktop:** Ensure you have Docker and Docker Compose installed and running.

### Deployment

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/](https://github.com/)[your-github-username]/AISavvy.git
    cd AISavvy
    ```

2.  **Make the Deployment Script Executable:**
    ```bash
    chmod +x deploy.sh
    ```

3.  **Run the Script:**
    This will build all the images, start the containers, download the Llama 3 model, and print the UI access URL.
    ```bash
    ./deploy.sh
    ```

4.  **Access the Application:**
    Open your web browser and navigate to **`http://localhost:8501`**.

<details>
<summary>Click to see the contents of the deploy.sh script</summary>

```sh
#!/bin/bash
# AISavvy Deployment Script

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "<span class="math-inline">\{YELLOW\}Starting the AISavvy deployment\.\.\.</span>{NC}"

echo -e "\n${YELLOW}[1/3] Building and starting all services...${NC}"
docker-compose up --build -d
if [ <span class="math-inline">? \-ne 0 \]; then
echo \-e "\\n</span>{RED}Error: Docker Compose failed to start services.<span class="math-inline">\{NC\}"
exit 1
fi
echo \-e "</span>{GREEN}✅ Services started successfully!<span class="math-inline">\{NC\}"
echo \-e "\\n</span>{YELLOW}[2/3] Downloading the Llama 3 LLM model...${NC}"
docker-compose exec ollama ollama pull llama3
if [ <span class="math-inline">? \-ne 0 \]; then
echo \-e "\\n</span>{RED}Error: Failed to download the Llama 3 model.<span class="math-inline">\{NC\}"
exit 1
fi
echo \-e "</span>{GREEN}✅ Llama 3 model downloaded successfully!<span class="math-inline">\{NC\}"
echo \-e "\\n</span>{YELLOW}[3/3] Deployment complete!<span class="math-inline">\{NC\}"
echo \-e "\\n</span>{GREEN}=====================================================<span class="math-inline">\{NC\}"
echo \-e "</span>{GREEN}    🚀 Your AISavvy application is ready! 🚀    <span class="math-inline">\{NC\}"
echo \-e "</span>{GREEN}=====================================================<span class="math-inline">\{NC\}"
echo \-e "\\nAccess the web UI at the following URL\:"
echo \-e "</span>{YELLOW}👉 http://localhost:8501 ${NC}\n"
```

</details>

---

## 🖥️ Using the Application

The user interface is a multi-page Streamlit application with a navigation sidebar on the left.

* **AISavvy | Chat:** The main page for your conversational interaction with the database.
* **Query History:** View, search, and export all past queries.
* **Schema Visualizer:** See a live-generated ERD of your database tables.