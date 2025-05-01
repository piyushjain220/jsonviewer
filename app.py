import streamlit as st
import pandas as pd
import json
import io
import base64
from datetime import datetime
import re

# Set page configuration
st.set_page_config(
    page_title="JSON to Table Converter",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main .block-container {
        padding-top: 2rem;
    }
    .stButton button {
        width: 100%;
    }
    .stDownloadButton button {
        width: 100%;
    }
    h1, h2, h3 {
        margin-bottom: 1rem;
    }
    .table-filter {
        padding: 1rem;
        background-color: #f0f2f6;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .stDataFrame {
        margin-top: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# Helper functions for JSON processing
def is_tabular_data(data):
    """Check if the data structure looks like tabular data (list of similar objects)"""
    if not isinstance(data, list) or not data:
        return False
    
    # Check if all items are dictionaries with similar keys
    if all(isinstance(item, dict) for item in data):
        # Get keys from the first item
        first_keys = set(data[0].keys())
        # Check if at least 80% of items have similar keys (allowing some flexibility)
        similar_items = sum(1 for item in data if set(item.keys()).intersection(first_keys))
        return similar_items / len(data) >= 0.8
    
    # Check if all items are lists of similar length (potential table rows)
    if all(isinstance(item, list) for item in data):
        lengths = [len(item) for item in data]
        # If most items have the same length, it's likely tabular
        return lengths.count(lengths[0]) / len(lengths) >= 0.8
    
    return False

def extract_tabular_data(json_obj, path="", results=None):
    """Recursively search for tabular data in the JSON structure"""
    if results is None:
        results = []
    
    if isinstance(json_obj, dict):
        for key, value in json_obj.items():
            new_path = f"{path}.{key}" if path else key
            if is_tabular_data(value):
                results.append((new_path, value))
            extract_tabular_data(value, new_path, results)
    
    elif isinstance(json_obj, list):
        if is_tabular_data(json_obj):
            results.append((path, json_obj))
        else:
            for i, item in enumerate(json_obj):
                new_path = f"{path}[{i}]"
                extract_tabular_data(item, new_path, results)
    
    return results

def json_to_dataframe(json_data):
    """Convert JSON data to pandas DataFrame based on its structure"""
    if isinstance(json_data, list):
        if all(isinstance(item, dict) for item in json_data):
            # List of dictionaries -> each dict becomes a row
            return pd.DataFrame(json_data)
        elif all(isinstance(item, list) for item in json_data):
            # List of lists -> each inner list becomes a row
            # Generate column names
            columns = [f"Column_{i}" for i in range(len(json_data[0]))]
            return pd.DataFrame(json_data, columns=columns)
    
    # For other structures, try to normalize and convert
    return pd.json_normalize(json_data)

def process_json_data(json_str):
    """Process JSON string and return DataFrames of tabular data found"""
    try:
        # Parse the JSON
        data = json.loads(json_str)
        
        # Find all tabular data structures
        tabular_data = extract_tabular_data(data)
        
        if not tabular_data:
            st.warning("No tabular data found in the JSON structure. Attempting to convert the entire JSON.")
            # Try to convert the entire JSON to a DataFrame as a fallback
            try:
                df = pd.json_normalize(data)
                return [("root", df)]
            except Exception as e:
                st.error(f"Could not convert JSON to table: {e}")
                return []
        
        # Convert each tabular structure to a DataFrame
        dataframes = []
        for path, table_data in tabular_data:
            try:
                df = json_to_dataframe(table_data)
                dataframes.append((path, df))
            except Exception as e:
                st.error(f"Error converting data at path '{path}': {e}")
        
        return dataframes
    
    except json.JSONDecodeError as e:
        st.error(f"Invalid JSON: {e}")
        return []
    except Exception as e:
        st.error(f"Error processing JSON: {e}")
        return []

def get_download_link(df, filename):
    """Generate a download link for the dataframe as Excel file"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')
    
    # Create the download link
    b64 = base64.b64encode(output.getvalue()).decode()
    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}">Download Excel file</a>'
    return href

def apply_filters(df, filters):
    """Apply filters to the dataframe"""
    filtered_df = df.copy()
    
    for column, value in filters.items():
        if value:
            if pd.api.types.is_numeric_dtype(filtered_df[column]):
                # For numeric columns, filter by range
                min_val, max_val = value
                filtered_df = filtered_df[(filtered_df[column] >= min_val) & (filtered_df[column] <= max_val)]
            elif pd.api.types.is_string_dtype(filtered_df[column]):
                # For string columns, filter by contains (case-insensitive)
                filtered_df = filtered_df[filtered_df[column].str.contains(value, case=False, na=False)]
            else:
                # For other types, filter by exact match
                filtered_df = filtered_df[filtered_df[column] == value]
    
    return filtered_df

# Main application
def main():
    st.title("JSON to Table Converter")
    st.write("Upload a JSON file or paste JSON text to convert it to a table format.")
    
    # Create tabs for file upload and text input
    tab1, tab2 = st.tabs(["Upload JSON File", "Paste JSON Text"])
    
    with tab1:
        uploaded_file = st.file_uploader("Choose a JSON file", type=["json"])
        if uploaded_file is not None:
            # Read the file
            json_str = uploaded_file.getvalue().decode("utf-8")
            st.session_state.json_data = json_str
            st.session_state.source = "file"
    
    with tab2:
        json_text = st.text_area("Paste your JSON data here", height=200)
        if st.button("Process JSON Text"):
            if json_text:
                st.session_state.json_data = json_text
                st.session_state.source = "text"
            else:
                st.warning("Please paste some JSON data.")
    
    # Process the JSON data if available
    if 'json_data' in st.session_state:
        json_str = st.session_state.json_data
        source = st.session_state.source
        
        # Process the JSON
        dataframes = process_json_data(json_str)
        
        if dataframes:
            # Create a selectbox to choose which table to display if multiple tables are found
            if len(dataframes) > 1:
                st.write(f"Found {len(dataframes)} tables in the JSON data.")
                table_options = [f"Table at {path} ({df.shape[0]} rows × {df.shape[1]} columns)" for path, df in dataframes]
                selected_table = st.selectbox("Select a table to view:", table_options)
                selected_index = table_options.index(selected_table)
                path, df = dataframes[selected_index]
            else:
                path, df = dataframes[0]
                st.write(f"Found table at path: {path}")
            
            # Display table info
            st.write(f"Table dimensions: {df.shape[0]} rows × {df.shape[1]} columns")
            
            # Create filters
            st.subheader("Filter Data")
            with st.expander("Show/Hide Filters", expanded=False):
                filters = {}
                cols = st.columns(3)
                
                for i, column in enumerate(df.columns):
                    col_idx = i % 3
                    with cols[col_idx]:
                        if pd.api.types.is_numeric_dtype(df[column]):
                            # For numeric columns, create a range slider
                            min_val = float(df[column].min())
                            max_val = float(df[column].max())
                            if min_val != max_val:
                                filters[column] = st.slider(
                                    f"Filter by {column}",
                                    min_value=min_val,
                                    max_value=max_val,
                                    value=(min_val, max_val)
                                )
                            else:
                                st.write(f"{column}: All values are {min_val}")
                        elif pd.api.types.is_string_dtype(df[column]):
                            # For string columns, create a text input
                            filters[column] = st.text_input(f"Filter by {column} (contains)")
                        else:
                            # For other types, create a selectbox with unique values
                            unique_values = df[column].unique().tolist()
                            if len(unique_values) < 10:  # Only show selectbox if there are few unique values
                                filters[column] = st.selectbox(
                                    f"Filter by {column}",
                                    options=[""] + unique_values
                                )
            
            # Apply filters
            filtered_df = apply_filters(df, filters)
            
            # Display the filtered dataframe
            st.subheader("Data Preview")
            st.dataframe(filtered_df, use_container_width=True)
            
            # Export options
            st.subheader("Export Options")
            col1, col2 = st.columns(2)
            
            with col1:
                # Generate timestamp for filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"json_data_{timestamp}.xlsx"
                
                # Create Excel download button
                excel_data = io.BytesIO()
                with pd.ExcelWriter(excel_data, engine='xlsxwriter') as writer:
                    filtered_df.to_excel(writer, sheet_name='Data', index=False)
                
                st.download_button(
                    label="Download as Excel",
                    data=excel_data.getvalue(),
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with col2:
                # Create CSV download button
                csv_data = filtered_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download as CSV",
                    data=csv_data,
                    file_name=f"json_data_{timestamp}.csv",
                    mime="text/csv"
                )
            
            # Show JSON structure
            with st.expander("JSON Structure", expanded=False):
                st.code(json.dumps(json.loads(json_str), indent=2)[:10000] + 
                       ("..." if len(json_str) > 10000 else ""))
        else:
            st.error("Could not extract any tabular data from the JSON. Please check the format.")

# Run the application
if __name__ == "__main__":
    main()