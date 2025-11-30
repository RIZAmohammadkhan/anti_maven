from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent_graph import app as graph_app
from models import ResearchRequest, ResearchResponse
import os

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.post("/api/research", response_model=ResearchResponse)
async def research(request: ResearchRequest):
    try:
        print(f"Received research request: {request.query}")
        initial_state = {"query": request.query, "product_candidates": [], "detailed_reports": [], "final_response": {}}
        result = graph_app.invoke(initial_state)
        
        final_response = result.get("final_response", {})
        if not final_response:
             raise HTTPException(status_code=500, detail="Failed to generate research response")
             
        return final_response
    except Exception as e:
        print(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def read_index():
    return FileResponse('index.html')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
