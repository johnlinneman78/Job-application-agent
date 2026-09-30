import requests
import json

BASE_URL = "http://localhost:8000"
EMAIL = "agent@test.com"
PASSWORD = "password123"

def trigger_applications():
    # 1. Login
    login_url = f"{BASE_URL}/api/auth/login"
    login_data = {"email": EMAIL, "password": PASSWORD}
    
    try:
        response = requests.post(login_url, json=login_data)
        response.raise_for_status()
        token_data = response.json()
        token = token_data["access_token"]
        print(f"Logged in successfully. Token obtained.")
        
        # 2. Start applications
        start_url = f"{BASE_URL}/api/applications/start"
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.post(start_url, headers=headers)
        response.raise_for_status()
        print(f"Applications started: {response.json()}")
        
    except Exception as e:
        print(f"Failed to trigger applications: {e}")

if __name__ == "__main__":
    trigger_applications()
