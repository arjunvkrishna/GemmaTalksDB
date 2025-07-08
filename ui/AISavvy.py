import streamlit as st
import requests
import pandas as pd
import json
import altair as alt
from fpdf import FPDF
from io import BytesIO

# --- Page Configuration ---
st.set_page_config(page_title="AISavvy | Chat", page_icon="🧠", layout="wide")

st.title("AISavvy 🧠↔️📊")
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
        # Ensure header is a string before passing to get_string_width
        width = pdf.get_string_width(str(header)) + 8 # Add padding
        column_widths.append(width)

    # Adjust column widths to ensure they don't exceed page width and are somewhat balanced
    # This is a basic adjustment; for complex tables, more sophisticated logic might be needed
    page_width = pdf.w - 2 * pdf.l_margin
    total_calculated_width = sum(column_widths)
    
    if total_calculated_width > page_width:
        # Scale down widths proportionally if they exceed page width
        scale_factor = page_width / total_calculated_width
        column_widths = [w * scale_factor for w in column_widths]
    else:
        # Distribute remaining space if total width is less than page width
        remaining_space = page_width - total_calculated_width
        if len(column_widths) > 0:
            space_per_column = remaining_space / len(column_widths)
            column_widths = [w + space_per_column for w in column_widths]


    for i, header in enumerate(df.columns):
        pdf.cell(column_widths[i], 10, header, 1, 0, "C")
    pdf.ln()

    # Table Rows
    pdf.set_font("Helvetica", "", 8)
    for _, row in df.iterrows():
        for i, item in enumerate(row):
            # Ensure item is a string and handle potential encoding issues
            cell_text = str(item)
            try:
                # Attempt to encode to latin-1, which FPDF uses by default
                cell_text.encode('latin-1')
            except UnicodeEncodeError:
                # Replace unsupported characters if encoding fails
                cell_text = cell_text.encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(column_widths[i], 10, cell_text, 1, 0)
        pdf.ln()
        
    # Convert bytearray to bytes before returning
    return bytes(pdf.output())


# --- Initialize session state for chat history ---
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

# --- Display Chat History ---
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
                            
                            # Add checks for x_col and y_col before creating the chart
                            if x_col is None or y_col is None:
                                st.warning(f"Could not generate chart: Missing 'x_column' or 'y_column' in chart specification. Received x_col: {x_col}, y_col: {y_col}")
                            else:
                                if chart_type == "bar":
                                    chart = alt.Chart(df).mark_bar().encode(x=alt.X(x_col, sort=None), y=y_col)
                                elif chart_type == "line":
                                    chart = alt.Chart(df).mark_line().encode(x=x_col, y=y_col)
                                elif chart_type == "pie":
                                    chart = alt.Chart(df).mark_arc().encode(theta=alt.Theta(field=y_col, type="quantitative"), color=alt.Color(field=x_col, type="nominal"))
                                st.altair_chart(chart, use_container_width=True)
                        except Exception as e:
                            st.warning(f"Could not generate chart: {e}")
                
                with st.expander("Show Technical Details"):
                    st.code(sql_query, language='sql')

# --- Handle User Input ---
prompt = st.chat_input("Ask a question about your database...")
if prompt:
    # Add user message to history and immediately get the AI response
    st.session_state.history.append({"role": "user", "content": prompt})
    
    with st.spinner("🧠 AISavvy is thinking..."):
        response_data = get_ai_response(st.session_state.history)
        st.session_state.history.append({"role": "assistant", "content": response_data})
    
    # Rerun the script to display the new messages immediately
    st.rerun()
