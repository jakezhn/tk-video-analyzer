import asyncio
import os
import subprocess
import yt_dlp
import whisper
import ffmpeg
import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector
from scenedetect.frame_timecode import FrameTimecode
import cv2

# Add Homebrew's ffmpeg to the path
# This is crucial for libraries like Whisper that call ffmpeg via subprocess
ffmpeg_path = "/opt/homebrew/bin"
if ffmpeg_path not in os.environ["PATH"]:
    os.environ["PATH"] = f"{ffmpeg_path}:{os.environ['PATH']}"

# Load environment variables from .env file
load_dotenv()

# Configure the generative AI model
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment variables. Please set it in a .env file.")
genai.configure(api_key=GOOGLE_API_KEY)

TEMP_STORAGE_PATH = os.path.abspath("./temp_storage")

# Load models once when the server starts
# Using the 'base' model is a good balance of speed and accuracy for an MVP.
whisper_model = whisper.load_model("base")
llm_model = genai.GenerativeModel('gemini-1.5-flash')

async def _run_analysis_on_local_file(job_id: str, video_path: str):
    """
    Runs the core analysis on a local video file.
    """
    job_dir = os.path.join(TEMP_STORAGE_PATH, job_id)
    status_file = os.path.join(job_dir, "status.txt")

    try:
        # Step 2: Extract audio from video
        with open(status_file, "w") as f:
            f.write("extracting_audio")
        audio_path = await asyncio.to_thread(_extract_audio, video_path, job_dir)

        # Step 3: Transcribe audio
        with open(status_file, "w") as f:
            f.write("transcribing")
        transcript = await asyncio.to_thread(_transcribe_audio, audio_path)

        # Step 4: Extract keyframes
        with open(status_file, "w") as f:
            f.write("extracting_frames")
        keyframes_dir = os.path.join(job_dir, "keyframes")
        os.makedirs(keyframes_dir, exist_ok=True)
        await asyncio.to_thread(_extract_keyframes, video_path, job_dir)

        # Step 5: Generate report with LLM
        with open(status_file, "w") as f:
            f.write("generating_report")
        report = await _generate_report(transcript, keyframes_dir)

        # Step 6: Save the final report
        report_path = os.path.join(job_dir, "report.md")
        with open(report_path, "w") as f:
            f.write(report)
        
        with open(status_file, "w") as f:
            f.write("complete")

    except Exception as e:
        error_message = f"Error during analysis: {e}"
        with open(status_file, "w") as f:
            f.write(f"error: {error_message}")
        print(f"Error in job {job_id}: {error_message}")
        # Re-raise the exception to be caught by the main endpoint handler
        raise

async def run_analysis_pipeline(job_id: str, video_url: str):
    """
    The main analysis pipeline for video URLs.
    """
    job_dir = os.path.join(TEMP_STORAGE_PATH, job_id)
    status_file = os.path.join(job_dir, "status.txt")

    # URL validation: Must be a direct link to a video or a note (image post).
    # Rejects user profiles, search pages, etc.
    if not ("/video/" in video_url or "/note/" in video_url):
        error_message = "Unsupported URL. Please provide a direct link to a TikTok or Douyin video, not a user profile or search page."
        print(f"Validation Error for job {job_id}: {error_message}")
        with open(status_file, "w") as f:
            f.write(f"Error: {error_message}")
        return

    try:
        # Step 1: Download the video
        with open(status_file, "w") as f:
            f.write("downloading")
        video_path = await asyncio.to_thread(_download_video, video_url, job_dir)
        if not video_path:
            raise ValueError("Failed to download video.")

        # Run the core analysis on the downloaded file
        await _run_analysis_on_local_file(job_id, video_path)

    except Exception as e:
        # This will catch errors from both download and analysis steps
        error_message = f"An error occurred: {e}"
        with open(status_file, "w") as f:
            f.write(f"error: {error_message}")
        print(f"Error in job {job_id}: {error_message}")

def _download_video(url: str, download_path: str) -> str:
    """Downloads a video from the given URL to the specified path."""
    # Find and remove existing video files to ensure a fresh download
    for f in os.listdir(download_path):
        if f.startswith('video.'):
            os.remove(os.path.join(download_path, f))

    cookie_file = os.path.join(os.path.dirname(__file__), "cookies.txt")

    ydl_opts = {
        'format': 'best',
        'outtmpl': os.path.join(download_path, 'video.%(ext)s'),
        'quiet': True,
    }

    if os.path.exists(cookie_file):
        ydl_opts['cookiefile'] = cookie_file
        print(f"INFO: Using cookie file at {cookie_file}")
    else:
        print("WARNING: cookies.txt not found. Some videos may fail to download.")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

