import streamlit as st
import requests
import pandas as pd
import json
import altair as alt
from fpdf import FPDF
from io import BytesIO

st.set_page_config(page_title="AISavvy | Chat", page_icon="🧠", layout="wide")

st.title("AISavvy 🧠↔️📊")
st.markdown("Your intelligent, conversational database assistant.")

# --- NEW: Helper function to generate a PDF from a DataFrame ---
def create_pdf(df: pd.DataFrame) -> bytes:
    """Creates a PDF file from a Pandas DataFrame and returns its content as bytes."""
    pdf = FPDF(orientation="L") # Landscape orientation for wider tables
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "AISavvy Query Result", 0, 1, "C")
    
    pdf.set_font("Helvetica", "B", 10)
    
    # Table Header
    column_widths = []
    for header in df.columns:
        # Simple width calculation - can be improved
        width = pdf.get_string_width(header) + 6
        column_widths.append(width)

    for i, header in enumerate(df.columns):
        pdf.cell(column_widths[i], 10, header, 1, 0, "C")
    pdf.ln()

    # Table Rows
    pdf.set_font("Helvetica", "", 10)
    for _, row in df.iterrows():
        for i, item in enumerate(row):
            pdf.cell(column_widths[i], 10, str(item), 1, 0)
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1')


# Initialize session state for chat history
if 'history' not in st.session_state:
    st.session_state.history = []

def get_ai_response(history):
    API_URL = "http://app:8000/query"
    try:
        response = requests.post(API_URL, json={"history": history})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        return {"error_data": e.response.json()}
    except requests.exceptions.RequestException as e:
        return {"error": f"Connection Error: {e}"}

# Display chat history
for i, turn in enumerate(st.session_state.history):
    role = turn["role"]
    with st.chat_message(name=role, avatar="🧑‍💻" if role == "user" else "🤖"):
        content = turn["content"]
        if role == "user":
            st.markdown(content)
        else: # Assistant's turn
            response_data = content
            
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
                st.warning(response_data["off_topic"])
            else:
                explanation = response_data.get("explanation")
                if explanation and explanation != "Could not generate explanation.":
                    st.success(f"💡 **Explanation:** {explanation}")
                
                result = response_data.get("result")
                sql_query = response_data.get("sql_query")
                chart_spec = response_data.get("chart_spec")

                if result:
                    df = pd.DataFrame(result)
                    st.dataframe(df, use_container_width=True)

                    # --- NEW: Add the PDF download button ---
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
                else:
                    st.info("Query executed successfully, but returned no data.")
                
                with st.expander("Show Technical Details"):
                    st.code(sql_query, language='sql')

# Handle user input
prompt = st.chat_input("Ask a question about your database...")
if prompt:
    st.session_state.history.append({"role": "user", "content": prompt})
    
    # Get AI response immediately and add it to history
    with st.spinner("🧠 AISavvy is thinking..."):
        response_data = get_ai_response(st.session_state.history)
        st.session_state.history.append({"role": "assistant", "content": response_data})
    
    st.rerun()
