import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
from backend_logic import (
    fetch_data, execute_query, get_db_connection, scan_bill_with_groq, 
    get_ai_item_details, seed_historical_data, get_item_forecast,
    get_footfall_forecast,
    update_family_member, delete_family_member 
)

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Smart Pantry and Kitchen Manager", 
    layout="wide", 
    page_icon="🍳",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS & THEME HANDLING ---
def load_custom_css(is_dark_mode):
    bg_color = "#0e1117" if is_dark_mode else "#ffffff"
    card_bg = "#262730" if is_dark_mode else "#f0f2f6"
    
    st.markdown(f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap');
        
        html, body, [class*="css"] {{
            font-family: 'Inter', sans-serif;
        }}
        
        h1, h2, h3 {{
            font-weight: 600;
            letter-spacing: -0.5px;
        }}
        
        /* Metric Cards Styling */
        div[data-testid="stMetric"] {{
            background-color: {card_bg};
            border-radius: 8px;
            padding: 15px;
            border: 1px solid rgba(128, 128, 128, 0.2);
        }}
        
        /* Dataframe Headers */
        th {{
            background-color: {card_bg} !important;
            font-weight: 600 !important;
        }}
        
        /* Navigation Sidebar */
        section[data-testid="stSidebar"] {{
            background-color: {card_bg};
        }}
        
        /* Buttons */
        div.stButton > button:first-child {{
            border-radius: 6px;
            font-weight: 500;
        }}
        </style>
    """, unsafe_allow_html=True)

# --- AUTHENTICATION ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

def login_screen():
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><br><h2 style='text-align: center;'>Smart Pantry and Kitchen Manager</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: grey;'>WE SAVE FOOD</p>", unsafe_allow_html=True)
        with st.container(border=True):
            user = st.text_input("Username")
            pwd = st.text_input("Password", type="password")
            if st.button("Sign In", type="primary", use_container_width=True):
                if user == "admin" and pwd == "password123":
                    st.session_state.logged_in = True
                    st.rerun()
                else: st.error("Invalid Credentials")

if not st.session_state.logged_in:
    login_screen()
    st.stop()

# --- SIDEBAR & THEME ---
with st.sidebar:
    st.markdown("### Navigation")
    
    nav_options = [
        "Dashboard", 
        "Family Setup",      # NEW
        "Morning Rush",      # NEW (The Main Tool)
        "Leftover Wizard",   # NEW
        "AI Bill Scanner", 
        "Inventory Logs", 
        "Catalog Entry", 
        "Analytics", 
        "Admin Settings"
    ]
    
    choice = st.radio("Go to", nav_options, label_visibility="collapsed")
    
    st.markdown("---")
    if st.button("Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

# --- HELPERS ---
def initialize_database():
    try:
        conn = get_db_connection()
        if not conn: st.error("❌ Cannot connect to Database."); return
        cursor = conn.cursor()
        with open('setup.sql', 'r') as f: sql_script = f.read()
        sql_commands = [cmd.strip() for cmd in sql_script.split(';') if cmd.strip()]
        prog = st.progress(0)
        for i, cmd in enumerate(sql_commands):
            try: cursor.execute(cmd)
            except: pass
            prog.progress((i + 1) / len(sql_commands))
        conn.commit(); conn.close()
        st.success("✅ Database Reset Successfully! Pantry is empty."); st.rerun()
    except Exception as e: st.error(f"Error: {e}")

def run_phase4_migration():
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    for q in [
        "ALTER TABLE TBL_LOGS ADD COLUMN Unit_Price DECIMAL(10,2) DEFAULT 0.00;",
        "ALTER TABLE TBL_LOGS ADD COLUMN Vendor_Name VARCHAR(100);",
        "ALTER TABLE TBL_ITEM_CATALOG ADD COLUMN Last_Vendor VARCHAR(100);",
        "ALTER TABLE TBL_ITEM_CATALOG ADD COLUMN Last_Price DECIMAL(10,2);"
    ]:
        try: cursor.execute(q)
        except: pass
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS TBL_FOOTFALL (
                Footfall_ID INT AUTO_INCREMENT PRIMARY KEY,
                Log_Date DATETIME DEFAULT CURRENT_TIMESTAMP,
                Customer_Count INT,
                Meal_Type VARCHAR(50)
            )
        """)
    except Exception as e: st.error(f"Migration Error: {e}")
    conn.commit(); conn.close()
    st.success("✅ Database upgraded to Phase 4!")

