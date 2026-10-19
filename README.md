# ScholarSwarm AI

> **Research smarter. Fund your future.**  
> Built for the TetraNoodle AI Hackathon 2026.

ScholarSwarm AI is an evidence-first, multi-agent scholarship and master's research platform that helps international students discover genuine opportunities, audits criteria against primary sources, and prepares customized application materials.

---

## Current Status: Milestone 1 — Foundation Baseline & Frontend Shell

- Isolated Git repository initialized.
- Dedicated Python 3.11 virtual environment configured at `backend/.venv`.
- Pinned backend dependencies (`fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `aiosqlite`, `httpx`, `pytest`).
- Structured `GET /api/v1/health` endpoint implemented with CORS support and automated tests passing.
- Frontend shell created at `frontend/` (React 19, TypeScript, Vite, Tailwind CSS v3, Lucide icons).
- Live backend connectivity integration verified with honest status handling.

---

## Prerequisites

- **Python**: 3.11.x (tested on Python 3.11.9, 64-bit AMD64)
- **Node.js**: 20+ (tested on Node v24.18.0, npm 11.16.0)
- **Git**: 2.x
- **OS**: Windows / Linux / macOS (PowerShell instructions provided)

---

## Quick Start (Local Development)

### 1. Backend Setup

```powershell
# Copy environment template
Copy-Item .env.example .env

# Install backend dependencies in virtual environment
backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt

# Run backend tests
backend\.venv\Scripts\python.exe -m pytest -v backend/tests

# Launch FastAPI backend on port 8000
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000 --host 127.0.0.1
```

Once running:
- Health check: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)
- Interactive API Docs (Swagger): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 2. Frontend Setup

In a separate terminal:

```powershell
cd frontend

# Copy environment template
Copy-Item .env.example .env.local

# Install dependencies (if needed)
npm install

# Start Vite development server
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser. The frontend will immediately ping the backend and display live connection diagnostics.

### 3. Frontend Production Build & Quality Checks

```powershell
cd frontend
npm run build    # Runs tsc -b type check + Vite build
npm run lint     # Runs linter (Oxlint)
```

---

## Windows PowerShell Activation Alternatives

If PowerShell script execution policy prevents running `Activate.ps1`:

### Option A: Direct Invocation (Recommended — Zero Policy Changes)
```powershell
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000 --host 127.0.0.1
```

### Option B: Process-Scoped Policy Bypass (Session Only)
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\backend\.venv\Scripts\Activate.ps1
cd backend
uvicorn app.main:app --reload
```
