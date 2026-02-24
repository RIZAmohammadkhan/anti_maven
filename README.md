# MAVEN - AI Shopping Assistant

A full-stack AI-powered shopping research assistant that finds, compares, and recommends products using multi-agent AI workflows.

## Project Structure

```
anti_maven/
├── backend/            # FastAPI Python backend
│   ├── main.py         # API server (auth, research, history)
│   ├── agents.py       # AI agents (researcher, specialist, price comparison)
│   ├── agent_graph.py  # Agent orchestration pipeline
│   ├── models.py       # Pydantic models
│   ├── database.py     # SQLAlchemy models & DB setup
│   ├── auth.py         # JWT authentication & password hashing
│   └── requirements.txt
├── frontend/           # React + Vite frontend
│   ├── src/
│   │   ├── pages/      # Login, Signup, Dashboard
│   │   ├── components/ # Navbar, SearchHistory, ProductCard, etc.
│   │   ├── contexts/   # Auth context (React Context API)
│   │   ├── api/        # API client
│   │   └── utils.js    # Shared helpers
│   └── vite.config.js  # Vite config with API proxy
└── .env.example
```

## Getting Started

### 1. Backend

```bash
cd backend
cp .env.example .env   # Fill in your API keys
pip install -r requirements.txt
python main.py
```

Backend runs at `http://localhost:8000`

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173` (proxies `/api` to backend)

### Environment Variables

See `backend/.env.example` for required keys:
- `LLM_PROVIDER` - `gemini` or `groq`
- `TAVILY_API_KEY` - for web search
- `GEMINI_API_KEY` / `GROQ_API_KEY` - LLM provider keys
- `JWT_SECRET_KEY` - for authentication tokens

## Features

- **User Authentication** - Sign up / Login with JWT tokens
- **AI Product Research** - Multi-agent pipeline: search → analyze → compare prices → recommend
- **Personalization** - AI-generated clarifying questions before research
- **Search History** - View and re-run previous searches
- **Real-time Progress** - Live terminal-style streaming via SSE
- **Product Comparison** - Price comparison across retailers
- **Responsive UI** - Modern design with Tailwind CSS