def safe_float(val, default=0.0):
    try: return float(val)
    except (ValueError, TypeError): return default

# --- DATA FETCHERS ---
def get_stock_status():
    return fetch_data("""
        SELECT c.Item_ID, c.Item_Name, c.Category, s.Current_Quantity, c.Standard_Unit, c.Shelf_Life_Days, s.Last_Updated, c.Last_Price, c.Last_Vendor
        FROM TBL_PANTRY_STOCK s
        JOIN TBL_ITEM_CATALOG c ON s.Item_ID = c.Item_ID
        ORDER BY c.Item_Name
    """)

# --- MAIN UI ---

# 1. DASHBOARD
if choice == "Dashboard":
    st.title("Dashboard")
    st.markdown("Overview of inventory health and valuation.")
    
    try:
        df = get_stock_status()
        if df.empty:
            st.info("ℹ️ Pantry is empty. Add items to get started.")
        else:
            df['Last_Updated'] = pd.to_datetime(df['Last_Updated'])
            df['Shelf_Life_Days'] = pd.to_numeric(df['Shelf_Life_Days'], errors='coerce').fillna(7)
            
            now = datetime.now()
            df['Days_Held'] = df['Last_Updated'].apply(lambda x: (now - x).days if pd.notnull(x) else 0)
            df['Days_Remaining'] = df['Shelf_Life_Days'] - df['Days_Held']
            
            df = df.reset_index(drop=True)
            df.index = df.index + 1

            critical_items = df[(df['Days_Remaining'] < 3) | (df['Current_Quantity'] < 2)].copy()
            
            df['Last_Price'] = pd.to_numeric(df['Last_Price'], errors='coerce').fillna(0)
            df['Current_Quantity'] = pd.to_numeric(df['Current_Quantity'], errors='coerce').fillna(0)
            total_value = (df['Current_Quantity'] * df['Last_Price']).sum()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total SKU Count", len(df))
            c2.metric("Low Stock Items", len(df[df['Current_Quantity'] < 2]))
            c3.metric("Critical Expiry", len(df[df['Days_Remaining'] < 3]))
            c4.metric("Inventory Value", f"₹{total_value:,.2f}", help="Sum of (Qty * Last Price)")

            st.divider()

            if not critical_items.empty:
                st.subheader("⚠️ Critical Attention Required")
                
                def highlight_critical(val):
                    color = '#FF4B4B' 
                    return f'color: {color}; font-weight: bold;'
                
                st.dataframe(
                    critical_items[['Item_Name', 'Current_Quantity', 'Days_Remaining', 'Category']]
                    .style
                    .map(lambda x: highlight_critical(x), subset=['Days_Remaining'])
                    .format({'Days_Remaining': '{:.1f}'}), 
                    width="stretch"
                )
            
            st.subheader("Full Inventory Catalog")
            st.dataframe(
                df[['Item_Name', 'Category', 'Current_Quantity', 'Standard_Unit', 'Last_Vendor', 'Last_Price', 'Days_Remaining']], 
                width="stretch",
                height=400
            )
    except Exception as e: st.error(f"⚠️ Dashboard Error: {e}")

