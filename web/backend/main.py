from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="Job Application Agent API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Job Application Agent API is running"}

@app.get("/api/stats")
async def get_stats():
    # Placeholder for actual stats from DB/Agent
    return {
        "applied_today": 0,
        "success_rate": 0,
        "active_jobs_in_queue": 0,
        "system_status": "idle"
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
