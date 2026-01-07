import mysql.connector
import pandas as pd
import os
import base64
import json
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from groq import Groq
import hashlib
# 1. Load environment variables
load_dotenv()

# --- CONFIGURATION ---
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'), 
    'database': os.getenv('DB_NAME'),
    'port': int(os.getenv('DB_PORT', 3306))
}

# Initialize AI Client
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
client = None
if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)

# --- DATABASE HELPERS ---
def get_db_connection():
    try:
        if not DB_CONFIG['password']: return None
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        return None

def fetch_data(query, params=None):
    """Fetches data using cursor to avoid Pandas UserWarning."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            columns = [col[0] for col in cursor.description]
            data = cursor.fetchall()
            df = pd.DataFrame(data, columns=columns)
            cursor.close()
            conn.close()
            return df
        except Exception as e:
            if conn.is_connected(): conn.close()
            return pd.DataFrame()
    return pd.DataFrame()

def execute_query(query, params=None):
    """Executes a query and returns (Success_Bool, Message_String)."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            cursor.close()
            conn.close()
            return True, "Success"
        except Exception as e:
            if conn.is_connected(): conn.close()
            return False, str(e)
    return False, "Connection Failed"

# --- ANALYTICS & SEEDING (OPTIMIZED) ---

def log_footfall_transaction(customer_count, meal_type):
    """Logs real-time footfall from the Chef screen."""
    return execute_query(
        "INSERT INTO TBL_FOOTFALL (Customer_Count, Meal_Type) VALUES (%s, %s)", 
        (customer_count, meal_type)
    )[0]

