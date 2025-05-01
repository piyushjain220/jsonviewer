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
css_style = """
       <style>
       #MainMenu {visibility: hidden; }
       header {visibility: hidden;}
       footer {visibility: hidden;}
       .st-emotion-cache-1ibsh2c {
            padding-top:0px;
       }
       
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
       """
st.markdown(css_style, unsafe_allow_html=True)

MAX_JSON_INPUTS = 20

# --- Auto Detection Logic ---
def find_repeating_list_key(obj, min_repeats=3, path=''):
    if isinstance(obj, dict):
        list_key_counts = {}
        for key, value in obj.items():
            if isinstance(value, list) and len(value) > 0 and all(isinstance(v, (dict, list)) for v in value):
                list_key_counts[key] = list_key_counts.get(key, 0) + 1

        for key, count in list_key_counts.items():
            if count >= min_repeats:
                return f"{path}.{key}" if path else key

        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            found = find_repeating_list_key(value, min_repeats, new_path)
            if found:
                return found

    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            new_path = f"{path}[{idx}]"
            found = find_repeating_list_key(item, min_repeats, new_path)
            if found:
                return found

    return None

def get_value_by_path(obj, path):
    try:
        for key in path.split('.'):
            if '[' in key and ']' in key:
                base, idx = key.split('[')
                idx = int(idx[:-1])
                obj = obj[base][idx]
            else:
                obj = obj[key]
        return obj
    except Exception:
        return None

def extract_table_data_auto(json_data):
    # Step 1: Try known paths
    known_values = extract_values_data(json_data)
    if known_values:
        return known_values

    # Step 2: Check for top-level list of dicts
    if isinstance(json_data, dict):
        for key, value in json_data.items():
            if isinstance(value, list) and len(value) > 3 and all(isinstance(i, dict) for i in value):
                return value

    # Step 3: Use recursive heuristic search
    candidate_path = find_repeating_list_key(json_data, min_repeats=3)
    if candidate_path:
        return get_value_by_path(json_data, candidate_path)

    return None


# --- Existing functions ---
def extract_values_data(json_data):
    try:
        if isinstance(json_data, dict):
            if 'regions' in json_data and isinstance(json_data['regions'], list):
                for region in json_data['regions']:
                    if isinstance(region, dict) and 'fetchedData' in region:
                        if 'values' in region['fetchedData']:
                            return region['fetchedData']['values']
            if 'values' in json_data:
                return json_data['values']
            if 'fetchedData' in json_data and 'values' in json_data['fetchedData']:
                return json_data['fetchedData']['values']
            if 'data' in json_data and 'values' in json_data['data']:
                return json_data['data']['values']
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
    if not values_array or not isinstance(values_array, list):
        return None

    try:
        # If list of dicts: use pandas json normalization
        if all(isinstance(row, dict) for row in values_array):
            return pd.json_normalize(values_array)

        # If list of lists: existing logic
        if all(isinstance(row, list) for row in values_array):
            row_lengths = [len(row) for row in values_array]
            most_common_length = max(set(row_lengths), key=row_lengths.count)
            valid_rows = [row for row in values_array if len(row) == most_common_length]
            column_names = [f"Column_{i+1}" for i in range(most_common_length)]
            return pd.DataFrame(valid_rows, columns=column_names)

        return None
    except Exception as e:
        st.error(f"Error processing values array: {e}")
        return None


def apply_filters(df, filters):
    filtered_df = df.copy()
    for column, value in filters.items():
        if value:
            if pd.api.types.is_numeric_dtype(filtered_df[column]):
                min_val, max_val = value
                filtered_df = filtered_df[(filtered_df[column] >= min_val) & (filtered_df[column] <= max_val)]
            elif pd.api.types.is_string_dtype(filtered_df[column]):
                filtered_df = filtered_df[filtered_df[column].str.contains(value, case=False, na=False)]
            else:
                filtered_df = filtered_df[filtered_df[column] == value]
    return filtered_df

def is_filterable_column(df, column):
    try:
        if df[column].isna().all():
            return False
        sample = df[column].dropna().iloc[0] if not df[column].isna().all() else None
        if sample is not None and isinstance(sample, (dict, list)):
            return False
        _ = df[column].dropna().unique()
        return True
    except:
        return False

