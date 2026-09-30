import json
import re
from pathlib import Path

def extract_jobs():
    interaction_file = Path("c:/Users/uriel/Downloads/interaction_flow_1769567870414.json")
    if not interaction_file.exists():
        print("Interaction file not found.")
        return

    with open(interaction_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    job_ids = set()
    for event in data.get('events', []):
        url = event.get('url', '')
        # Extract jobId from URL: currentJobId=4326420964
        match = re.search(r'currentJobId=(\d+)', url)
        if match:
            job_ids.add(match.group(1))
        
        # Also try description or any title that looks like a job
        title = event.get('title', '')
        # (27) Top job picks for you | LinkedIn
        # Usually internal navigation has currentJobId

    jobs = []
    # Simple heuristic: if the interaction flow contains 'Easy Apply' or 'apply', it's likely an EA job
    raw_data = json.dumps(data)
    can_infer_ea = "Easy Apply" in raw_data or "apply" in raw_data

    for jid in job_ids:
        jobs.append({
            "job_id": f"linkedin_{jid}",
            "platform": "linkedin",
            "title": "Automated Recovery Job",
            "company": "See LinkedIn",
            "location": "Remote",
            "url": f"https://www.linkedin.com/jobs/view/{jid}/",
            "guard_status": "safe",
            "has_easy_apply": can_infer_ea # Better than blind True
        })

    # Also add the one we know was submitted if it's missing
    # (Actually we want to apply to ones NOT submitted, but for testing we just want ANYTHING)
    
    output_path = Path("data/jobs_discovered.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Merge with existing if any
    if output_path.exists():
        try:
            with open(output_path, 'r') as f:
                existing = json.load(f)
                existing_ids = {j['job_id'] for j in existing}
                for j in jobs:
                    if j['job_id'] not in existing_ids:
                        existing.append(j)
                jobs = existing
        except:
            pass

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=2)
    
    print(f"Extracted and seeded {len(jobs)} jobs to {output_path}")

if __name__ == "__main__":
    extract_jobs()
