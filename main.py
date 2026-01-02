from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent_graph import app as graph_app, set_progress_callback, clear_progress_callback
from models import ResearchRequest, ResearchResponse
import os
import json
import asyncio
import httpx
from typing import Callable, Optional

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def execute_research(query: str, progress_callback: Optional[Callable] = None):
    """Execute research with optional progress callback"""
    initial_state = {"query": query, "product_candidates": [], "detailed_reports": [], "final_response": {}}
    
    # Set callback for nodes to access
    if progress_callback:
        set_progress_callback(progress_callback)
    
    try:
        result = graph_app.invoke(initial_state)
    finally:
        # Clean up callback
        clear_progress_callback()
    
    return result

@app.post("/api/research", response_model=ResearchResponse)
async def research(request: ResearchRequest):
    try:
        print(f"Received research request: {request.query}")
        result = execute_research(request.query)
        
        final_response = result.get("final_response", {})
        if not final_response:
             raise HTTPException(status_code=500, detail="Failed to generate research response")
             
        return final_response
    except Exception as e:
        print(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

@app.get("/api/research/stream")
async def research_stream(query: str):
    """Stream research progress using Server-Sent Events"""
    async def event_generator():
        try:
            # Queue to collect progress messages
            message_queue = asyncio.Queue()
            loop = asyncio.get_event_loop()
            
            def progress_callback(message: str):
                """Callback to send progress updates - thread-safe"""
                try:
                    # Use call_soon_threadsafe to safely add to queue from another thread
                    loop.call_soon_threadsafe(message_queue.put_nowait, message)
                except Exception as e:
                    print(f"Error in progress_callback: {e}")
            
            # Start research in a separate thread
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            
            # Run research in background
            future = executor.submit(execute_research, query, progress_callback)
            
            # Stream progress messages
            while not future.done():
                try:
                    message = await asyncio.wait_for(message_queue.get(), timeout=0.5)
                    yield f"data: {json.dumps({'type': 'progress', 'message': message})}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f": heartbeat\n\n"
            
            # Get remaining messages
            while not message_queue.empty():
                try:
                    message = message_queue.get_nowait()
                    yield f"data: {json.dumps({'type': 'progress', 'message': message})}\n\n"
                except:
                    break
            
            # Get result
            result = future.result()
            final_response = result.get("final_response", {})
            
            if not final_response:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to generate research response'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'complete', 'data': final_response})}\n\n"
            
        except Exception as e:
            print(f"Error in stream: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/")
async def read_index():
    return FileResponse('index.html')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
