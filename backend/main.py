from fastapi import FastAPI, HTTPException, Response, Depends, status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, List, Union, Callable
from agent_graph import app as graph_app, set_progress_callback, clear_progress_callback
from models import (
    ResearchRequest,
    ResearchResponse,
    PersonalizationInitRequest,
    PersonalizationInitResponse,
    PersonalizationAnswersRequest,
    PersonalizationAnswersResponse,
)
from database import create_tables, get_db, User, SearchHistory
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
import os
import json
import asyncio
import httpx
from collections import OrderedDict
import uuid
import time

from agents import PersonalizationAgent

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="Maven API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    create_tables()


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------
class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


class UserOut(BaseModel):
    id: int
    name: str
    email: str


class SearchHistoryOut(BaseModel):
    id: int
    query: str
    products: Optional[list] = None
    recommendation: Optional[str] = None
    created_at: str


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
@app.post("/api/auth/signup", response_model=AuthResponse)
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email.lower().strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        name=req.name.strip(),
        email=req.email.lower().strip(),
        hashed_password=hash_password(req.password),
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create account: {e}")

    token = create_access_token({"sub": str(user.id)})
    return {
        "token": token,
        "user": {"id": user.id, "name": user.name, "email": user.email},
    }


@app.post("/api/auth/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.email == req.email.lower().strip()).first()
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({"sub": str(user.id)})
    return {
        "token": token,
        "user": {"id": user.id, "name": user.name, "email": user.email},
    }


@app.get("/api/auth/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email}


# ---------------------------------------------------------------------------
# Search history endpoints
# ---------------------------------------------------------------------------
@app.get("/api/history", response_model=List[SearchHistoryOut])
def get_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == current_user.id)
        .order_by(SearchHistory.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": h.id,
            "query": h.query,
            "products": h.products,
            "recommendation": h.recommendation,
            "created_at": h.created_at.isoformat() if h.created_at else "",
        }
        for h in items
    ]


