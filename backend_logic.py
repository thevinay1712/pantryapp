import mysql.connector
import pandas as pd
import os
import base64
import json
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from groq import Groq

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

# --- SMART INVENTORY (PHASE 3) ---

def process_smart_deduction(bom_list):
    deduction_report = []
    missing_items = []
    conn = get_db_connection()
    if not conn: return {"error": "DB Connection Failed"}
    
    try:
        cursor = conn.cursor()
        for item in bom_list:
            ai_name = item['item_name']
            needed_qty = float(item['quantity'])
            
            # Using LIKE matching to find the item in DB
            cursor.execute("SELECT Item_ID, Item_Name, Standard_Unit FROM TBL_ITEM_CATALOG WHERE Item_Name LIKE %s LIMIT 1", (f"%{ai_name}%",))
            match = cursor.fetchone()
            
            if match:
                item_id, db_name, unit = match
                cursor.execute("SELECT Current_Quantity FROM TBL_PANTRY_STOCK WHERE Item_ID = %s", (item_id,))
                stock_res = cursor.fetchone()
                
                if stock_res:
                    current_qty = float(stock_res[0])
                    actual_deduct = min(current_qty, needed_qty)
                    new_qty = current_qty - actual_deduct
                    status = f"Partial (Needed {needed_qty})" if needed_qty > current_qty else "Success"
                    
                    if actual_deduct > 0:
                        cursor.execute("INSERT INTO TBL_LOGS (Item_ID, Action_Type, Quantity, Vendor_Name) VALUES (%s, 'CONSUME', %s, 'AI Chef Menu')", (item_id, actual_deduct))
                        
                        if new_qty == 0: cursor.execute("DELETE FROM TBL_PANTRY_STOCK WHERE Item_ID = %s", (item_id,))
                        else: cursor.execute("UPDATE TBL_PANTRY_STOCK SET Current_Quantity = %s WHERE Item_ID = %s", (new_qty, item_id))
                        
                        deduction_report.append({"Item": db_name, "Deducted": actual_deduct, "Unit": unit, "Status": status})
                else: missing_items.append(f"{db_name} (No Stock)")
            else: missing_items.append(f"{ai_name} (Unknown Item)")
        
        conn.commit()
        return {"success": True, "report": deduction_report, "missing": missing_items}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        if cursor: cursor.close()
        conn.close()

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

def generate_morning_plan(inventory_list, family_df, guest_count=0, language="English"):
    if not client: return "Error: API Key missing"
    
    # 1. Construct Family Context
    family_context = ""
    total_people = len(family_df) + guest_count
    
    for _, row in family_df.iterrows():
        lunch_status = "Needs Packed Lunch" if row['Needs_Packed_Lunch'] else "Eats Lunch at Home"
        leave_status = f"Leaves at {row['Leave_Time']}" if row['Leave_Time'] else "Stays Home"
        health = f"(Health: {row['Health_Condition']})" if row['Health_Condition'] != "None" else ""
        
        family_context += f"- {row['Name']} ({row['Role']}): {leave_status}, {lunch_status} {health}\n"

    # 2. Guest Logic
    guest_context = f"Note: There are {guest_count} extra guests today." if guest_count > 0 else ""

    # 3. The Prompt
    prompt = f"""
    You are a Smart Indian Kitchen Assistant.
    
    CURRENT INVENTORY:
    {inventory_list}
    
    FAMILY SCHEDULE (Who leaves first needs food first!):
    {family_context}
    {guest_context}
    
    TASK:
    Plan the 'Morning Rush' (Breakfast & Lunch).
    1. Suggest ONE Breakfast dish and ONE Lunch dish that uses available inventory.
    2. Prioritize the person leaving earliest (e.g., if Son leaves at 7:30, food must be ready by 7:00).
    3. Suggest modifications for Health Issues (e.g., "Less sugar for Dad").
    4. Calculate Total Quantities (e.g., "Total Idlis: 12 + 4 for guests = 16").
    
    OUTPUT FORMAT:
    Output the response in {language} language. Use simple, clear bullet points.
    """
    
    try: 
        return client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        ).choices[0].message.content
    except Exception as e: return str(e)

# UPDATED FUNCTION WITH INVENTORY CONTEXT
def get_menu_ingredients_for_deduction(menu, customers, inventory_list=""):
    if not client: return {"error": "Key missing"}
    
    # Enhanced prompt to ensure ALL items are caught and matched to inventory
    prompt = f"""
    You are a Kitchen Inventory Manager.
    
    MENU TO PREPARE:
    "{menu}"
    
    YOUR CURRENT PANTRY INVENTORY:
    "{inventory_list}"
    
    TASK:
    1. Extract EVERY ingredient required for EACH course in the menu (Appetizers, Mains, Sides, Desserts, etc.).
    2. Estimate total quantity needed for {customers} guests.
    3. IMPORTANT: If an ingredient exists in the PANTRY INVENTORY list above, use THAT EXACT NAME (e.g., if Pantry has 'Tomato', do NOT use 'Tomatoes').
    4. If an item is not in the pantry, use a standard name.
    
    Return JSON format:
    {{'ingredients': [{{ 'item_name': 'Exact Pantry Name', 'quantity': 0.5 }}]}}
    """
    try: return json.loads(client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}], temperature=0, response_format={"type": "json_object"}).choices[0].message.content)
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
