# ScholarSwarm AI — Frontend Shell

Lightweight, accessible frontend client for ScholarSwarm AI built with React 19, TypeScript, Vite, and Tailwind CSS v3.

---

## Tech Stack

- **Framework**: React 19 + TypeScript
- **Bundler & Dev Server**: Vite 8
- **Styling**: Tailwind CSS v3 (configured via PostCSS & Autoprefixer)
- **Icons**: Lucide React
- **Linter & Type Checking**: TypeScript (`tsc -b`) + Oxlint

---

## Design System Foundations

- **Surfaces**: Warm off-white (`#fbfbfa` / `surface-warm`), clean cards (`#ffffff`), and subtle borders (`#e2e8f0`).
- **Typography**: Deep midnight navy (`#0b1329` / `brand-navy`) using Inter font.
- **Accents**: Restrained indigo (`#4f46e5`) and teal (`#0d9488`).
- **Status Indicators**: Emerald (`#059669`) for verified/online, Amber (`#d97706`) for warnings, Rose (`#e11d48`) for errors/offline.
- **Motion**: Subtle, purposeful interactions with full `prefers-reduced-motion` suppression.

---

## Configuration

Copy `.env.example` to `.env.local` to customize environment variables:

```bash
# In frontend/
cp .env.example .env.local
```

### Environment Variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Target URL of the FastAPI backend service |

*(Note: `.env.local` is ignored by Git to protect local machine settings).*

---

## Development Commands

Run all commands from the `frontend/` directory:

### 1. Install Dependencies
```bash
npm install
```

### 2. Start Development Server
```bash
npm run dev
```
By default, the Vite dev server starts at `http://localhost:5173`.

### 3. Run Production Build & Type Check
```bash
npm run build
```
Executes `tsc -b` (TypeScript type check) followed by `vite build`. Output is saved to `dist/`.

### 4. Run Linter
```bash
npm run lint
```

### 5. Preview Production Build
```bash
npm run preview
```

---

## Backend Health Integration

The frontend automatically pings `GET /api/v1/health` on initial load and allows on-demand verification via the "Check Connection" button.
- **Online**: Displays live status, application identity, version, and round-trip latency in milliseconds.
- **Offline / Loading**: Displays genuine state without simulating connectivity, providing clear instructions to launch the backend Uvicorn server if unreachable.
