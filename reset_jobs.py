import json
from pathlib import Path

JOBS_FILE = Path("backend/data/jobs.json")

def reset_jobs():
    if not JOBS_FILE.exists():
        print("Jobs file not found.")
        return
    
    with open(JOBS_FILE, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    if "agent@test.com" in db:
        for job in db["agent@test.com"]:
            job["status"] = "queued"
        
        with open(JOBS_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=2)
        print("Successfully reset all jobs for agent@test.com to 'queued'.")
    else:
        print("User agent@test.com not found in jobs db.")

if __name__ == "__main__":
    reset_jobs()
