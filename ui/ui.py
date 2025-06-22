import streamlit as st
import requests
import pandas as pd
import json

# --- Page Configuration ---
st.set_page_config(
    page_title="SQLingua",
    page_icon="🗣️",
    layout="wide"
)

# --- App Title and Description ---
st.title("SQLingua 🗣️↔️🐘")
st.markdown("Talk to your PostgreSQL database in plain English. Powered by Gemma, Ollama, and Docker.")
st.markdown("---")

# --- Configuration ---
# The API endpoint is the name of the 'app' service in docker-compose, on port 8000
API_URL = "http://app:8000/query"

# --- UI Elements ---
st.sidebar.header("About")
st.sidebar.info(
    "This application uses a local Gemma LLM to convert your natural language "
    "questions into SQL queries and executes them against a PostgreSQL database."
)
st.sidebar.header("Example Questions")
st.sidebar.markdown("""
- *Who is the manager of the Sales department?*
- *How many employees are in the Engineering department?*
- *List all employees hired after 2022.*
- *What is the average salary in the Sales department?*
""")


# --- Main Application Logic ---
# Use a form for the input to prevent rerunning the app on every keystroke
with st.form(key='query_form'):
    question = st.text_input("Enter your question about the database:", placeholder="e.g., Who is the highest-paid employee?")
    submit_button = st.form_submit_button(label='▶️ Ask SQLingua')

# Handle form submission
if submit_button and question:
    with st.spinner("🧠 SQLingua is thinking..."):
        try:
            # Call the backend API
            payload = {"question": question}
            response = requests.post(API_URL, json=payload)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

            data = response.json()

            st.markdown("---")
            st.subheader("💡 Result")

            # Display the result
            if 'result' in data and data['result']:
                # If the result is a list of dictionaries, display as a table
                if isinstance(data['result'], list) and all(isinstance(i, dict) for i in data['result']):
                    df = pd.DataFrame(data['result'])
                    st.dataframe(df, use_container_width=True)
                # Otherwise, display the raw JSON
                else:
                    st.json(data['result'])
            else:
                st.info("The query executed successfully but returned no results.")

            # Expander to show the technical details
            with st.expander("Show Technical Details"):
                st.write("**Your Question:**")
                st.code(data.get('question', ''), language='text')
                st.write("**Generated SQL Query:**")
                st.code(data.get('sql_query', ''), language='sql')

        except requests.exceptions.RequestException as e:
            st.error(f"Connection Error: Could not connect to the API. Is the 'app' service running? \n\nDetails: {e}")
        except Exception as e:
            st.error(f"An error occurred: {e}")
elif submit_button:
    st.warning("Please enter a question.")