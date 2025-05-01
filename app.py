import streamlit as st
import pandas as pd
import json
import io
from datetime import datetime
import numpy as np

# Set page configuration
st.set_page_config(
    page_title="JSON Table Viewer",
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

def extract_values_data(json_data):
    """Extract tabular data from the 'values' array in the JSON structure"""
    try:
        # Try to find the values array using common patterns
        if isinstance(json_data, dict):
            # Pattern 1: regions > fetchedData > values
            if 'regions' in json_data and isinstance(json_data['regions'], list):
                for region in json_data['regions']:
                    if isinstance(region, dict) and 'fetchedData' in region:
                        if 'values' in region['fetchedData']:
                            return region['fetchedData']['values']
            
            # Pattern 2: direct values array
            if 'values' in json_data:
                return json_data['values']
            
            # Pattern 3: fetchedData > values
            if 'fetchedData' in json_data and 'values' in json_data['fetchedData']:
                return json_data['fetchedData']['values']
            
            # Pattern 4: data > values
            if 'data' in json_data and 'values' in json_data['data']:
                return json_data['data']['values']
            
            # Pattern 5: recursive search for 'values' key
            for key, value in json_data.items():
                if key == 'values' and isinstance(value, list):
                    return value
                if isinstance(value, dict):
                    result = extract_values_data(value)
                    if result:
                        return result
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            result = extract_values_data(item)
                            if result:
                                return result
        
        return None
    except Exception as e:
        st.error(f"Error extracting values data: {e}")
        return None

def process_values_array(values_array):
    """Process the values array into a DataFrame with appropriate columns"""
    if not values_array or not isinstance(values_array, list):
        return None
    
    try:
        # Check if the values array contains rows of data
        if all(isinstance(row, list) for row in values_array):
            # Determine the number of columns (use the most common length)
            row_lengths = [len(row) for row in values_array]
            most_common_length = max(set(row_lengths), key=row_lengths.count)
            
            # Filter rows to include only those with the most common length
            valid_rows = [row for row in values_array if len(row) == most_common_length]
            
            # Generate column names based on the data pattern
            # For this specific JSON structure, we know the pattern
            column_names = [
                "Company Name", "ID", "Status1", "Date1", 
                "Status2", "Date2", "Status3", "Date3", 
                "Status4", "Date4"
            ]
            
            # If we have more or fewer columns than expected, adjust the column names
            if most_common_length > len(column_names) + 1:  # +1 for the metadata object
                column_names.extend([f"Column_{i}" for i in range(len(column_names), most_common_length-1)])
            elif most_common_length < len(column_names) + 1:
                column_names = column_names[:most_common_length-1]
            
            # Process each row to handle the metadata object at the end
            processed_rows = []
            for row in valid_rows:
                # Check if the last item is a dict (metadata)
                if isinstance(row[-1], dict):
                    # Extract the row without the metadata
                    processed_row = row[:-1]
                else:
                    processed_row = row
                
                # Ensure the row has the correct length
                if len(processed_row) < len(column_names):
                    # Pad with empty strings if needed
                    processed_row.extend([""] * (len(column_names) - len(processed_row)))
                elif len(processed_row) > len(column_names):
                    # Truncate if too long
                    processed_row = processed_row[:len(column_names)]
                
                processed_rows.append(processed_row)
            
            # Create DataFrame
            df = pd.DataFrame(processed_rows, columns=column_names)
            return df
        
        return None
    except Exception as e:
        st.error(f"Error processing values array: {e}")
        return None

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

def is_filterable_column(df, column):
    """Check if a column can be filtered (has hashable values)"""
    try:
        # Check if we can get unique values
        if df[column].isna().all():
            return False
        
        # Check for complex types that might cause issues
        sample = df[column].dropna().iloc[0] if not df[column].isna().all() else None
        if sample is not None and isinstance(sample, (dict, list)):
            return False
        
        # Try to get unique values (this will fail for unhashable types)
        _ = df[column].dropna().unique()
        return True
    except:
        return False

# Main application
def main():
    st.title("JSON Table Viewer")
    st.write("Upload a JSON file or paste JSON text to view the tabular data.")
    
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
        
        try:
            # Parse the JSON
            json_data = json.loads(json_str)
            
            # Extract the values array
            values_array = extract_values_data(json_data)
            
            if values_array:
                # Process the values array into a DataFrame
                df = process_values_array(values_array)
                
                if df is not None and not df.empty:
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
                                # Check if column can be filtered
                                if is_filterable_column(df, column):
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
                                        # For other types, try to create a selectbox with unique values
                                        try:
                                            # Get unique values, handling NaN values
                                            unique_values = df[column].dropna().unique().tolist()
                                            if len(unique_values) < 10:  # Only show selectbox if there are few unique values
                                                filters[column] = st.selectbox(
                                                    f"Filter by {column}",
                                                    options=[""] + unique_values
                                                )
                                        except:
                                            st.write(f"{column}: Cannot filter (complex data type)")
                                else:
                                    st.write(f"{column}: Cannot filter (complex data type)")
                    
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
                        filename = f"table_data_{timestamp}.xlsx"
                        
                        # Create Excel download button
                        try:
                            excel_data = io.BytesIO()
                            with pd.ExcelWriter(excel_data, engine='xlsxwriter') as writer:
                                filtered_df.to_excel(writer, sheet_name='Data', index=False)
                            
                            st.download_button(
                                label="Download as Excel",
                                data=excel_data.getvalue(),
                                file_name=filename,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        except Exception as e:
                            st.error(f"Error creating Excel file: {e}")
                            st.info("Try downloading as CSV instead.")
                    
                    with col2:
                        # Create CSV download button
                        try:
                            csv_data = filtered_df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label="Download as CSV",
                                data=csv_data,
                                file_name=f"table_data_{timestamp}.csv",
                                mime="text/csv"
                            )
                        except Exception as e:
                            st.error(f"Error creating CSV file: {e}")
                else:
                    st.error("Could not process the values array into a table.")
            else:
                st.error("Could not find a 'values' array in the JSON structure.")
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")
        except Exception as e:
            st.error(f"Error processing JSON: {e}")

# Run the application
if __name__ == "__main__":
    main()
