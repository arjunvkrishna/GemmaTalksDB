import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Query History", page_icon="📜", layout="wide")

st.title("📜 Query History")
st.markdown("A log of all questions and generated queries for the current session and past sessions.")

API_URL = "http://app:8000/history"

try:
    response = requests.get(API_URL)
    response.raise_for_status()
    history_data = response.json()

    if history_data:
        df = pd.DataFrame(history_data)
        # Format dataframe for display
        df['success'] = df['success'].apply(lambda x: '✅ Yes' if x else '❌ No')
        df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
        st.dataframe(df, use_container_width=True)

        st.markdown("---")
        st.subheader("📥 Export History")
        
        col1, col2 = st.columns(2)

        # Export as CSV
        csv_data = df.to_csv(index=False).encode('utf-8')
        col1.download_button(
            label="Export as CSV",
            data=csv_data,
            file_name='query_history.csv',
            mime='text/csv',
        )

        # Export as SQL
        sql_data = "\n\n".join([f"-- Question: {row['question']}\n{row['sql_query']};" for index, row in df.iterrows()])
        col2.download_button(
            label="Export as SQL",
            data=sql_data.encode('utf-8'),
            file_name='query_history.sql',
            mime='text/plain',
        )
    else:
        st.info("No query history found yet. Ask some questions in the Chat!")

except Exception as e:
    st.error(f"Could not load query history: {e}")