@app.delete("/api/history/{history_id}")
def delete_history_item(history_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(SearchHistory).filter(
        SearchHistory.id == history_id, SearchHistory.user_id == current_user.id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Research helpers (unchanged logic)
# ---------------------------------------------------------------------------
def execute_research(query: str, progress_callback: Optional[Callable] = None):
    initial_state = {"query": query, "product_candidates": [], "detailed_reports": [], "final_response": {}}
    if progress_callback:
        set_progress_callback(progress_callback)
    try:
        result = graph_app.invoke(initial_state)
    finally:
        clear_progress_callback()
    return result


# --- Personalization session store (in-memory) ---
_PERSONALIZATION_SESSIONS: "OrderedDict[str, dict]" = OrderedDict()
_MAX_SESSIONS = 200


def _session_put(session_id: str, payload: dict) -> None:
    if session_id in _PERSONALIZATION_SESSIONS:
        _PERSONALIZATION_SESSIONS.pop(session_id, None)
    _PERSONALIZATION_SESSIONS[session_id] = payload
    while len(_PERSONALIZATION_SESSIONS) > _MAX_SESSIONS:
        _PERSONALIZATION_SESSIONS.popitem(last=False)


def _session_get(session_id: str) -> Optional[dict]:
    payload = _PERSONALIZATION_SESSIONS.get(session_id)
    if not payload:
        return None
    _PERSONALIZATION_SESSIONS.pop(session_id, None)
    _PERSONALIZATION_SESSIONS[session_id] = payload
    return payload


def _build_personalized_query(query: str, answers: Optional[dict]) -> str:
    if not answers:
        return query
    lines = []
    for key, val in answers.items():
        if val is None:
            continue
        if isinstance(val, list):
            val_str = ", ".join([str(v) for v in val if v is not None and str(v).strip()])
        else:
            val_str = str(val)
        val_str = val_str.strip()
        if not val_str:
            continue
        lines.append(f"- {key}: {val_str}")
    if not lines:
        return query
    return (
        f"User request: {query}\n\n"
        f"Personalization (use these preferences to tailor recommendations):\n"
        + "\n".join(lines)
    )


personalization_agent = PersonalizationAgent()


# ---------------------------------------------------------------------------
# Personalization endpoints
# ---------------------------------------------------------------------------
@app.post("/api/personalization/init", response_model=PersonalizationInitResponse)
async def personalization_init(request: PersonalizationInitRequest):
    query = (request.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    try:
        questions = personalization_agent.generate_questions(query)
    except Exception as e:
        print(f"Error generating personalization questions: {e}")
        questions = []

    session_id = uuid.uuid4().hex
    _session_put(session_id, {"query": query, "questions": questions, "answers": {}, "created_at": time.time()})
    return {"session_id": session_id, "query": query, "questions": questions}


@app.post("/api/personalization/answers", response_model=PersonalizationAnswersResponse)
async def personalization_answers(request: PersonalizationAnswersRequest):
    session = _session_get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    answers = request.answers or {}
    if not isinstance(answers, dict):
        raise HTTPException(status_code=400, detail="answers must be an object")
    session["answers"] = answers
    _session_put(request.session_id, session)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Research endpoint (POST)
# ---------------------------------------------------------------------------
@app.post("/api/research", response_model=ResearchResponse)
async def research(request: ResearchRequest):
    try:
        query = (request.query or "").strip()
        if request.session_id:
            session = _session_get(request.session_id)
            if session:
                query = _build_personalized_query(session.get("query", query), session.get("answers"))
        elif request.preferences:
            query = _build_personalized_query(query, request.preferences)

        print(f"Received research request: {query}")
        result = execute_research(query)
        final_response = result.get("final_response", {})
        if not final_response:
            raise HTTPException(status_code=500, detail="Failed to generate research response")
        return final_response
    except Exception as e:
        print(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Image proxy
# ---------------------------------------------------------------------------
@app.get("/api/image-proxy")
async def proxy_image(url: str):
    if not url or not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid image URL")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Image fetch failed: {exc.__class__.__name__}")

    content_type = response.headers.get("Content-Type", "image/jpeg")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Upstream image fetch failed")
    if "image" not in content_type.lower():
        raise HTTPException(status_code=415, detail="URL did not return image content")

    return Response(
        content=response.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ---------------------------------------------------------------------------
# SSE stream endpoint (saves result to history when done)
# ---------------------------------------------------------------------------
@app.get("/api/research/stream")
async def research_stream(
    query: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[int] = None,
):
    """Stream research progress via Server-Sent Events.
    user_id is passed as a query-param by the authenticated frontend.
    """

    async def event_generator():
        try:
            resolved_query = (query or "").strip()
            original_query = resolved_query

            if session_id:
                session = _session_get(session_id)
                if not session:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Unknown session_id'})}\n\n"
                    return
                original_query = session.get("query", resolved_query)
                resolved_query = _build_personalized_query(original_query, session.get("answers"))

            if not resolved_query:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Query is required'})}\n\n"
                return

            message_queue = asyncio.Queue()
            loop = asyncio.get_event_loop()

            def progress_callback(message: str):
                try:
                    loop.call_soon_threadsafe(message_queue.put_nowait, message)
                except Exception as e:
                    print(f"Error in progress_callback: {e}")

            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(execute_research, resolved_query, progress_callback)

            while not future.done():
                try:
                    message = await asyncio.wait_for(message_queue.get(), timeout=0.5)
                    yield f"data: {json.dumps({'type': 'progress', 'message': message})}\n\n"
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"

            while not message_queue.empty():
                try:
                    message = message_queue.get_nowait()
                    yield f"data: {json.dumps({'type': 'progress', 'message': message})}\n\n"
                except Exception:
                    break

            result = future.result()
            final_response = result.get("final_response", {})

            if not final_response:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to generate research response'})}\n\n"
            else:
                # Persist to search history if user_id provided
                if user_id:
                    try:
                        from database import SessionLocal
                        db = SessionLocal()
                        entry = SearchHistory(
                            user_id=user_id,
                            query=original_query,
                            products=final_response.get("products"),
                            recommendation=final_response.get("final_recommendation", ""),
                        )
                        db.add(entry)
                        db.commit()
                        db.close()
                    except Exception as e:
                        print(f"Failed to save search history: {e}")

                yield f"data: {json.dumps({'type': 'complete', 'data': final_response})}\n\n"

        except Exception as e:
            print(f"Error in stream: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
