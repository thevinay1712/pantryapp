from backend_logic import get_db_connection
import hashlib

def force_fix_users():
    print("🔌 Connecting to database...")
    conn = get_db_connection()
    if not conn:
        print("❌ Failed to connect. Check .env file.")
        return

    cursor = conn.cursor()
    
    try:
        # 1. Drop the old/broken table
        print("🔨 Dropping broken TBL_USERS table...")
        cursor.execute("DROP TABLE IF EXISTS TBL_USERS")
        
        # 2. Recreate it with the correct columns (including Full_Name)
        print("🏗️ Re-creating TBL_USERS with correct schema...")
        cursor.execute("""
            CREATE TABLE TBL_USERS (
                User_ID INT AUTO_INCREMENT PRIMARY KEY,
                Username VARCHAR(50) UNIQUE NOT NULL,
                Password_Hash VARCHAR(64) NOT NULL,
                Full_Name VARCHAR(100), 
                Role VARCHAR(20) DEFAULT 'User',
                Created_At DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 3. Create the Default Admin
        print("👤 Creating Admin user...")
        # Hash for 'password123'
        admin_pass = hashlib.sha256("password123".encode()).hexdigest()
        
        cursor.execute(
            "INSERT INTO TBL_USERS (Username, Password_Hash, Full_Name, Role) VALUES (%s, %s, %s, %s)",
            ('admin', admin_pass, 'System Administrator', 'Admin')
        )
        
        conn.commit()
        print("✅ SUCCESS! Table fixed.")
        print("👉 You can now login with: admin / password123")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    force_fix_users()