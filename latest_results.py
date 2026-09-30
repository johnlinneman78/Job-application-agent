import json
from pathlib import Path

def main():
    path = Path("data/applications_submitted.json")
    if not path.exists():
        print("File not found")
        return
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print(f"Total applications in file: {len(data)}")
    print("\nLATEST 5 ENTRIES:")
    for item in data[-5:]:
        job = item.get("job", {})
        job_id = job.get("job_id", "Unknown")
        status = item.get("status", "Unknown")
        error = item.get("error_message", "None")
        print(f"ID: {job_id} | Status: {status} | Error: {error}")

if __name__ == "__main__":
    main()
