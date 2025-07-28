import asyncio
import uuid
import os
import shutil
from typing import Dict

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from analyzer import run_analysis_pipeline, _run_analysis_on_local_file

app = FastAPI()

# --- CORS Middleware ---
# Allow all origins for development. In production, restrict to the frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# --- App State and Models ---
TEMP_STORAGE_PATH = "temp_storage"

class AnalyzeRequest(BaseModel):
    url: str

# In-memory store for SSE connections
class SSEManager:
    def __init__(self):
        self.connections: Dict[str, asyncio.Queue] = {}

    async def add_connection(self, job_id: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.connections[job_id] = queue
        return queue

    async def send_event(self, job_id: str, message: str):
        if job_id in self.connections:
            await self.connections[job_id].put(message)

    def remove_connection(self, job_id: str):
        if job_id in self.connections:
            del self.connections[job_id]

sse_manager = SSEManager()

# Ensure the temporary storage directory exists
if not os.path.exists(TEMP_STORAGE_PATH):
    os.makedirs(TEMP_STORAGE_PATH)

# --- Analysis Pipeline Wrappers ---
async def run_analysis_and_notify(job_id: str, url: str):
    """Wrapper for URL-based analysis."""
    try:
        await run_analysis_pipeline(job_id, url)
        await sse_manager.send_event(job_id, "complete")
    except Exception as e:
        print(f"Error in job {job_id}: {e}")
        await sse_manager.send_event(job_id, "error")

async def run_local_file_analysis_and_notify(job_id: str, video_path: str):
    """Wrapper for local file analysis."""
    try:
        await _run_analysis_on_local_file(job_id, video_path)
        await sse_manager.send_event(job_id, "complete")
    except Exception as e:
        print(f"Error in job {job_id}: {e}")
        await sse_manager.send_event(job_id, "error")


# --- API Endpoints ---
@app.post("/analyze")
async def analyze_video_url(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Analyzes a video from a URL."""
    job_id = str(uuid.uuid4())
    # Create the job directory immediately to prevent race conditions
    os.makedirs(os.path.join(TEMP_STORAGE_PATH, job_id), exist_ok=True)
    background_tasks.add_task(run_analysis_and_notify, job_id, request.url)
    return {"job_id": job_id}

@app.post("/analyze-upload")
async def analyze_video_upload(background_tasks: BackgroundTasks, video: UploadFile = File(...) ):
    """Analyzes a video from an uploaded file."""
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(TEMP_STORAGE_PATH, job_id)
    os.makedirs(job_dir, exist_ok=True)

    # Save the uploaded file to the job directory.
    # Using a consistent name like 'video.mp4' simplifies downstream processing.
    video_path = os.path.join(job_dir, "video.mp4")

    try:
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
    finally:
        video.file.close()
    
    background_tasks.add_task(run_local_file_analysis_and_notify, job_id, video_path)
    return {"job_id": job_id}

@app.get("/stream/{job_id}")
async def stream_status(request: Request, job_id: str):
    queue = await sse_manager.add_connection(job_id)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                # Wait for a message
                message = await queue.get()
                yield {"event": "message", "data": message}
                # If the job is done, stop sending events
                if message in ["complete", "error"]:
                    break
        finally:
            sse_manager.remove_connection(job_id)

    return EventSourceResponse(event_generator())

@app.get("/results/{job_id}/report")
async def get_report(job_id: str):
    report_path = os.path.join(TEMP_STORAGE_PATH, job_id, "report.md")
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Report not found.")
    return FileResponse(report_path, media_type='text/markdown')

@app.get("/results/{job_id}/video")
async def get_video(job_id: str):
    video_path = os.path.join(TEMP_STORAGE_PATH, job_id, "video.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found.")
    return FileResponse(video_path, media_type='video/mp4')

@app.get("/")
def read_root():
    return {"message": "TikTok Video Analyzer Backend is running."}
