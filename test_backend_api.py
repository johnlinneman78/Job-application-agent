import requests
import json
import os

BASE_URL = "http://localhost:8000"

def test_registration():
    url = f"{BASE_URL}/api/auth/register"
    data = {
        "email": "agent@test.com",
        "password": "password123",
        "full_name": "Agent Alpha"
    }
    response = requests.post(url, json=data)
    if response.status_code == 400: # Already registered
        return test_login()
    print(f"Registration status: {response.status_code}")
    return response.json()

def test_login():
    url = f"{BASE_URL}/api/auth/login"
    data = {
        "email": "agent@test.com",
        "password": "password123"
    }
    response = requests.post(url, json=data)
    print(f"Login status: {response.status_code}")
    return response.json()

def test_update_config(token):
    url = f"{BASE_URL}/api/config"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "personal_info": {
            "name": "Agent Alpha",
            "email": "agent@test.com",
            "phone": "555-0199",
            "address": "123 Automation Way",
            "city": "Cyber City",
            "state": "WA",
            "zip_code": "98001",
            "years_of_experience": 5,
            "linkedin_url": "https://linkedin.com/in/agentalpha",
            "portfolio_url": "https://agentalpha.dev"
        },
        "search": {
            "keywords": ["software engineer", "full stack"],
            "locations": ["Remote"],
            "seniority": ["Entry Level", "Mid Level"],
            "platforms": ["linkedin"],
            "max_applications": 5,
            "posted_within_days": 7
        },
        "application": {
            "min_delay": 5,
            "max_delay": 15,
            "auto_answer_screening": True
        },
        "screening_answers": {
            "work_authorization": "Yes",
            "require_sponsorship": "No",
            "remote_preference": "Yes",
            "willing_to_relocate": "No",
            "expected_salary": "150000",
            "start_date": "Immediately"
        }
    }
    response = requests.put(url, json=data, headers=headers)
    print(f"Update Config status: {response.status_code}")
    return response.json()

def test_upload_resume(token):
    url = f"{BASE_URL}/api/resume/upload"
    headers = {"Authorization": f"Bearer {token}"}
    # Need to create a real dummy PDF if possible, or just send the text one
    with open("resume.pdf", "rb") as f:
        files = {"file": ("resume.pdf", f, "application/pdf")}
        response = requests.post(url, headers=headers, files=files)
    print(f"Upload Resume status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.json()

def test_search(token):
    url = f"{BASE_URL}/api/jobs/search"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(url, headers=headers)
    print(f"Search status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.json()

if __name__ == "__main__":
    try:
        if not os.path.exists("resume.pdf"):
            with open("resume.pdf", "w") as f:
                f.write("Dummy Resume Content")
        
        auth_data = test_registration()
        token = auth_data.get("access_token")
        
        if token:
            test_update_config(token)
            test_upload_resume(token)
            test_search(token)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
