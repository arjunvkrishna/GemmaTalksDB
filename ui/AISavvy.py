import streamlit as st
import requests
import pandas as pd
import json
import altair as alt

st.set_page_config(page_title="AISavvy | Chat", page_icon="🧠", layout="wide")
st.title("AISavvy 🧠↔️📊")
st.markdown("Your intelligent, conversational database assistant.")

if 'history' not in st.session_state:
    st.session_state.history = []

# ... (get_ai_response function is unchanged)

# Display chat history
for turn in st.session_state.history:
    role = turn["role"]
    with st.chat_message(name=role, avatar="🧑‍💻" if role == "user" else "🤖"):
        content = turn["content"]
        if role == "user":
            st.markdown(content)
        else: # Assistant's turn
            response_data = content
            
            # --- NEW: Handle all new response types ---
            if "off_topic" in response_data:
                st.warning(response_data["off_topic"])
            elif "clarification" in response_data:
                st.info(f'🤔 {response_data["clarification"]}')
            elif "no_results_explanation" in response_data:
                st.info(f'✅ {response_data["no_results_explanation"]}')
            elif "error" in response_data:
                # ... (error handling)
            else:
                # ... (standard result display with tables, charts, explanations)
                explanation = response_data.get("explanation")
                if explanation and explanation != "Could not generate explanation.":
                    st.success(f"💡 **Explanation:** {explanation}")
                
                result = response_data.get("result")
                df = pd.DataFrame(result)
                st.dataframe(df, use_container_width=True)
                # ... chart logic ...
                with st.expander("Show Technical Details"):
                    st.code(response_data.get("sql_query"), language='sql')

# ... (Chat input and API call logic is unchanged)