import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe, get_as_dataframe
import uuid
import io
import qrcode

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource(ttl=3600)
def connect_gspread():
    """Initializes and authenticates the gspread client."""
    try:
        # Authenticate using the secrets passed from Streamlit Cloud
        credentials = st.secrets["gcp_service_account"]
        gc = gspread.service_account_from_dict(credentials)
        return gc
    except Exception as e:
        st.error(f"Authentication failed. Check your Streamlit secrets. Error: {e}")
        return None

@st.cache_data(ttl=5) # Cache data for 5 seconds to reduce API calls
def load_data(gc, sheet_url):
    """Loads data from the Google Sheet into a Pandas DataFrame."""
    try:
        sh = gc.open_by_url(sheet_url)
        # Assuming data is on the first worksheet (index 0)
        worksheet = sh.get_worksheet(0)
        df = get_as_dataframe(worksheet, header=0, evaluate_formulas=True)
        # Clean up empty rows
        df = df.dropna(how='all') 
        return df
    except Exception as e:
        st.error(f"Could not load data from sheet. Ensure the Sheet URL is correct and the service account has Editor access. Error: {e}")
        return pd.DataFrame() # Return empty DataFrame on failure

def save_data(gc, sheet_url, df):
    """Saves the DataFrame back to the Google Sheet, overwriting existing data."""
    try:
        sh = gc.open_by_url(sheet_url)
        worksheet = sh.get_worksheet(0)
        # Overwrite the sheet with the entire, updated DataFrame
        set_with_dataframe(worksheet, df) 
        st.success("Database updated successfully!")
        st.cache_data.clear() # Clear the cache so the next load pulls the fresh data
    except Exception as e:
        st.error(f"Failed to save data to sheet. Error: {e}")

# --- QR GENERATION LOGIC ---
def generate_qr_image(data):
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# --- MAIN APP ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1pNW2z9RrAAJJZOyPJZUQx3QHZ4u1lm0bl2v2Sbl6lvk/edit?gid=0#gid=0" # <<< IMPORTANT: UPDATE THIS

gc = connect_gspread()
if gc is None:
    st.stop()

df_attendees = load_data(gc, SHEET_URL)

# Sidebar for Mode Selection
mode = st.sidebar.radio(
    "Select Operation Mode",
    ("View/Bulk Download", "Single User Generation")
)

if mode == "Single User Generation":
    st.header("👤 Urgent Registration & QR Generation")

    with st.form("single_user_form"):
        st.markdown("Enter details for the new attendee.")
        new_name = st.text_input("Name")
        new_phone = st.text_input("Phone Number")
        submitted = st.form_submit_button("Generate & Save Attendee")

        if submitted and new_name and new_phone:
            # 1. Generate Unique ID
            new_uuid = str(uuid.uuid4())[:8].upper()

            # 2. Prepare new row data
            new_row = {
                'Name': new_name,
                'Phone Number': new_phone,
                'Email': 'N/A', # Placeholder if email isn't collected here
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

elif mode == "View/Bulk Download":
    st.header("📋 Master Attendee List")
    st.dataframe(df_attendees)

    # Download button for printing QR codes later (using the Google Sheet method)
    csv_export = df_attendees.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Master CSV for Backup/Printing",
        data=csv_export,
        file_name='master_attendee_list.csv',
        mime='text/csv',
    )
