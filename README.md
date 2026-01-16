# Vietnam Stock Financial Reports

A full-stack application to fetch, store, and display Vietnam stock financial reports using vnstock3 library.

## Tech Stack

- **Frontend**: React + Vite + TypeScript + TailwindCSS
- **Backend**: FastAPI + SQLAlchemy + PostgreSQL
- **Data Source**: vnstock3 (Vietnam stock market data)
- **Deployment**: Vercel (frontend) + Render (backend + PostgreSQL)

## Project Structure

```
VN_Finance/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry
│   │   ├── config.py            # Environment config
│   │   ├── database.py          # SQLAlchemy setup
│   │   ├── models/              # DB models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── services/            # vnstock3 integration
│   │   └── routers/             # API endpoints
│   ├── requirements.txt
│   ├── Dockerfile
│   └── render.yaml
├── frontend/
│   ├── src/
│   │   ├── components/          # React components
│   │   ├── services/            # API service
│   │   ├── types/               # TypeScript types
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── vercel.json
└── .github/workflows/           # CI/CD pipelines
```

## Features

- Search for Vietnam stock symbols (e.g., VNM, FPT, VIC)
- Fetch annual and quarterly financial reports from vnstock3
- Store data in PostgreSQL for faster subsequent loads
- View financial data by year with year selector
- Auto-fetch last 5 years of data on first request
- Three report types: Balance Sheet, Income Statement, Cash Flow

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stocks` | List all stocks in DB |
| GET | `/api/stocks/search?q=VNM` | Search stocks |
| GET | `/api/stocks/{symbol}` | Get stock details |
| POST | `/api/stocks/{symbol}/fetch` | Fetch & store data from vnstock3 |
| GET | `/api/stocks/{symbol}/balance-sheet` | Get balance sheets |
| GET | `/api/stocks/{symbol}/income-statement` | Get income statements |
| GET | `/api/stocks/{symbol}/cash-flow` | Get cash flow statements |
| GET | `/api/stocks/{symbol}/reports` | Get all reports |

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your database URL

# Run the server
uvicorn app.main:app --reload
```

The API will be available at http://localhost:8000. API docs at http://localhost:8000/docs.

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

The frontend will be available at http://localhost:5173.

### Database Setup

```sql
CREATE DATABASE vn_finance;
```

The tables will be created automatically when the backend starts.

## Deployment

### Backend (Render)

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Set the root directory to `backend`
4. Create a PostgreSQL database
5. Set environment variables:
   - `DATABASE_URL`: PostgreSQL connection string
   - `CORS_ORIGINS`: Frontend URL

### Frontend (Vercel)

1. Import your GitHub repository on Vercel
2. Set the root directory to `frontend`
3. Set environment variables:
   - `VITE_API_URL`: Backend API URL

### GitHub Actions Secrets

For CI/CD, configure the following secrets:

**Backend:**
- `RENDER_SERVICE_ID`
- `RENDER_API_KEY`

**Frontend:**
- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`
- `VITE_API_URL`

## Environment Variables

### Backend
```
DATABASE_URL=postgresql://user:pass@host:5432/vn_finance
CORS_ORIGINS=http://localhost:5173,https://your-frontend.vercel.app
DEBUG=false
```

### Frontend
```
VITE_API_URL=https://your-backend.onrender.com
```

## License

MIT