def seed_historical_data():
    """Generates 60 days of mock consumption & footfall data."""
    conn = get_db_connection()
    if not conn: return "DB Connection Failed"
    
    try:
        cursor = conn.cursor()
        
        # Ensure TBL_FOOTFALL exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS TBL_FOOTFALL (
                Footfall_ID INT AUTO_INCREMENT PRIMARY KEY,
                Log_Date DATETIME DEFAULT CURRENT_TIMESTAMP,
                Customer_Count INT,
                Meal_Type VARCHAR(50)
            )
        """)
        conn.commit()

        cursor.execute("SELECT Item_ID FROM TBL_ITEM_CATALOG")
        items = [row[0] for row in cursor.fetchall()]
        
        if not items: return "No items in catalog. Add items first."

        footfall_data = []
        log_data = []
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)
        current_sim_date = start_date
        
        while current_sim_date < end_date:
            weekday = current_sim_date.weekday()
            
            # Weekend Bump Logic
            base_footfall = random.randint(20, 40)
            if weekday >= 4: base_footfall += random.randint(15, 35)
            if weekday == 0: base_footfall -= random.randint(5, 10)
            
            lunch_count = int(base_footfall * 0.4)
            dinner_count = base_footfall - lunch_count
            
            lunch_time = current_sim_date.replace(hour=13, minute=30)
            dinner_time = current_sim_date.replace(hour=20, minute=00)
            
            footfall_data.append((lunch_time, lunch_count, 'Lunch'))
            footfall_data.append((dinner_time, dinner_count, 'Dinner'))
            
            # Simulate Item Consumption
            daily_items = random.sample(items, k=max(1, int(len(items)*0.4)))
            
            for i_id in daily_items:
                consumption = round(base_footfall * random.uniform(0.05, 0.2), 2)
                if consumption > 0:
                    log_data.append((i_id, 'CONSUME', consumption, 'Historical Seed', dinner_time))
            
            current_sim_date += timedelta(days=1)

        # Batch Insert
        batch_size = 100
        for i in range(0, len(footfall_data), batch_size):
            cursor.executemany("INSERT INTO TBL_FOOTFALL (Log_Date, Customer_Count, Meal_Type) VALUES (%s, %s, %s)", footfall_data[i:i + batch_size])
            conn.commit()

        log_batch_size = 50
        for i in range(0, len(log_data), log_batch_size):
            cursor.executemany("INSERT INTO TBL_LOGS (Item_ID, Action_Type, Quantity, Vendor_Name, Log_Date) VALUES (%s, %s, %s, %s, %s)", log_data[i:i + log_batch_size])
            conn.commit()
        
        return f"Success! Optimized Seed Complete: {len(footfall_data)} footfall records and {len(log_data)} consumption logs added."

    except Exception as e:
        conn.rollback()
        return f"Error: {str(e)}"
    finally:
        if cursor: cursor.close()
        conn.close()

def get_footfall_forecast(days_ahead=7):
    try: from prophet import Prophet
    except ImportError: return {"error": "Prophet library not installed."}
    
    df = fetch_data("SELECT Log_Date as ds, Customer_Count as y FROM TBL_FOOTFALL ORDER BY Log_Date ASC")
    if len(df) < 5: return {"error": "Not enough data. Please Seed Data in Admin."}
    
    df['ds'] = pd.to_datetime(df['ds']).dt.tz_localize(None)
    df_daily = df.groupby(df['ds'].dt.date)['y'].sum().reset_index()
    df_daily.columns = ['ds', 'y']
    
    try:
        m = Prophet(daily_seasonality=False, yearly_seasonality=False)
        m.fit(df_daily)
        future = m.make_future_dataframe(periods=days_ahead)
        forecast = m.predict(future)
        
        next_days = forecast.tail(days_ahead)[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]
        total_visitors = round(next_days['yhat'].sum())
        
        return {"success": True, "forecast_df": next_days, "total_visitors": total_visitors, "trend_chart": forecast[['ds', 'yhat']]}
    except Exception as e: return {"error": f"Model Error: {str(e)}"}

def get_item_forecast(item_id, days_ahead=7):
    try: from prophet import Prophet
    except ImportError: return {"error": "Prophet library not installed."}

    df = fetch_data("SELECT Log_Date as ds, Quantity as y FROM TBL_LOGS WHERE Item_ID = %s AND Action_Type = 'CONSUME' ORDER BY Log_Date ASC", (item_id,))
    if len(df) < 5: return {"error": "Not enough data. Please Seed Data in Admin."}
    
    df['ds'] = pd.to_datetime(df['ds']).dt.tz_localize(None)
    df_daily = df.groupby(df['ds'].dt.date)['y'].sum().reset_index()
    df_daily.columns = ['ds', 'y']
    
    try:
        m = Prophet(daily_seasonality=True, yearly_seasonality=False)
        m.fit(df_daily)
        future = m.make_future_dataframe(periods=days_ahead)
        forecast = m.predict(future)
        
        next_days = forecast.tail(days_ahead)[['ds', 'yhat']]
        total_demand = next_days['yhat'].sum()
        
        return {"success": True, "forecast_df": next_days, "total_demand": round(total_demand, 2), "trend_chart": forecast[['ds', 'yhat']]}
    except Exception as e: return {"error": f"Model Error: {str(e)}"}

# --- AI HELPERS ---

def get_ai_item_details(item_name):
    if not client: return {"error": "API Key missing"}
    
    prompt = f"""
    For the food ingredient '{item_name}', return a JSON object with:
    1. 'category': Must be one of [Dairy, Vegetable, Fruit, Meat, Grains, Spices, Beverage, Cleaning, Other].
    2. 'shelf_life': Estimated shelf life in days (integer).
    3. 'unit': Suggested unit from [kg, Liters, Units, Grams, Packets, Cans, Bottles, Dozen].
    """
    
    try:
        return json.loads(client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}], temperature=0, response_format={"type": "json_object"}).choices[0].message.content)
    except Exception as e: return {"error": str(e)}

def scan_bill_with_groq(image_bytes):
    if not client: return {"error": "API Key missing"}
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    prompt = "Analyze bill. Return JSON: {'vendor': 'V', 'items': [{'name': 'N', 'quantity': 1, 'unit': 'U', 'price': 1.0, 'shelf_life': 7}]}"
    try:
        return json.loads(client.chat.completions.create(model="meta-llama/llama-4-scout-17b-16e-instruct", messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}], temperature=0, response_format={"type": "json_object"}).choices[0].message.content)
    except Exception as e: return {"error": str(e)}

# --- STEP 2: SMART AI PLANNING (CORRECTED) ---

def get_inventory_with_ids():
    """Fetches inventory formatted for AI context with IDs."""
    # CRITICAL FIX: Changed 'Item_ID' to 's.Item_ID' to avoid "Column Ambiguous" error
    df = fetch_data("""
        SELECT s.Item_ID, c.Item_Name, s.Current_Quantity, c.Standard_Unit 
        FROM TBL_PANTRY_STOCK s 
        JOIN TBL_ITEM_CATALOG c ON s.Item_ID = c.Item_ID
        WHERE s.Current_Quantity > 0
    """)
    
    if df.empty: return "Inventory is Empty."
    
    inventory_str = ""
    for _, row in df.iterrows():
        inventory_str += f"- ID {row['Item_ID']}: {row['Item_Name']} ({row['Current_Quantity']} {row['Standard_Unit']})\n"
    return inventory_str
# --- STEP 2: SMART AI PLANNING (STRICT INVENTORY FIRST) ---

def generate_morning_plan(family_df, guest_count=0, language="English"):
    if not client: return {"error": "API Key missing"}
    
    # 1. Get Inventory with IDs
    inventory_context = get_inventory_with_ids()
    
    # 2. Family Context
    family_context = ""
    for _, row in family_df.iterrows():
        lunch = "Needs Lunch Box" if row['Needs_Packed_Lunch'] else "Eats Lunch at Home"
        leave = f"Leaves {row['Leave_Time']}" if row['Leave_Time'] else "Stays Home"
        health = f"({row['Health_Condition']})" if row['Health_Condition'] != "None" else ""
        family_context += f"- {row['Name']}: {leave}, {lunch} {health}\n"

    # 3. The Strict "Inventory-First" Prompt
    prompt = f"""
    You are a Strict Kitchen Inventory Manager.
    
    CURRENT PANTRY STOCK (Format: ID: Name):
    {inventory_context}
    
    FAMILY:
    {family_context}
    (Guests: {guest_count})
    
    TASK:
    Create a meal plan (Breakfast & Lunch) strictly using the CURRENT PANTRY STOCK.
    
    CRITICAL RULES:
    1. **DO NOT HALLUCINATE RECIPES.** If the pantry only has 'Rice' and 'Milk', suggest 'Rice Pudding', NOT 'Oatmeal'.
    2. **CHECK IDs:** You must include the `id` from the list above for every ingredient.
    3. **MISSING ITEMS:** If a recipe *absolutely* needs an item not in stock (e.g., Oil, Salt), set `id: -1`.
    4. **PRIORITY:** Recipes must use >80% items that actually exist in the stock list.
    
    JSON STRUCTURE:
    {{
      "plan": [
        {{
          "member_name": "Rohan",
          "meals": [
            {{
              "type": "Breakfast",
              "options": [
                {{
                  "dish_name": "Rice Porridge (Ganji)", 
                  "calories": 250,
                  "protein": "5g",
                  "ingredients": [
                    {{ "id": 12, "name": "Rice", "qty": 0.1, "unit": "kg" }}, 
                    {{ "id": 15, "name": "Milk", "qty": 0.2, "unit": "L" }}
                  ]
                }}
              ]
            }}
          ]
        }}
      ]
    }}
    """
    
    try: 
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0, # Zero temp forces it to be logical, not creative
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e: return {"error": str(e)}
# Getting family schedule
def get_family_schedule():
    """Fetches family members sorted by who leaves home earliest."""
    df = fetch_data("""
        SELECT Member_ID, Name, Role, Health_Condition, 
               DATE_FORMAT(Leave_Time, '%H:%i') as Leave_Time, 
               Needs_Packed_Lunch 
        FROM TBL_FAMILY_MEMBERS 
        ORDER BY Leave_Time ASC
    """)
    return df

# Leftover Wizard
def suggest_leftover_recipe(leftover_item, language="English"):
    if not client: return "Error: API Key missing"
    
    prompt = f"""
    I have leftover "{leftover_item}" in the fridge.
    Suggest 2 quick Indian recipes to reuse it for today's dinner or tomorrow's lunch box.
    Output in {language}.
    """
    try: 
        return client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        ).choices[0].message.content
    except Exception as e: return str(e)

# --- FAMILY MANAGEMENT HELPERS (NEW) ---

def update_family_member(member_id, name, role, health, leave_time, pack_lunch):
    """Updates an existing family member's details."""
    return execute_query(
        """UPDATE TBL_FAMILY_MEMBERS 
           SET Name=%s, Role=%s, Health_Condition=%s, Leave_Time=%s, Needs_Packed_Lunch=%s 
           WHERE Member_ID=%s""",
        (name, role, health, leave_time, pack_lunch, member_id)
    )

