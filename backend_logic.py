import mysql.connector
import pandas as pd
from groq import Groq
import json
import base64
import holidays

# --- CONFIGURATION ---
# REPLACE WITH YOUR ACTUAL CREDENTIALS
DB_CONFIG = {
    'host': 'db.filess.io',         
    'user': 'your_user_here',        
    'password': 'your_password_here', 
    'database': 'your_db_name_here',    
    'port': 3306
}

GROQ_API_KEY = "your_groq_api_key_here" 
client = Groq(api_key=GROQ_API_KEY)

# --- DATABASE HELPERS ---
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def fetch_data(query):
    """
    Fetches data and automatically removes duplicate columns 
    to prevent Streamlit errors.
    """
    conn = get_db_connection()
    df = pd.read_sql(query, conn)
    conn.close()
    # FIX: Remove duplicate columns (like category_id appearing twice)
    df = df.loc[:, ~df.columns.duplicated()]
    return df

def execute_query(query, params=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    conn.close()

# --- NEW: DELETE FUNCTION ---
def delete_item_by_name(item_name):
    query = "DELETE FROM TBL_PANTRY WHERE item_name = %s"
    execute_query(query, (item_name,))

# --- UNIT FORMATTER ---
def format_quantity(qty, unit_type):
    if unit_type == 'discrete':
        return int(round(qty))
    return round(float(qty), 2)

# --- AI FUNCTIONS ---

# 1. BILL SCANNER (Uses Vision Model)
# Note: Switched to 11b-vision-preview as 90b is often rate-limited/deprecated
def process_bill_image(image_bytes):
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    prompt = """
    Analyze this bill. Extract food items. Return ONLY JSON list: 
    [{"item_name": "Milk", "quantity": 2, "unit": "L"}]
    Ignore prices.
    """
    completion = client.chat.completions.create(
        model="llama-3.2-11b-vision-preview", 
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                ],
            }
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )
    return json.loads(completion.choices[0].message.content)

# 2. MENU GENERATOR (Uses Text Model)
def generate_menu(available_items, chefs, time_limit, customers):
    inventory_str = ", ".join([f"{r['item_name']} ({r['quantity']} {r['unit_label']})" for _, r in available_items.iterrows()])
    chefs_str = ", ".join([f"{r['name']} (Spec: {r['specialty_dish']})" for _, r in chefs.iterrows()])
    
    prompt = f"""
    You are a Head Chef AI. 
    Current Inventory: {inventory_str}
    Available Chefs: {chefs_str}
    Constraints: Must serve {customers} people within {time_limit} minutes.
    Suggest 3 dishes. Output JSON format:
    {{ "recommendations": [{{"dish_name": "...", "assigned_chef": "...", "estimated_time": "...", "ingredients_used": ["item1"]}}] }}
    """
    chat_completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile", 
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(chat_completion.choices[0].message.content)

# 3. CUSTOMER PREDICTION
def predict_customers(date_input):
    df = fetch_data("SELECT date as ds, customer_count as y FROM TBL_SALES_LOG")
    india_holidays = holidays.India()
    
    # Simple logic if not enough data
    if len(df) < 5:
        return {"prediction": 15, "is_holiday": date_input in india_holidays, "holiday_name": india_holidays.get(date_input, "None")}
    
    # (Prophet logic omitted for brevity, keeping simple fallback for now)
    # In full version, put Prophet code here.
    return {"prediction": 25, "is_holiday": date_input in india_holidays, "holiday_name": india_holidays.get(date_input, "None")}