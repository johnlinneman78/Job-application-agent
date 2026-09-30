import requests
try:
    r = requests.get("http://localhost:8000/api/health")
    print(f"Status: {r.status_code}")
    print(f"Body: {r.json()}")
except Exception as e:
    print(f"Error: {e}")