def delete_family_member(member_id):
    """Permanently removes a family member."""
    return execute_query("DELETE FROM TBL_FAMILY_MEMBERS WHERE Member_ID=%s", (member_id,))
# --- STEP 3: EXECUTE COOKING (NEW) ---

def process_meal_deduction(selected_meals_list):
    """
    Processes selected meals.
    Handles ID -1 as automatically 'Missing'.
    """
    conn = get_db_connection()
    if not conn: return {"success": False, "error": "DB Connection Failed"}
    
    report = []   # What we successfully deducted
    missing = []  # What we don't have (ID -1 or Low Stock)
    
    try:
        cursor = conn.cursor()
        
        # 1. Aggregate needs
        # We separate 'known_items' (ID > 0) from 'unknown_items' (ID == -1)
        needed_inventory = {} # {id: qty}
        
        for meal in selected_meals_list:
            ingredients = meal.get('ingredients', [])
            for ing in ingredients:
                i_id = int(ing.get('id', -1))
                qty = float(ing.get('qty', 0))
                name = ing.get('name', 'Unknown')
                unit = ing.get('unit', '')
                
                if i_id == -1:
                    # AI says we don't own this at all
                    missing.append(f"❌ {name} (Not in Pantry): Need {qty} {unit}")
                elif i_id > 0 and qty > 0:
                    needed_inventory[i_id] = needed_inventory.get(i_id, 0) + qty

        # 2. Process Known Inventory Items
        for i_id, needed_qty in needed_inventory.items():
            # Check Stock
            cursor.execute("SELECT Item_Name, Standard_Unit, Current_Quantity FROM TBL_PANTRY_STOCK s JOIN TBL_ITEM_CATALOG c ON s.Item_ID = c.Item_ID WHERE s.Item_ID = %s", (i_id,))
            res = cursor.fetchone()
            
            if res:
                item_name, unit, current_stock = res
                current_stock = float(current_stock)
                
                if current_stock >= needed_qty:
                    # SUCCESS: Deduct
                    new_qty = current_stock - needed_qty
                    if new_qty == 0:
                        cursor.execute("DELETE FROM TBL_PANTRY_STOCK WHERE Item_ID = %s", (i_id,))
                    else:
                        cursor.execute("UPDATE TBL_PANTRY_STOCK SET Current_Quantity = %s WHERE Item_ID = %s", (new_qty, i_id))
                    
                    # Log
                    cursor.execute("INSERT INTO TBL_LOGS (Item_ID, Action_Type, Quantity, Vendor_Name) VALUES (%s, 'CONSUME', %s, 'Chef AI')", (i_id, needed_qty))
                    
                    report.append(f"✅ Deducted {needed_qty} {unit} of {item_name}")
                else:
                    # PARTIAL / LOW STOCK
                    missing.append(f"⚠️ {item_name}: Need {needed_qty} {unit}, but only have {current_stock}")
            else:
                # ID exists in plan but not in stock table (Zombie ID?)
                missing.append(f"❌ Item ID {i_id} not found in Stock.")

        conn.commit()
        return {"success": True, "report": report, "missing": missing}

    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        if cursor: cursor.close()
        conn.close()

