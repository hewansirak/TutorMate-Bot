from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
from datetime import datetime
import json

from database import DatabaseManager, init_db
from tutor_agent import AcademicCustomerServiceAgent

app = FastAPI(title="Academic Research Assistant", version="1.0.0")

# CORS middleware for Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database and agent
init_db()
db_manager = DatabaseManager()
agent = AcademicCustomerServiceAgent(db_manager)

class ChatRequest(BaseModel):
    user_id: str
    message: str

class ChatResponse(BaseModel):
    response: str
    papers: Optional[List[dict]] = None
    summary: Optional[str] = None

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        response_data = await agent.process_message(request.user_id, request.message)
        return ChatResponse(**response_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search-history/{user_id}")
async def get_search_history(user_id: str):
    try:
        history = db_manager.get_user_search_history(user_id)
        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user-interests/{user_id}")
async def get_user_interests(user_id: str):
    try:
        interests = db_manager.get_user_interests(user_id)
        return {"interests": interests}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/debug/cached-papers")
async def debug_cached_papers():
    try:
        papers = db_manager.debug_cached_papers()
        return {"cached_papers": papers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/debug/paper/{paper_id}")
async def debug_get_paper(paper_id: str):
    try:
        paper = db_manager.get_cached_paper(paper_id)
        return {"paper": paper, "found": bool(paper)}
    except Exception as e:
        return {"error": str(e)}
    
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)