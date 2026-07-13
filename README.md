# Email Finder & Verifier

A professional web application for generating professional email permutations for a person and checking their validity using passive DNS MX resolving and SMTP handshake handshakes.

Features:
- **Interactive Web Interface**: Built with React (Vite) and styled with dark-mode glassmorphism.
- **FastAPI Backend**: Exposes a real-time progress update stream (using Server-Sent Events).
- **DNS resolving**: Queries DNS MX records.
- **Passive SMTP checks**: Connects to mail servers and tests address existence without sending emails.
- **Catch-All detection**: Caches and handles catch-all configurations.
- **Hunter.io Fallback**: Automatically falls back to Hunter.io database checking if Port 25 is blocked or if domain is catch-all.

---

## Workspace Setup

### 1. Backend Server Setup
Install dependencies:
```bash
pip install -r requirements.txt
```

Create a `.env` file in the root directory and add your Hunter.io key:
```ini
HUNTER_API_KEY=your_hunter_io_api_key
```

Run the backend server:
```bash
python server.py
```
*Runs on http://localhost:8000*

### 2. Frontend React Client
Navigate to `frontend/`, install dependencies and run Vite:
```bash
cd frontend
npm install
npm run dev
```
*Runs on http://localhost:5173*

---

## Production Deployment

### Backend (Render)
1. Deploy the root folder to Render.
2. Select **Python** environment.
3. Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
4. Set the `HUNTER_API_KEY` environment variable in Render's dashboard.

### Frontend (Vercel)
1. Deploy the `frontend/` sub-folder to Vercel.
2. Set Environment Variable: `VITE_API_BASE=https://your-backend-url.onrender.com`
3. Build command: `npm run build`
4. Output directory: `dist`