# --- USER MANAGEMENT & SECURITY ---

def run_user_migration():
    """Creates the Users table and seeds the default admin."""
    conn = get_db_connection()
    if not conn: 
        print("❌ DB Connection Failed during Migration")
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS TBL_USERS (
                User_ID INT AUTO_INCREMENT PRIMARY KEY,
                Username VARCHAR(50) UNIQUE NOT NULL,
                Password_Hash VARCHAR(64) NOT NULL,
                Full_Name VARCHAR(100),
                Role VARCHAR(20) DEFAULT 'User',
                Created_At DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Check if admin exists
        cursor.execute("SELECT User_ID FROM TBL_USERS WHERE Username = 'admin'")
        if not cursor.fetchone():
            default_hash = hashlib.sha256("password123".encode()).hexdigest()
            cursor.execute(
                "INSERT INTO TBL_USERS (Username, Password_Hash, Full_Name, Role) VALUES (%s, %s, %s, %s)",
                ('admin', default_hash, 'System Administrator', 'Admin')
            )
            print("✅ Default admin user created.")
            
        conn.commit()
    except Exception as e:
        print(f"❌ Migration Error: {e}")
    finally:
        if cursor: cursor.close()
        conn.close()

def verify_login(username, password):
    """
    Verifies credentials against the database.
    Returns: (Success_Bool, Message_or_UserDict)
    """
    # 1. Clean inputs
    clean_user = username.strip()
    clean_pass = password.strip()
    
    conn = get_db_connection()
    if not conn:
        return False, "Database Connection Failed"

    try:
        cursor = conn.cursor(dictionary=True) # Use dictionary cursor for easier access
        
        # 2. Check if user exists first (Debugging Step)
        cursor.execute("SELECT User_ID, Password_Hash, Full_Name, Role FROM TBL_USERS WHERE Username=%s", (clean_user,))
        user_record = cursor.fetchone()
        
        if not user_record:
            return False, "User does not exist."
            
        # 3. Check Hash
        input_hash = hashlib.sha256(clean_pass.encode()).hexdigest()
        stored_hash = user_record['Password_Hash']
        
        if input_hash == stored_hash:
            return True, user_record
        else:
            return False, "Incorrect Password."

    except Exception as e:
        return False, f"Login Error: {str(e)}"
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

def create_new_user(username, password, full_name, role="User"):
    """Creates a new user with a hashed password."""
    clean_user = username.strip()
    clean_pass = password.strip()
    clean_name = full_name.strip()

    # Check if username exists
    check = fetch_data("SELECT User_ID FROM TBL_USERS WHERE Username=%s", (clean_user,))
    if not check.empty:
        return False, "Username already exists."
        
    pwd_hash = hashlib.sha256(clean_pass.encode()).hexdigest()
    
    success, msg = execute_query(
        "INSERT INTO TBL_USERS (Username, Password_Hash, Full_Name, Role) VALUES (%s, %s, %s, %s)",
        (clean_user, pwd_hash, clean_name, role)
    )
    return success, msg