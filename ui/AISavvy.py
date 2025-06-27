import streamlit as st
import requests
import pandas as pd
import json
import altair as alt
import os
from streamlit_mic_recorder import mic_recorder

st.set_page_config(page_title="AISavvy | Chat", page_icon="🧠", layout="wide")

st.title("AISavvy 🧠↔️📊")
st.markdown("Your intelligent, conversational database assistant. Now with voice!")

# --- Configuration ---
API_URL = "http://app:8000/query"
STT_API_URL = os.getenv("STT_API_URL", "http://localhost:8080/inference") # Fallback for local dev

# Initialize session state
if 'history' not in st.session_state:
    st.session_state.history = []
if 'last_prompt' not in st.session_state:
    st.session_state.last_prompt = None

def process_prompt(prompt_text):
    """Adds a prompt to history and triggers a rerun."""
    if prompt_text:
        st.session_state.last_prompt = prompt_text
        st.session_state.history.append({"role": "user", "content": prompt_text})
        st.rerun()

# --- Display Chat History ---
# ... (The display logic from the previous step is unchanged) ...
for turn in st.session_state.history:
    role = turn["role"]
    with st.chat_message(name=role, avatar="🧑‍💻" if role == "user" else "🤖"):
        # ... (Same display logic as before)
        # ... (This section is long so it's omitted for brevity, but it should be here)
        content = turn["content"]
        if role == "user":
            st.markdown(content)
        else: # Assistant's turn
            response_data = content
            result = response_data.get("result")
            sql_query = response_data.get("sql_query")
            chart_spec = response_data.get("chart_spec")
            error_info = response_data.get("error")
            if error_info:
                # ... display error ...
                st.error(f"Database Error: {error_info.get('error')}")
                if "suggested_fix" in error_info:
                    st.warning("🤖 AI Suggested Fix:")
                    st.code(error_info["suggested_fix"], language="sql")
            else:
                # ... display results and charts ...
                if result:
                    df = pd.DataFrame(result)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("Query executed successfully, but returned no data.")
                if chart_spec and chart_spec.get("chart_needed") and result:
                    # ... chart generation logic ...
                    pass
                with st.expander("Show Technical Details"):
                    st.code(sql_query, language='sql')


# --- Chat Input Area ---
st.markdown("---")
# Text input
text_prompt = st.chat_input("Type or use the microphone to ask a question...")
if text_prompt:
    process_prompt(text_prompt)

# Voice input
st.write("Or, ask with your voice:")
audio_info = mic_recorder(
    start_prompt="🔴 Record",
    stop_prompt="⏹️ Stop",
    just_once=True,
    key='voice_input'
)
if audio_info and audio_info['bytes']:
    st.info("Transcribing audio...")
    # Send audio bytes to STT service
    files = {'file': ('audio.wav', audio_info['bytes'], 'audio/wav')}
    try:
        stt_response = requests.post(STT_API_URL, files=files)
        stt_response.raise_for_status()
        transcribed_text = stt_response.json().get('text', '').strip()
        st.success(f"Transcribed: \"{transcribed_text}\"")
        process_prompt(transcribed_text)
    except Exception as e:
        st.error(f"Audio transcription failed: {e}")


# --- AI Response Logic ---
if st.session_state.last_prompt and st.session_state.history and st.session_state.history[-1]["role"] == "user":
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("🧠 AISavvy is thinking..."):
            # The logic to call the API and handle the response is the same as the last step
            # ...
            # ... This section is long so it's omitted for brevity, but it should be here
            API_URL_CHAT = "http://app:8000/query"
            payload = {"history": st.session_state.history}
            response = requests.post(API_URL_CHAT, json=payload)
            # ... process response and add to history ...
            response_data = response.json() # Simplified for brevity
            st.session_state.history.append({"role": "assistant", "content": response_data})
            st.session_state.last_prompt = None # Reset the prompt to prevent re-running
            st.rerun()