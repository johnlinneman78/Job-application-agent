import json
import bcrypt
from pathlib import Path
from datetime import datetime

# Paths
WORKSPACE_ROOT = Path(__file__).resolve().parent
DB_DIR = WORKSPACE_ROOT / "backend" / "data"
USERS_FILE = DB_DIR / "users.json"

def seed_user():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    
    users = {}
    if USERS_FILE.exists():
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
            
    email = "test@example.com"
    password = "password123"
    
    # Hash password
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    users[email] = {
        "email": email,
        "full_name": "Test User",
        "password_hash": hashed,
        "created_at": datetime.now().isoformat(),
        "is_active": True
    }
    
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)
        
    print(f"Seeded user: {email} with password: {password}")

if __name__ == "__main__":
    seed_user()
