import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Play, Loader, Bot, Send } from 'lucide-react';
import VideoPlayer from './components/VideoPlayer';

const API_BASE_URL = 'http://127.0.0.1:8000';

function App() {
  const [url, setUrl] = useState('');
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState('idle'); // idle, processing, complete, error
  const [report, setReport] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const eventSourceRef = useRef(null);

  useEffect(() => {
    if (jobId && status === 'processing') {
      // Close any existing connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const es = new EventSource(`${API_BASE_URL}/stream/${jobId}`);
      eventSourceRef.current = es;

      es.onmessage = (event) => {
        const newStatus = event.data;
        if (newStatus === 'complete') {
          setStatus('complete');
          fetchResults(jobId);
          es.close();
        } else if (newStatus === 'error') {
          setStatus('error');
          es.close();
        }
      };

      es.onerror = () => {
        setStatus('error');
        es.close();
      };
    }

    // Cleanup on component unmount
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [jobId, status]);

  const fetchResults = async (currentJobId) => {
    try {
      const reportRes = await fetch(`${API_BASE_URL}/results/${currentJobId}/report`);
      const reportText = await reportRes.text();
      setReport(reportText);

      const videoRes = await fetch(`${API_BASE_URL}/results/${currentJobId}/video`);
      const videoBlob = await videoRes.blob();
      setVideoUrl(URL.createObjectURL(videoBlob));
    } catch (error) {
      console.error("Failed to fetch results:", error);
      setStatus('error');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url) return;

    setStatus('processing');
    setReport('');
    setVideoUrl('');
    setJobId(null);

    try {
      const response = await fetch(`${API_BASE_URL}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      const data = await response.json();
      setJobId(data.job_id);
    } catch (error) {
      console.error("Failed to start analysis:", error);
      setStatus('error');
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white font-sans flex flex-col items-center p-4 sm:p-8">
      <header className="w-full max-w-4xl text-center mb-8">
        <h1 className="text-4xl sm:text-5xl font-bold text-purple-400 flex items-center justify-center gap-3">
          <Bot size={48} /> TikTok AI Analyzer
        </h1>
        <p className="text-gray-400 mt-2">Paste a TikTok URL to get a deep-dive analysis powered by AI.</p>
      </header>

      <main className="w-full max-w-4xl">
        <form onSubmit={handleSubmit} className="flex gap-2 mb-8">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.tiktok.com/@user/video/123..."
            className="flex-grow bg-gray-800 border border-gray-700 rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-purple-500 transition"
            disabled={status === 'processing'}
          />
          <button
            type="submit"
            className="bg-purple-600 hover:bg-purple-700 rounded-lg px-6 py-3 flex items-center justify-center gap-2 transition disabled:bg-gray-600 disabled:cursor-not-allowed"
            disabled={status === 'processing'}
          >
            {status === 'processing' ? <Loader className="animate-spin" /> : <Send />}
            <span className="hidden sm:inline">Analyze</span>
          </button>
        </form>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 min-h-[50vh]">
          {status === 'idle' && (
            <div className="text-center text-gray-500">Your analysis report will appear here.</div>
          )}
          {status === 'processing' && (
            <div className="flex flex-col items-center justify-center h-full gap-4">
              <Loader size={48} className="animate-spin text-purple-400" />
              <p className="text-lg">AI is analyzing the video... this may take a few minutes.</p>
            </div>
          )}
          {status === 'error' && (
            <div className="text-center text-red-400">An error occurred. Please try again.</div>
          )}
          {status === 'complete' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
              <div className="w-full">
                <h2 className="text-2xl font-bold mb-4 text-purple-300">Analyzed Video</h2>
                <VideoPlayer src={videoUrl} />
              </div>
              <div className="w-full">
                <h2 className="text-2xl font-bold mb-4 text-purple-300">AI-Generated Report</h2>
                <div className="prose prose-invert max-w-none bg-gray-900 p-4 rounded-md">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      table: ({node, ...props}) => <table className="w-full border-collapse border border-slate-500" {...props} />,
                      thead: ({node, ...props}) => <thead className="bg-slate-800" {...props} />,
                      th: ({node, ...props}) => <th className="border border-slate-600 p-2" {...props} />,
                      td: ({node, ...props}) => <td className="border border-slate-700 p-2" {...props} />,
                    }}
                  >
                    {report}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
