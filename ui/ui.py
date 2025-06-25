import streamlit as st
import requests
import pandas as pd
import json

# --- Page Configuration ---
st.set_page_config(
    page_title="AISavvy.py",
    page_icon="🗣️",
    layout="wide"
)

# --- App Title ---
st.title("AISavvy.py 🗣️↔️🐘")
st.markdown("A conversational assistant for your PostgreSQL database.")
st.markdown("---")

# --- Initialize Session State ---
# This will store the conversation history
if 'history' not in st.session_state:
    st.session_state.history = []

# --- Helper function to call the backend ---
def get_ai_response(history):
    API_URL = "http://app:8000/query"
    try:
        response = requests.post(API_URL, json={"history": history})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        try:
            return {"error": e.response.json().get('detail', e.response.text)}
        except json.JSONDecodeError:
            return {"error": f"API Error: {e.response.status_code} {e.response.reason}."}
    except requests.exceptions.RequestException as e:
        return {"error": f"Connection Error: Could not connect to the API. Details: {e}"}

# --- Display Chat History ---
# Loop through the history and display each message
for turn in st.session_state.history:
    role = turn["role"]
    with st.chat_message(name=role, avatar="🧑‍💻" if role == "user" else "🤖"):
        # The user's message is just text
        if role == "user":
            st.markdown(turn["content"])
        # The assistant's message contains the result and the SQL query
        else:
            result = turn.get("result")
            sql_query = turn.get("sql_query")
            
            if result:
                if isinstance(result, list) and all(isinstance(i, dict) for i in result):
                    df = pd.DataFrame(result)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.json(result)
            else:
                st.info("The query executed successfully but returned no results.")

            with st.expander("Show Generated SQL Query"):
                st.code(sql_query, language='sql')


# --- Chat Input ---
# The text input for the user's question
prompt = st.chat_input("Ask a question about your database...")

if prompt:
    # 1. Add user's question to history and display it
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(prompt)

    # 2. Get AI response and display it
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("🧠 Gemma is thinking..."):
            # The payload now contains the full history
            response_data = get_ai_response(st.session_state.history)

            if "error" in response_data:
                st.error(response_data["error"])
                # Add the error to history so it's displayed
                st.session_state.history.append({"role": "assistant", "content": response_data["error"]})
            else:
                result = response_data.get("result")
                sql_query = response_data.get("sql_query")

                if result:
                    if isinstance(result, list) and all(isinstance(i, dict) for i in result):
                        df = pd.DataFrame(result)
                        st.dataframe(df, use_container_width=True)
                    else:
                        st.json(result)
                else:
                    st.info("The query executed successfully but returned no results.")
                
                with st.expander("Show Generated SQL Query"):
                    st.code(sql_query, language='sql')

                # 3. Add AI's full response to history for context in the next turn
                # For the LLM's context, we only need to pass the generated SQL
                st.session_state.history.append({"role": "assistant", "content": sql_query})