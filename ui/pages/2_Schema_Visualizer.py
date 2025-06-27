import streamlit as st
import requests

st.set_page_config(page_title="Schema Visualizer", page_icon="🗺️", layout="wide")

st.title("🗺️ Database Schema Visualizer")
st.markdown("An auto-generated Entity-Relationship Diagram (ERD) of the connected database.")

API_URL = "http://app:8000/schema/erd"

try:
    response = requests.get(API_URL)
    response.raise_for_status()
    data = response.json()
    dot_string = data.get("dot_string")

    if dot_string:
        st.graphviz_chart(dot_string)
    else:
        st.warning("Could not generate ERD string from the API.")

except Exception as e:
    st.error(f"Could not load schema visualization: {e}")