#2. Family setup
# 2. FAMILY CONFIGURATION (IMPROVED)
elif choice == "Family Setup":
    st.title("🏡 Family Configuration")
    st.markdown("Manage your family members and their schedules.")

    # Create Tabs for better organization
    tab1, tab2 = st.tabs(["📋 Member List & Add New", "✏️ Edit & Delete"])

    # --- TAB 1: VIEW & ADD ---
    with tab1:
        # Fetch existing members
        members = fetch_data("""
            SELECT Member_ID, Name, Role, Health_Condition, 
                DATE_FORMAT(Leave_Time, '%H:%i') as Leave_Time, 
                Needs_Packed_Lunch 
            FROM TBL_FAMILY_MEMBERS 
            ORDER BY Leave_Time ASC
        """)
        
        if not members.empty:
            st.dataframe(members, use_container_width=True)
        else:
            st.info("No family members added yet.")

        st.divider()
        st.subheader("Add New Member")
        
        with st.form("add_member_form"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Name (e.g., Rohan)")
            role = c2.selectbox("Role", ["Father", "Mother", "Grandparent", "Son", "Daughter", "House Help"])
            
            c3, c4 = st.columns(2)
            health = c3.selectbox("Health Condition", ["None", "Diabetes", "High BP", "Cholesterol", "Allergy"])
            pack_lunch = c4.checkbox("Needs Packed Lunch?")
            
            c5, c6 = st.columns(2)
            leave_time = c5.time_input("Leaves Home At (Leave empty if stays home)", value=None)
            
            if st.form_submit_button("Save Member", type="primary"):
                l_time_str = leave_time.strftime('%H:%M:%S') if leave_time else None
                
                success, message = execute_query(
                    "INSERT INTO TBL_FAMILY_MEMBERS (Name, Role, Health_Condition, Leave_Time, Needs_Packed_Lunch) VALUES (%s, %s, %s, %s, %s)",
                    (name, role, health, l_time_str, pack_lunch)
                )
                
                if success:
                    st.success(f"✅ {name} added to family!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"❌ Database Error: {message}")

    # --- TAB 2: EDIT & DELETE ---
# --- TAB 2: EDIT & DELETE ---
    with tab2:
        st.subheader("Modify Existing Member")
        
        # reload members to ensure list is fresh
        members_refresh = fetch_data("SELECT Member_ID, Name FROM TBL_FAMILY_MEMBERS ORDER BY Name")
        
        if members_refresh.empty:
            st.warning("No members to edit. Go to the 'Add New' tab first.")
        else:
            # 1. Select Member
            member_names = members_refresh['Name'].tolist()
            selected_name = st.selectbox("Select Person to Edit", member_names)
            
            # CRITICAL FIX: Ensure ID is a standard Python int, not a Numpy int
            raw_id = members_refresh[members_refresh['Name'] == selected_name].iloc[0]['Member_ID']
            selected_id = int(raw_id)
            
            # 2. Fetch Current Details for this person
            details_df = fetch_data("SELECT * FROM TBL_FAMILY_MEMBERS WHERE Member_ID = %s", (selected_id,))
            
            if not details_df.empty:
                curr = details_df.iloc[0]
                
                # Parse existing time
                current_time_val = None
                if pd.notnull(curr['Leave_Time']):
                    try:
                        # Handle timedelta (e.g., 07:30:00)
                        seconds = curr['Leave_Time'].total_seconds()
                        current_time_val = (datetime.min + timedelta(seconds=seconds)).time()
                    except:
                        try:
                            # Handle string format
                            current_time_val = datetime.strptime(str(curr['Leave_Time']), "%H:%M:%S").time()
                        except:
                            current_time_val = None

                # 3. Edit Form
                with st.form("edit_member_form"):
                    ec1, ec2 = st.columns(2)
                    new_name = ec1.text_input("Name", value=curr['Name'])
                    
                    # Handle Role Index
                    roles = ["Father", "Mother", "Grandparent", "Son", "Daughter", "House Help"]
                    role_idx = roles.index(curr['Role']) if curr['Role'] in roles else 0
                    new_role = ec2.selectbox("Role", roles, index=role_idx)
                    
                    ec3, ec4 = st.columns(2)
                    # Handle Health Index
                    healths = ["None", "Diabetes", "High BP", "Cholesterol", "Allergy"]
                    h_idx = healths.index(curr['Health_Condition']) if curr['Health_Condition'] in healths else 0
                    new_health = ec3.selectbox("Health Condition", healths, index=h_idx)
                    
                    # Checkbox
                    new_pack_lunch = ec4.checkbox("Needs Packed Lunch?", value=bool(curr['Needs_Packed_Lunch']))
                    
                    ec5, ec6 = st.columns(2)
                    new_leave_time = ec5.time_input("Leaves Home At", value=current_time_val)

                    st.markdown("---")
                    col_update, col_delete = st.columns([1, 1])
                    
                    with col_update:
                        if st.form_submit_button("💾 Update Details"):
                            l_time_str = new_leave_time.strftime('%H:%M:%S') if new_leave_time else None
                            update_family_member(selected_id, new_name, new_role, new_health, l_time_str, new_pack_lunch)
                            st.success("Updated successfully!")
                            time.sleep(1)
                            st.rerun()

                    with col_delete:
                        if st.form_submit_button("🗑️ Delete Member", type="primary"):
                            delete_family_member(selected_id)
                            st.warning(f"Deleted {selected_name}.")
                            time.sleep(1)
                            st.rerun()
            else:
                st.error("Could not fetch details. Please check database connection.")

# 3. Morning Rush
elif choice == "Morning Rush":
    st.title("☀️ Morning Rush Planner")
    st.markdown("Plan breakfast and lunch boxes based on who leaves first.")
    
    # 1. Imports needed just for this block
    from backend_logic import get_family_schedule, generate_morning_plan
    
    # 2. Context Inputs
    col1, col2 = st.columns(2)
    with col1:
        guest_count = st.number_input("Any Guests Today?", min_value=0, value=0, help="Enter number of extra people eating")
    with col2:
        lang = st.selectbox("Preferred Language", ["English", "Hindi", "Kannada", "Tamil", "Telugu"])

    # 3. Show Schedule Timeline
    family = get_family_schedule()
    if family.empty:
        st.warning("Please go to 'Family Setup' and add members first.")
    else:
        st.subheader("📅 Today's Timeline")
        # Visual Timeline
        for _, person in family.iterrows():
            time_str = person['Leave_Time'] if person['Leave_Time'] else "🏠 Stays Home"
            lunch_icon = "🍱 Pack Dabba" if person['Needs_Packed_Lunch'] else "🍽️ Eats Home"
            health_badge = f"🩺 {person['Health_Condition']}" if person['Health_Condition'] != "None" else ""
            
            st.info(f"**{time_str}** : {person['Name']} ({person['Role']}) — {lunch_icon} {health_badge}")

        st.divider()

        # 4. Generate AI Plan
        if st.button("✨ Create Cooking Plan", type="primary"):
            stock = get_stock_status()
            if stock.empty:
                st.error("Pantry is empty! Add items in Catalog first.")
            else:
                stock_str = ", ".join([f"{r['Item_Name']} ({r['Current_Quantity']} {r['Standard_Unit']})" for _, r in stock.iterrows()])
                
                with st.spinner("🤖 Thinking... (Checking Inventory & Schedule)"):
                    plan = generate_morning_plan(stock_str, family, guest_count, lang)
                    st.markdown("### 🍳 Your Morning Plan")
                    st.markdown(plan)

# 4. Leftover Wizard
elif choice == "Leftover Wizard":
    st.title("♻️ Leftover Wizard")
    st.markdown("Don't throw food away! Let AI suggest how to reuse it.")
    
    from backend_logic import suggest_leftover_recipe
    
    c1, c2 = st.columns([2, 1])
    item = c1.text_input("What is leftover? (e.g., Rice, Dal, Chapati)")
    lang_lo = c2.selectbox("Language", ["English", "Hindi", "Kannada"])
    
    if st.button("Get Ideas"):
        if item:
            with st.spinner("Asking Grandma AI..."):
                idea = suggest_leftover_recipe(item, lang_lo)
                st.success("Try these:")
                st.markdown(idea)
        else:
            st.warning("Enter an item name.")

# 5. AI Bill Scanner
elif choice == "AI Bill Scanner":
    st.title("AI Bill Scanner")
    st.markdown("Upload receipt images to auto-update inventory using Llama Vision.")
    
    with st.container(border=True):
        uploaded_file = st.file_uploader("Upload Bill Image", type=['png', 'jpg', 'jpeg'])
        
    if 'scanned_data' not in st.session_state: st.session_state.scanned_data = []
    if 'scanned_vendor' not in st.session_state: st.session_state.scanned_vendor = ""

    if uploaded_file:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.image(uploaded_file, caption="Receipt Preview") 
        with c2:
            st.info("Click below to extract items, quantities, and prices.")
            if st.button("Start AI Analysis", type="primary"):
                with st.spinner("Processing image with Groq AI..."):
                    res = scan_bill_with_groq(uploaded_file.getvalue())
                    if "error" in res: st.error(res['error'])
                    else:
                        st.session_state.scanned_data = res.get("items", [])
                        st.session_state.scanned_vendor = res.get("vendor", "Unknown")
                        st.success(f"Analysis Complete! Found {len(st.session_state.scanned_data)} items.")

    if st.session_state.scanned_data:
        st.divider()
        st.subheader("Verify & Commit")
        vendor_name = st.text_input("Vendor Name", value=st.session_state.scanned_vendor)
        
        scan_df = pd.DataFrame(st.session_state.scanned_data)
        if not scan_df.empty:
            scan_df.index = scan_df.index + 1
        
        edited_df = st.data_editor(scan_df, num_rows="dynamic", width="stretch")
        
        if st.button("Save to Database", type="primary"):
            count = 0
            progress_bar = st.progress(0)
            
            edited_records = edited_df.to_dict('records')
            total_items = len(edited_records)
            
            for idx, item in enumerate(edited_records):
                i_name = item.get('name', 'Unk')
                i_qty = safe_float(item.get('quantity', 0))
                i_price = safe_float(item.get('price', 0))
                
                existing = fetch_data("SELECT Item_ID FROM TBL_ITEM_CATALOG WHERE LOWER(Item_Name) = LOWER(%s)", (i_name,))
                i_id = None
                
                if not existing.empty:
                    i_id = int(existing.iloc[0]['Item_ID'])
                    execute_query("UPDATE TBL_ITEM_CATALOG SET Last_Vendor=%s, Last_Price=%s WHERE Item_ID=%s", (vendor_name, i_price, i_id))
                else:
                    raw_shelf = item.get('shelf_life', None)
                    i_shelf_life = None
                    i_category = 'Groceries'
                    try: i_shelf_life = int(float(raw_shelf))
                    except (ValueError, TypeError): i_shelf_life = None
                    
                    if i_shelf_life is None:
                        with st.spinner(f"Fetching details for new item: {i_name}..."):
                            ai_details = get_ai_item_details(i_name)
                            if "error" not in ai_details:
                                i_category = ai_details.get('category', 'Groceries')
                                try: i_shelf_life = int(ai_details.get('shelf_life', 7))
                                except: i_shelf_life = 7 
                            else: i_shelf_life = 7
                    
                    execute_query(
                        "INSERT INTO TBL_ITEM_CATALOG (Item_Name, Category, Standard_Unit, Shelf_Life_Days, Last_Vendor, Last_Price) VALUES (%s, %s, %s, %s, %s, %s)", 
                        (i_name, i_category, item.get('unit', 'Units'), i_shelf_life, vendor_name, i_price)
                    )
                    id_df = fetch_data("SELECT Item_ID FROM TBL_ITEM_CATALOG WHERE Item_Name=%s ORDER BY Item_ID DESC LIMIT 1", (i_name,))
                    if not id_df.empty: i_id = int(id_df.iloc[0]['Item_ID'])
                
                if i_id:
                    execute_query("INSERT INTO TBL_LOGS (Item_ID, Action_Type, Quantity, Unit_Price, Vendor_Name) VALUES (%s, 'PURCHASE', %s, %s, %s)", (i_id, i_qty, i_price, vendor_name))
                    check = fetch_data("SELECT Stock_ID FROM TBL_PANTRY_STOCK WHERE Item_ID=%s", (i_id,))
                    if check.empty:
                        execute_query("INSERT INTO TBL_PANTRY_STOCK (Item_ID, Current_Quantity) VALUES (%s, %s)", (i_id, i_qty))
                    else:
                        execute_query("UPDATE TBL_PANTRY_STOCK SET Current_Quantity = Current_Quantity + %s WHERE Item_ID = %s", (i_qty, i_id))
                    count += 1
                
                progress_bar.progress((idx + 1) / total_items)
                
            st.success(f"Successfully committed {count} items to inventory!"); st.session_state.scanned_data = []; st.rerun()

# 6. Inventory Logs
elif choice == "Inventory Logs":
    st.title("Inventory Logs")
    tab1, tab2 = st.tabs(["Manual Adjustment", "Price History"])
    items = fetch_data("SELECT Item_ID, Item_Name, Standard_Unit, Last_Price, Last_Vendor FROM TBL_ITEM_CATALOG ORDER BY Item_Name")
    
    with tab1:
        if not items.empty:
            c_sel, c_info = st.columns([2, 1])
            with c_sel: 
                raw_id = st.selectbox("Select Ingredient", items['Item_ID'], format_func=lambda x: items[items['Item_ID']==x]['Item_Name'].iloc[0])
                i_id = int(raw_id)
            
            details = items[items['Item_ID'] == i_id].iloc[0]
            curr_stock_df = fetch_data("SELECT Current_Quantity FROM TBL_PANTRY_STOCK WHERE Item_ID = %s", (i_id,))
            current_qty = float(curr_stock_df.iloc[0]['Current_Quantity']) if not curr_stock_df.empty else 0.0
            
            st.info(f"**Current Stock:** {current_qty} {details['Standard_Unit']}  |  **Last Price:** ₹{details['Last_Price']}")
            
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns(4)
                act = c1.selectbox("Action Type", ["PURCHASE", "CONSUME", "WASTE"])
                qty = c2.number_input(f"Quantity ({details['Standard_Unit']})", min_value=0.1)
                price = c3.number_input("Unit Price (₹)", value=float(details['Last_Price'] or 0))
                vendor = c4.text_input("Vendor", value=str(details['Last_Vendor'] or ""))

                if st.button("Update Inventory Record", type="primary", use_container_width=True):
                    execute_query("INSERT INTO TBL_LOGS (Item_ID, Action_Type, Quantity, Unit_Price, Vendor_Name) VALUES (%s, %s, %s, %s, %s)", (i_id, act, qty, price, vendor))
                    if act == "PURCHASE": execute_query("UPDATE TBL_ITEM_CATALOG SET Last_Vendor=%s, Last_Price=%s WHERE Item_ID=%s", (vendor, price, i_id))

                    new_qty = current_qty + qty if act == "PURCHASE" else current_qty - qty
                    
                    if new_qty <= 0:
                        execute_query("DELETE FROM TBL_PANTRY_STOCK WHERE Item_ID = %s", (i_id,))
                        st.warning(f"Stock depleted. Item removed from active pantry.")
                    else:
                        check = fetch_data("SELECT Stock_ID FROM TBL_PANTRY_STOCK WHERE Item_ID=%s", (i_id,))
                        if check.empty:
                            execute_query("INSERT INTO TBL_PANTRY_STOCK (Item_ID, Current_Quantity) VALUES (%s, %s)", (i_id, new_qty))
                        else:
                            execute_query("UPDATE TBL_PANTRY_STOCK SET Current_Quantity = %s WHERE Item_ID = %s", (new_qty, i_id))
                    st.success("Transaction recorded successfully!"); st.rerun()

    with tab2:
        if not items.empty:
            raw_hid = st.selectbox("Select Item for History", items['Item_ID'], format_func=lambda x: items[items['Item_ID']==x]['Item_Name'].iloc[0], key='h')
            hid = int(raw_hid)
            hist = fetch_data("SELECT Log_Date, Unit_Price, Vendor_Name, Quantity, Action_Type FROM TBL_LOGS WHERE Item_ID=%s ORDER BY Log_Date DESC", (hid,))
            if not hist.empty: 
                hist = hist.reset_index(drop=True)
                hist.index = hist.index + 1
                st.plotly_chart(px.line(hist[hist['Action_Type']=='PURCHASE'], x='Log_Date', y='Unit_Price', title="Price Fluctuation Trend (₹)"), use_container_width=True)
                st.dataframe(hist, width="stretch")

# 7. Catalog Entry
elif choice == "Catalog Entry":
    st.title("Catalog Entry")
    st.markdown("Register new ingredients into the system.")
    
    if 'new_item' not in st.session_state: st.session_state.new_item = {"name": "", "cat": "Dairy", "unit": "kg", "shelf": 7}
    
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        name_in = c1.text_input("Ingredient Name", value=st.session_state.new_item['name'])
        if c2.button("✨ AI Auto-Fill", help="Predict category and shelf life"):
            with st.spinner("Analyzing..."):
                res = get_ai_item_details(name_in)
                if "error" not in res:
                    st.session_state.new_item.update({"name": name_in, "cat": res.get("category"), "unit": res.get("unit"), "shelf": int(res.get("shelf_life", 7))})
                    st.rerun()
                else: st.error(res['error'])
    
    with st.form("new_item_form"):
        name = st.text_input("Confirm Name", value=name_in)
        valid_cats = ["Dairy", "Vegetable", "Fruit", "Meat", "Grains", "Spices", "Beverage", "Cleaning", "Other"]
        ai_cat = st.session_state.new_item.get("cat", "Dairy")
        idx = 0
        if ai_cat in valid_cats: idx = valid_cats.index(ai_cat)
        
        c3, c4 = st.columns(2)
        cat = c3.selectbox("Category", valid_cats, index=idx)
        unit = c4.selectbox("Unit of Measure", ["kg", "Liters", "Units", "Grams", "Packets", "Cans", "Bottles", "Dozen"], index=0)
        
        c5, c6 = st.columns(2)
        shelf = c5.number_input("Shelf Life (Days)", value=st.session_state.new_item['shelf'])
        qty = c6.number_input("Opening Stock", min_value=0.0)
        
        c7, c8 = st.columns(2)
        init_price = c7.number_input("Price per Unit (₹)", min_value=0.0)
        init_vendor = c8.text_input("Default Vendor")
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.form_submit_button("Create Item", type="primary"):
            if not name:
                st.error("Name is required!")
            else:
                check = fetch_data("SELECT Item_ID FROM TBL_ITEM_CATALOG WHERE LOWER(Item_Name) = LOWER(%s)", (name,))
                if not check.empty: st.error("Item already exists in catalog!")
                else:
                    s1, m1 = execute_query("INSERT INTO TBL_ITEM_CATALOG (Item_Name, Category, Standard_Unit, Shelf_Life_Days, Last_Vendor, Last_Price) VALUES (%s, %s, %s, %s, %s, %s)", (name, cat, unit, shelf, init_vendor, init_price))
                    if s1:
                        new_item_row = fetch_data("SELECT Item_ID FROM TBL_ITEM_CATALOG WHERE Item_Name=%s", (name,))
                        if not new_item_row.empty:
                            nid = int(new_item_row.iloc[0]['Item_ID'])
                            s2, m2 = execute_query("INSERT INTO TBL_PANTRY_STOCK (Item_ID, Current_Quantity) VALUES (%s, %s)", (nid, qty))
                            if s2:
                                if qty > 0:
                                    execute_query("INSERT INTO TBL_LOGS (Item_ID, Action_Type, Quantity, Unit_Price, Vendor_Name) VALUES (%s, 'PURCHASE', %s, %s, %s)", (nid, qty, init_price, init_vendor))
                                st.success(f"Item '{name}' created successfully!")
                                st.session_state.new_item = {"name": "", "cat": "Dairy", "unit": "kg", "shelf": 7}
                                st.rerun()
                            else: st.error(f"Stock Error: {m2}")
                    else: st.error(f"Catalog Error: {m1}")

# 8. ANALYTICS
elif choice == "Analytics":
    st.title("Analytics")
    t1, t2 = st.tabs(["Inventory Demand", "Footfall Traffic"])
    
    with t1:
        items = fetch_data("SELECT Item_ID, Item_Name FROM TBL_ITEM_CATALOG")
        if not items.empty:
            raw_sid = st.selectbox("Select Item for Forecasting", items['Item_ID'], format_func=lambda x: items[items['Item_ID']==x]['Item_Name'].iloc[0])
            sid = int(raw_sid)
            if st.button("Generate Demand Forecast"):
                with st.spinner("Calculating projection..."):
                    res = get_item_forecast(sid)
                    if "error" in res: st.error(res['error'])
                    else: 
                        st.metric("Predicted Consumption (Next 7 Days)", f"{res['total_demand']} Units")
                        st.plotly_chart(px.line(res['trend_chart'], x='ds', y='yhat', title="Demand Trend"), use_container_width=True)
    with t2:
        st.markdown("### Customer Traffic Prediction")
        if st.button("Analyze Footfall"):
            with st.spinner("Analyzing patterns..."):
                res = get_footfall_forecast()
                if "error" in res: st.error(res['error'])
                else: 
                    st.metric("Expected Visitors (Next 7 Days)", res['total_visitors'])
                    st.plotly_chart(px.line(res['trend_chart'], x='ds', y='yhat', title="Visitor Forecast"), use_container_width=True)

# 9. Admin Settings
elif choice == "Admin Settings":
    st.title("Admin Settings")
    
    with st.container(border=True):
        st.subheader("Database Maintenance")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Run Phase 4 Migration", help="Update Schema"): 
                run_phase4_migration()
            
            if st.button("Reset Database", type="primary", help="⚠️ Wipes all data"): 
                initialize_database()
        
        with c2:
            if st.button("Seed Mock Data", help="Fills DB with test data"): 
                with st.spinner("Seeding..."): st.info(seed_historical_data())
