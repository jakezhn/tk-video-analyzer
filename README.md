# TikTok AI Analyzer

This project is an AI-powered video analyzer that provides a detailed analysis of a video from its URL. It currently supports both TikTok and Douyin. The backend is built with FastAPI and the frontend is a React application.

## Local Development Setup

Follow these instructions to run both the backend and frontend servers locally.

### Backend Setup

1.  **Navigate to Project Root:**
    Open your terminal in the root directory of the project.

2.  **Create and Activate Virtual Environment:**
    ```sh
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```sh
    pip install -r backend/requirements.txt
    ```

4.  **Set Up Environment Variables:**
    Create a file named `.env` inside the `backend` directory (`/backend/.env`) and add your Google API key:
    ```
    GOOGLE_API_KEY=your_google_api_key_here
    ```

5.  **Run the Backend Server:**
    From the **project root directory**, run:
    ```sh
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
    ```
    The backend will be running at `http://localhost:8000`.

### Frontend Setup

1.  **Navigate to Frontend Directory:**
    In a new terminal window, navigate to the `frontend` directory:
    ```sh
    cd frontend
    ```

2.  **Install Dependencies:**
    *Note: This project requires Node.js and npm.*
    ```sh
    npm install
    ```

3.  **Run the Frontend Server:**
    ```sh
    npm run dev
    ```
    The frontend will be running at `http://localhost:5173` (or the next available port).

curl -X POST -F "video=@backend/test/test-vid1.mp4" http://127.0.0.1:8000/analyze-upload