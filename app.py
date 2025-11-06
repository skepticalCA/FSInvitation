import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe, get_as_dataframe
import uuid
import io
import qrcode
import json # Corrected: Import json for parsing the secret

# --- CONFIGURATION ---
# IMPORTANT: Use the exact URL you provided
SHEET_URL = "https://docs.google.com/spreadsheets/d/1pNW2z9RrAAJJZOyPJZUQx3QHZ4u1lm0bl2v2Sbl6lvk/edit?gid=0#gid=0"

# --- GOOGLE SHEETS CONNECTION ---

@st.cache_resource(ttl=3600)
def connect_gspread():
    """Initializes and authenticates the gspread client by parsing the secret string."""
    try:
        # Access the secret as a raw string
        credentials_json_string = st.secrets["gcp_service_account"] 
        
        # Corrected: Convert the raw string into a Python dictionary
        credentials = json.loads(credentials_json_string) 
        
        # Use the dictionary for authentication
        gc = gspread.service_account_from_dict(credentials)
        return gc
    except KeyError:
        st.error('Authentication failed: The key "gcp_service_account" was not found in st.secrets.')
        st.stop()
    except Exception as e:
        st.error(f"Authentication failed during JSON load or GSpread connection. Error: {e}")
        st.stop()

@st.cache_data(ttl=5)
def load_data(gc_client, sheet_url):
    """Loads data from the Google Sheet into a Pandas DataFrame."""
    try:
        sh = gc_client.open_by_url(sheet_url)
        worksheet = sh.get_worksheet(0)
        df = get_as_dataframe(worksheet, header=0, evaluate_formulas=True)
        # Ensure minimum required columns exist
        if 'Unique ID (UUID)' not in df.columns:
            df['Unique ID (UUID)'] = ''
        if 'Attendance Status' not in df.columns:
            df['Attendance Status'] = 'NO'

        df = df.dropna(how='all') 
        return df
    except Exception as e:
        st.error(f"Could not load data from sheet. Check URL and Sharing permissions. Error: {e}")
        return pd.DataFrame() 

def save_data(gc_client, sheet_url, df):
    """Saves the DataFrame back to the Google Sheet, overwriting existing data."""
    try:
        sh = gc_client.open_by_url(sheet_url)
        worksheet = sh.get_worksheet(0)
        # Overwrite the sheet with the entire, updated DataFrame
        set_with_dataframe(worksheet, df) 
        st.success("Database updated successfully! Attendance data is now saved.")
        st.cache_data.clear() # Clear the cache so the next load pulls the fresh data
    except Exception as e:
        st.error(f"Failed to save data to sheet. Error: {e}")

def generate_qr_image(data):
    """Generates a QR code image buffer."""
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# --- MAIN APP EXECUTION ---

gc = connect_gspread()
df_attendees = load_data(gc, SHEET_URL)

st.sidebar.title("QR Code System")

# Sidebar for Mode Selection
mode = st.sidebar.radio(
    "Select Operation Mode",
    ("View/Bulk Generation", "Single User Generation")
)

if mode == "Single User Generation":
    st.header("👤 Urgent Registration & QR Generation")
    
    with st.form("single_user_form"):
        st.markdown("Enter details for the new attendee.")
        new_name = st.text_input("Name")
        new_phone = st.text_input("Phone Number")
        new_email = st.text_input("Email (Optional)")
        submitted = st.form_submit_button("Generate & Save Attendee")
        
        if submitted and new_name and new_phone:
            # 1. Generate Unique ID
            new_uuid = str(uuid.uuid4())[:8].upper()
            
            # 2. Prepare new row data
            new_row = {
                'Name': new_name,
                'Phone Number': new_phone,
                'Email': new_email if new_email else 'N/A', 
                'Unique ID (UUID)': new_uuid,
                'Attendance Status': 'NO'
            }
            
            # 3. Append to local DataFrame
            new_df = pd.concat([df_attendees, pd.DataFrame([new_row])], ignore_index=True)
            
            # 4. Save entire new DataFrame to Google Sheet
            save_data(gc, SHEET_URL, new_df)
            
            # 5. Display QR code for immediate use/printing
            qr_buffer = generate_qr_image(new_uuid)
            st.success(f"Attendee **{new_name}** saved with ID: **{new_uuid}**")
            st.image(qr_buffer, caption=f"QR Code for {new_name}", width=200)
            
            st.warning("Please advise the check-in team of the new ID for manual lookup.")

elif mode == "View/Bulk Generation":
    st.header("📋 Master Attendee List & QR Code Preview")
    
    # Generate QRs for all existing attendees for bulk printing
    qr_col_data = []
    for index, row in df_attendees.iterrows():
        unique_id = row['Unique ID (UUID)']
        if unique_id:
            qr_buffer = generate_qr_image(unique_id)
            qr_col_data.append(qr_buffer)
        else:
            qr_col_data.append(None)

    df_display = df_attendees.copy()
    # Note: Streamlit DataFrames struggle with image columns; for simplicity, we display the data here.
    st.dataframe(df_display, use_container_width=True)
    
    # Download button for printing QR codes later (using the Google Sheet method)
    csv_export = df_attendees.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Master CSV for Backup/Printing",
        data=csv_export,
        file_name='master_attendee_list.csv',
        mime='text/csv',
    )
