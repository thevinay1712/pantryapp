import streamlit as st
import pandas as pd
from backend_logic import *
from datetime import date

st.set_page_config(page_title="Smart Kitchen OS", layout="wide")

# --- AUTH ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

def login():
    st.title("Manager Login")
    c1, c2 = st.columns(2)
    user = c1.text_input("Username")
    pwd = c2.text_input("Password", type="password")
    if st.button("Login"):
        if user == "admin" and pwd == "admin123":
            st.session_state.logged_in = True
            st.rerun()
        else: st.error("Invalid Credentials")

if not st.session_state.logged_in:
    login()
    st.stop()

# --- HELPER: LIVE INVENTORY TABLE ---
def show_live_inventory():
    st.markdown("### 📦 Live Pantry Status")
    # Fetch Data
    df_inv = fetch_data("""
        SELECT item_name, quantity, unit_label, name as category 
        FROM TBL_PANTRY 
        JOIN TBL_CATEGORIES ON TBL_PANTRY.category_id = TBL_CATEGORIES.category_id
    """)
    # Display nicely
    st.dataframe(df_inv, use_container_width=True)

# --- SIDEBAR ---
st.sidebar.title("👨‍🍳 Smart Kitchen OS")
choice = st.sidebar.radio("Navigate", ["Inventory", "Bill Scanner", "Chef's Menu", "Customer AI"])

# ==========================================
# 1. INVENTORY (Add & Remove)
# ==========================================
if choice == "Inventory":
    st.header("Manage Inventory")
    
    # Two Tabs: Add and Remove
    tab1, tab2 = st.tabs(["Add Item", "Remove Item"])
    
    with tab1:
        c1, c2, c3 = st.columns(3)
        i_name = c1.text_input("Item Name")
        i_cat = c2.selectbox("Category", ["Dairy", "Spices", "Groceries", "Pulses", "Oil", "Beverages", "Utensils"])
        i_qty = c3.number_input("Qty", 0.0, step=0.1)
        
        if st.button("➕ Add to Pantry"):
            sql = """INSERT INTO TBL_PANTRY (item_name, category_id, quantity, unit_type, unit_label) 
                     VALUES (%s, (SELECT category_id FROM TBL_CATEGORIES WHERE name=%s), %s, 'discrete', 'unit')"""
            execute_query(sql, (i_name, i_cat, i_qty))
            st.success(f"Added {i_name}!")
            st.rerun() # Refresh immediately

    with tab2:
        # Fetch current items for the dropdown
        current_items = fetch_data("SELECT item_name FROM TBL_PANTRY")
        if not current_items.empty:
            item_to_remove = st.selectbox("Select Item to Remove", current_items['item_name'])
            if st.button("🗑️ Remove Selected"):
                delete_item_by_name(item_to_remove)
                st.warning(f"Removed {item_to_remove}")
                st.rerun() # Refresh immediately
        else:
            st.info("Pantry is empty.")

    st.divider()
    # LIVE DISPLAY (Requirement 2 & 3)
    show_live_inventory()

# ==========================================
# 2. BILL SCANNER
# ==========================================
elif choice == "Bill Scanner":
    st.header("🧾 Bill Scanner")
    uploaded = st.file_uploader("Upload Bill", type=['jpg','png'])
    if uploaded and st.button("Analyze"):
        data = process_bill_image(uploaded.getvalue())
        st.json(data)
        st.info("Logic to auto-add these to DB would go here.")

# ==========================================
# 3. CHEF'S MENU
# ==========================================
elif choice == "Chef's Menu":
    st.header("🍳 AI Menu Planner")
    
    # LIVE DISPLAY (Requirement 4)
    with st.expander("View Available Ingredients", expanded=True):
        show_live_inventory()
    
    c1, c2 = st.columns(2)
    prep_time = c1.slider("Time (mins)", 15, 120, 30)
    cust_count = c2.number_input("Customers", 1, 100, 10)
    
    if st.button("Generate Menu"):
        inv = fetch_data("SELECT * FROM TBL_PANTRY")
        chefs = fetch_data("SELECT * FROM TBL_CHEFS")
        menu = generate_menu(inv, chefs, prep_time, cust_count)
        
        for dish in menu.get('recommendations', []):
            st.info(f"**{dish['dish_name']}** (Chef {dish['assigned_chef']})")

# ==========================================
# 4. CUSTOMER AI
# ==========================================
elif choice == "Customer AI":
    st.header("📈 Customer Prediction")
    
    # LIVE DISPLAY (Requirement 5)
    with st.expander("Check Stock for High Traffic", expanded=False):
        show_live_inventory()
        
    d = st.date_input("Date")
    if st.button("Predict"):
        res = predict_customers(d)
        st.metric("Predicted Customers", res['prediction'])
        st.write(f"Holiday: {res['holiday_name']}")