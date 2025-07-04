import streamlit as st
import requests
import pandas as pd
import json
import altair as alt
from fpdf import FPDF
from io import BytesIO

st.set_page_config(page_title="AISavvy | Chat", page_icon="🧠", layout="wide")

st.title("AISavvy ↔️📊")
st.markdown("Your intelligent, conversational database assistant.")

# --- Helper function to generate a PDF from a DataFrame ---
def create_pdf(df: pd.DataFrame) -> bytes:
    """Creates a PDF file from a Pandas DataFrame and returns its content as bytes."""
    pdf = FPDF(orientation="L") # Landscape orientation for wider tables
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "AISavvy Query Result", 0, 1, "C")
    
    pdf.set_font("Helvetica", "B", 8)
    
    # Table Header
    column_widths = []
    for header in df.columns:
        # A simple width calculation for PDF columns
        width = pdf.get_string_width(str(header)) + 6 # Add padding
        column_widths.append(width)

    for i, header in enumerate(df.columns):
        pdf.cell(column_widths[i], 10, header, 1, 0, "C")
    pdf.ln()

    # Table Rows
    pdf.set_font("Helvetica", "", 8)
    for _, row in df.iterrows():
        for i, item in enumerate(row):
            pdf.cell(column_widths[i], 10, str(item), 1, 0)
        pdf.ln()
        
    # --- FIXED: Use the modern, direct method to get the PDF content as bytes ---
    return pdf.output()


# Initialize session state for chat history
if 'history' not in st.session_state:
    st.session_state.history = []

def get_ai_response(history):
    """Calls the backend API and returns the JSON response."""
    API_URL = "http://app:8000/query"
    try:
        response = requests.post(API_URL, json={"history": history})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        try:
            return {"error_data": e.response.json()}
        except json.JSONDecodeError:
            return {"error": f"API Error: {e.response.status_code} - {e.response.text}"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Connection Error: Could not connect to the API. Details: {e}"}

# Display chat history
for i, turn in enumerate(st.session_state.history):
    role = turn["role"]
    with st.chat_message(name=role, avatar="🧑‍💻" if role == "user" else "🤖"):
        content = turn["content"]
        if role == "user":
            st.markdown(content)
        else: # Assistant's turn
            response_data = content
            
            # Handle all possible response types from the API
            if "clarification" in response_data:
                st.info(f'🤔 {response_data["clarification"]}')
            elif "no_results_explanation" in response_data:
                st.info(f'✅ {response_data["no_results_explanation"]}')
            elif "error_data" in response_data:
                error_info = response_data["error_data"].get("detail", {})
                st.error(f"Database Error: {error_info.get('error')}")
                if "suggested_fix" in error_info:
                    st.warning("🤖 AI Suggested Fix:")
                    st.code(error_info["suggested_fix"], language="sql")
            elif "off_topic" in response_data:
                st.warning(f'🤖 {response_data["off_topic"]}')
            elif "error" in response_data:
                st.error(response_data["error"])
            else:
                # --- This is the successful response block ---
                summary = response_data.get("summary")
                if summary:
                    st.markdown(f"**💡 Summary:** {summary}")
                
                result = response_data.get("result")
                sql_query = response_data.get("sql_query")
                chart_spec = response_data.get("chart_spec")

                if result:
                    st.markdown("---")
                    st.write("#### Data Result")
                    df = pd.DataFrame(result)
                    st.dataframe(df, use_container_width=True)

                    # Add the PDF download button
                    pdf_bytes = create_pdf(df)
                    st.download_button(
                        label="Download as PDF",
                        data=pdf_bytes,
                        file_name=f"aisavvy_result_{i}.pdf",
                        mime="application/pdf"
                    )

                    if chart_spec and chart_spec.get("chart_needed"):
                        try:
                            st.subheader("📊 Visualization")
                            chart_type = chart_spec.get("chart_type")
                            x_col = chart_spec.get("x_column")
                            y_col = chart_spec.get("y_column")
                            
                            if chart_type == "bar":
                                chart = alt.Chart(df).mark_bar().encode(x=alt.X(x_col, sort=None), y=y_col)
                            elif chart_type == "line":
                                chart = alt.Chart(df).mark_line().encode(x=x_col, y=y_col)
                            elif chart_type == "pie":
                                chart = alt.Chart(df).mark_arc().encode(theta=y_col, color=x_col)
                            st.altair_chart(chart, use_container_width=True)
                        except Exception as e:
                            st.warning(f"Could not generate chart: {e}")
                
                with st.expander("Show Technical Details"):
                    st.code(sql_query, language='sql')

# Handle user input
prompt = st.chat_input("Ask a question about your database...")
if prompt:
    st.session_state.history.append({"role": "user", "content": prompt})
    
    with st.spinner("🧠 AISavvy is thinking..."):
        response_data = get_ai_response(st.session_state.history)
        st.session_state.history.append({"role": "assistant", "content": response_data})
    
    st.rerun()