def _extract_audio(video_path: str, job_dir: str) -> str:
    """Extracts audio from a video file and returns the path to the audio file."""
    audio_path = os.path.join(job_dir, "audio.mp3")
    try:
        # Use ffmpeg-python to extract audio. This is more robust than subprocess.
        (ffmpeg.input(video_path)
         .output(audio_path, acodec="libmp3lame", audio_bitrate="192k", vn=None)
         .run(capture_stdout=True, capture_stderr=True, overwrite_output=True))
    except ffmpeg.Error as e:
        print("ffmpeg-python error during audio extraction:")
        print(e.stderr.decode())
        raise
    return audio_path

def _transcribe_audio(audio_path: str) -> str:
    """Transcribes the audio from the given path and cleans up the audio file."""
    try:
        result = whisper_model.transcribe(audio_path, fp16=False)
        transcript = result["text"]
        # Save the transcript to a file for debugging/caching
        transcript_path = os.path.splitext(audio_path)[0] + ".txt"
        with open(transcript_path, "w") as f:
            f.write(transcript)
        return transcript
    finally:
        # Clean up the temporary audio file
        if os.path.exists(audio_path):
            os.remove(audio_path)

def _extract_keyframes(video_path: str, job_dir: str) -> list[str]:
    """Detects scenes and saves the middle frame of each scene as a keyframe."""
    keyframes_dir = os.path.join(job_dir, "keyframes")
    os.makedirs(keyframes_dir, exist_ok=True)

    video = open_video(video_path)
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector())
    scene_manager.detect_scenes(video=video, show_progress=False)
    scene_list = scene_manager.get_scene_list()

    saved_keyframes = []
    for i, scene in enumerate(scene_list):
        start_frame, end_frame = scene
        middle_frame_num = int(start_frame.get_frames() + (end_frame.get_frames() - start_frame.get_frames()) / 2)

        video.seek(middle_frame_num)
        frame_image = video.read()

        if frame_image is not None:
            keyframe_path = os.path.join(keyframes_dir, f"keyframe_{i+1:03d}.jpg")
            cv2.imwrite(keyframe_path, frame_image)
            saved_keyframes.append(keyframe_path)
            
    # The VideoStream object is automatically closed when it goes out of scope.
    return saved_keyframes

async def _generate_report(transcript: str, keyframes_dir: str) -> str:
    """Generates a detailed report using the LLM, based on transcript and keyframes."""

    image_parts = []
    # Find all keyframe images in the directory
    keyframe_files = sorted([os.path.join(keyframes_dir, f) for f in os.listdir(keyframes_dir) if f.endswith('.jpg')])
    for img_path in keyframe_files:
        try:
            img = Image.open(img_path)
            image_parts.append(img)
        except IOError:
            print(f"Could not open image file {img_path}, skipping.")
            continue

    prompt_parts = [
        "You are a world-class TikTok video analyst. Your task is to analyze the provided materials (transcript and keyframes) of a TikTok video and generate a comprehensive report in Markdown format.",
        "The report must follow these language requirements:",
        "The final report will have two parts: the speech transcript in its original language, and all other analysis in Simplified Chinese.",
        "\n---",
        "\n\n**1. Full Speech Transcript:**",
        f'\n> "{transcript}"',
        "\n\n**2. 故事板和拍摄脚本:**",
        "请根据提供的关键帧和文字记录，创建一个专业级的故事板和拍摄脚本。**必须使用标准的GitHub Flavored Markdown表格格式**，包含表头和分隔线。表格应包含以下列：`场景`、`关键帧描述`、`视觉元素`、`人物动作`、`镜头语言`、`音频/对话`、`音效/背景音乐`。直接回答内容，不需要其他说明。",
        *image_parts,
        "\n\n**3. 深入分析:**",
        "请以资深内容策略师的视角，对视频进行多维度的深入分析。分析应包括但不限于以下方面：内容创意、叙事结构、视觉呈现、情感共鸣和传播潜力。请务必结合具体画面和对话进行讨论。直接回答内容，不需要其他说明。",
    ]

    try:
        request_options = {"timeout": 600}
        response = await llm_model.generate_content_async(
            prompt_parts, request_options=request_options
        )
        return response.text
    except Exception as e:
        print(f"Error generating report with LLM: {e}")
        # Fallback to a simple report if LLM fails
        return f"# LLM Analysis Failed\n\nError: {e}\n\n## Transcript\n{transcript}"