# --- Main App ---
def main():
    st.title("JSON Table Viewer")
    st.write("Upload a JSON file or paste JSON text to view the tabular data.")

    tab1, tab2, tab3 = st.tabs(["Upload JSON File", "Paste JSON Text", "Merge Multiple JSON Chunks"])

    with tab1:
        uploaded_file = st.file_uploader("Choose a JSON file", type=["json"])
        df = None  # define early

        if uploaded_file is not None:
            try:
                json_str = uploaded_file.getvalue().decode("utf-8")
                json_data = json.loads(json_str)

                values_array = extract_table_data_auto(json_data)
                if values_array:
                    df = process_values_array(values_array)

                if df is not None and not df.empty:
                    st.success(f"Table loaded with {df.shape[0]} rows and {df.shape[1]} columns.")
                    st.subheader("Data Preview")
                    st.dataframe(df, use_container_width=True)

                    st.subheader("Export Options")
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"table_data_{timestamp}"

                    col1, col2 = st.columns(2)
                    with col1:
                        with st.spinner("Generating Excel file..."):
                            try:
                                excel_data = io.BytesIO()
                                with pd.ExcelWriter(excel_data, engine='xlsxwriter') as writer:
                                    df.to_excel(writer, sheet_name='Data', index=False)
                                st.download_button(
                                    label="Download as Excel",
                                    data=excel_data.getvalue(),
                                    file_name=f"{filename}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )
                            except Exception as e:
                                st.error(f"Error creating Excel file: {e}")

                    with col2:
                        with st.spinner("Generating CSV file..."):
                            try:
                                csv_data = df.to_csv(index=False).encode('utf-8')
                                st.download_button(
                                    label="Download as CSV",
                                    data=csv_data,
                                    file_name=f"{filename}.csv",
                                    mime="text/csv"
                                )
                            except Exception as e:
                                st.error(f"Error creating CSV file: {e}")
                else:
                    st.warning("No tabular data found in the uploaded JSON.")

            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON format: {e}")
            except Exception as e:
                st.error(f"Unexpected error while processing file: {e}")


    with tab2:
        json_text = st.text_area("Paste your JSON data here", height=200)

        if st.button("Process JSON Text"):
            if not json_text.strip():
                st.warning("Please paste some JSON data.")
            else:
                try:
                    json_data = json.loads(json_text.strip())
                    df = None  # define early

                    values_array = extract_table_data_auto(json_data)
                    if values_array:
                        df = process_values_array(values_array)

                    if df is not None and not df.empty:
                        st.success(f"Table loaded with {df.shape[0]} rows and {df.shape[1]} columns.")
                        st.subheader("Data Preview")
                        st.dataframe(df, use_container_width=True)

                        st.subheader("Export Options")
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"table_data_{timestamp}"

                        col1, col2 = st.columns(2)
                        with col1:
                            with st.spinner("Generating Excel file..."):
                                try:
                                    excel_data = io.BytesIO()
                                    with pd.ExcelWriter(excel_data, engine='xlsxwriter') as writer:
                                        df.to_excel(writer, sheet_name='Data', index=False)
                                    st.download_button(
                                        label="Download as Excel",
                                        data=excel_data.getvalue(),
                                        file_name=f"{filename}.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                    )
                                except Exception as e:
                                    st.error(f"Error creating Excel file: {e}")

                        with col2:
                            with st.spinner("Generating CSV file..."):
                                try:
                                    csv_data = df.to_csv(index=False).encode('utf-8')
                                    st.download_button(
                                        label="Download as CSV",
                                        data=csv_data,
                                        file_name=f"{filename}.csv",
                                        mime="text/csv"
                                    )
                                except Exception as e:
                                    st.error(f"Error creating CSV file: {e}")
                    else:
                        st.warning("No tabular data found in the JSON.")

                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON: {e}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")

    
    with tab3:
        merged_df = None
        st.write("Click '+' to add JSON chunks from paginated/lazy-loaded API calls.")

        if "json_inputs_count" not in st.session_state:
            st.session_state.json_inputs_count = 1
            st.session_state.json_inputs_data = [""]

        def add_json_input():
            if st.session_state.json_inputs_count < MAX_JSON_INPUTS:
                st.session_state.json_inputs_data.append("")
                st.session_state.json_inputs_count += 1

        st.markdown("#### Input JSONs")
        for idx in range(st.session_state.json_inputs_count):
            with st.expander(f"JSON #{idx + 1}", expanded=(idx == st.session_state.json_inputs_count - 1)):
                st.session_state.json_inputs_data[idx] = st.text_area(
                    label="Paste JSON here",
                    value=st.session_state.json_inputs_data[idx],
                    height=200,
                    key=f"json_text_area_{idx}"
                )

        col_add, col_merge = st.columns([1, 3])
        with col_add:
            if st.button("➕ Add JSON Chunk"):
                add_json_input()

        with col_merge:
            if st.button("🔄 Merge All JSONs"):
                combined_records = []
                errors = []
                valid_count = 0

                for idx, json_str in enumerate(st.session_state.json_inputs_data, start=1):
                    json_str = json_str.strip()
                    if not json_str:
                        continue
                    try:
                        json_data = json.loads(json_str)
                        values_array = extract_table_data_auto(json_data)
                        if values_array:
                            df = process_values_array(values_array)
                            if df is not None:
                                combined_records.append(df)
                                valid_count += 1
                            else:
                                errors.append(f"JSON #{idx}: Unable to convert to table.")
                        else:
                            errors.append(f"JSON #{idx}: No tabular data found.")
                    except Exception as e:
                        errors.append(f"JSON #{idx}: {str(e)}")

                if combined_records:
                    merged_df = pd.concat(combined_records, ignore_index=True)
                    st.success(f"Merged {len(combined_records)} tables into one DataFrame with {merged_df.shape[0]} rows.")
        
                    st.subheader("Merged Data Preview")
                    st.dataframe(merged_df, use_container_width=True)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"merged_data_{timestamp}"

                    col1, col2 = st.columns(2)
                    with col1:
                        try:
                            excel_data = io.BytesIO()
                            with pd.ExcelWriter(excel_data, engine='xlsxwriter') as writer:
                                merged_df.to_excel(writer, sheet_name='Data', index=False)
                            st.download_button(
                                label="Download as Excel",
                                data=excel_data.getvalue(),
                                file_name=f"{filename}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        except Exception as e:
                            st.error(f"Error creating Excel: {e}")

                    with col2:
                        try:
                            csv_data = merged_df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label="Download as CSV",
                                data=csv_data,
                                file_name=f"{filename}.csv",
                                mime="text/csv"
                            )
                        except Exception as e:
                            st.error(f"Error creating CSV: {e}")
                else:
                    st.warning("No valid tables were found.")

                if errors:
                    with st.expander("⚠️ Warnings / Errors", expanded=False):
                        for err in errors:
                            st.text(err)
            if merged_df is not None and not merged_df.empty:
                st.subheader("Export Options")

    if 'json_data' in st.session_state:
        json_str = st.session_state.json_data

        try:
            json_data = json.loads(json_str)
            values_array = extract_table_data_auto(json_data)

            if values_array:
                df = process_values_array(values_array)
                if df is not None and not df.empty:
                    st.write(f"Table dimensions: {df.shape[0]} rows × {df.shape[1]} columns")
                    st.subheader("Filter Data")
                    with st.expander("Show/Hide Filters", expanded=False):
                        filters = {}
                        cols = st.columns(3)
                        for i, column in enumerate(df.columns):
                            col_idx = i % 3
                            with cols[col_idx]:
                                if is_filterable_column(df, column):
                                    if pd.api.types.is_numeric_dtype(df[column]):
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
                                        filters[column] = st.text_input(f"Filter by {column} (contains)")
                                    else:
                                        try:
                                            unique_values = df[column].dropna().unique().tolist()
                                            if len(unique_values) < 10:
                                                filters[column] = st.selectbox(
                                                    f"Filter by {column}",
                                                    options=[""] + unique_values
                                                )
                                        except:
                                            st.write(f"{column}: Cannot filter (complex data type)")
                                else:
                                    st.write(f"{column}: Cannot filter (complex data type)")

                    filtered_df = apply_filters(df, filters)
                    st.subheader("Data Preview")
                    st.dataframe(filtered_df, use_container_width=True)

                    st.subheader("Export Options")
                    col1, col2 = st.columns(2)

                    with col1:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"table_data_{timestamp}.xlsx"
                        with st.spinner("Generating Excel file..."):
                            try:
                                excel_data = io.BytesIO()
                                with pd.ExcelWriter(excel_data, engine='xlsxwriter') as writer:
                                    merged_df.to_excel(writer, sheet_name='Data', index=False)
                                st.download_button(
                                    label="Download as Excel",
                                    data=excel_data.getvalue(),
                                    file_name=f"{filename}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )
                            except Exception as e:
                                st.error(f"Error creating Excel file: {e}")
                            st.info("Try downloading as CSV instead.")

                    with col2:
                        with st.spinner("Generating CSV file..."):
                            try:
                                csv_data = merged_df.to_csv(index=False).encode('utf-8')
                                st.download_button(
                                    label="Download as CSV",
                                    data=csv_data,
                                    file_name=f"{filename}.csv",
                                    mime="text/csv"
                                )
                            except Exception as e:
                                st.error(f"Error creating CSV file: {e}")

                else:
                    st.error("Could not process the values array into a table.")
            else:
                st.error("Could not find tabular data in the JSON structure.")
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")
        except Exception as e:
            st.error(f"Error processing JSON: {e}")

if __name__ == "__main__":
    main()
