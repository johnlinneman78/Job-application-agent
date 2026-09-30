import requests
import json

base_url = "http://localhost:8000"
email = "agent@test.com"
password = "password123"

# 1. Login
login_res = requests.post(f"{base_url}/api/auth/login", json={"email": email, "password": password})
if login_res.status_code != 200:
    print(f"Login failed: {login_res.text}")
    exit(1)

token = login_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. Trigger Applications
print("Triggering applications...")
deploy_res = requests.post(f"{base_url}/api/applications/start", headers=headers)
print(f"Deploy Response: {deploy_res.status_code} - {deploy_res.text}")

# 3. Monitor stats
import time
for _ in range(5):
    time.sleep(10)
    stats_res = requests.get(f"{base_url}/api/applications/stats", headers=headers)
    print(f"Current Stats: {stats_res.json()}")
