from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from openai import OpenAI #type: ignore
import os
from dotenv import load_dotenv
from typing import Optional, List, Dict
import json
import uuid
from datetime import datetime
from pathlib import Path
import re
import boto3 
from botocore.exceptions import ClientError
from context import prompt
from rag import FaissRAG, format_retrieval_context

load_dotenv()

app = FastAPI()

origins = os.getenv(
    "CORS_ORIGIN",
    os.getenv("CORS_ORIGINS", "http://localhost:3000"),
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.getenv("GROQ_API_KEY"),
                base_url="https://api.groq.com/openai/v1",
)

# Memory storage configuration
USE_S3 = os.getenv("USE_S3", "false").lower() == "true"
S3_BUCKET = os.getenv("S3_BUCKET", "")
BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_MEMORY_DIR = Path("/tmp/meettwin-memory") if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else BACKEND_DIR / "memory"
MEMORY_DIR = os.getenv("MEMORY_DIR", str(DEFAULT_MEMORY_DIR))
RAG_DIR = os.getenv("RAG_DIR", str(Path(MEMORY_DIR) / "faiss"))


#Initialize S3 client if needed
if USE_S3:
    s3_client = boto3.client("s3")

# The embedding model and existing FAISS files are loaded once per worker.
# For Lambda, point RAG_DIR at EFS (or another persistent mounted volume).
rag = FaissRAG(RAG_DIR)

# Request/Response models
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    session_id: Optional[str] = Field(default=None, max_length=128)

    @validator("message")
    def normalize_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value

    @validator("session_id")
    def validate_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
            raise ValueError("session_id may contain only letters, numbers, underscores, and hyphens")
        return value


class ChatResponse(BaseModel):
    response: str
    session_id: str


class Message(BaseModel):
    role: str
    content: str
    timestamp: str


INJECTION_PATTERNS = (
    r"\bignore\s+(all\s+)?(previous|prior|system)\s+instructions?\b",
    r"\b(disregard|override|bypass)\b.{0,40}\b(instructions?|guardrails?|policy|prompt)\b",
    r"\b(reveal|show|print|dump)\b.{0,40}\b(system prompt|instructions?|hidden context|chain[ -]?of[ -]?thought)\b",
    r"\bact as (?:a )?(?:different|unrestricted|jailbroken)\b",
)


def violates_input_guardrails(message: str) -> bool:
    """Catch direct prompt-injection attempts before they reach the model."""
    normalized = re.sub(r"\s+", " ", message.lower())
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in INJECTION_PATTERNS)


def valid_session_id(session_id: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id))
    
#Memory management functions
def get_memory_path(session_id: str) -> str:
    return f"{session_id}.json"

def load_conversation(session_id: str) -> List[Dict]:
    """Load conversation history from storage"""
    if USE_S3:
        try:
            response = s3_client.get_object(Bucket = S3_BUCKET, Key=get_memory_path(session_id))
            return json.loads(response["Body"].read().decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return []
            raise
    else:
        #Local file storage
        file_path = os.path.join(MEMORY_DIR, get_memory_path(session_id))
        if os.path.exists(file_path):
            with open(file_path,"r") as f:
                return json.load(f)
        return []
    

def save_conversation(session_id: str, messages: List[Dict]):
    """Save conversation history to storage"""
    if USE_S3:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=get_memory_path(session_id),
            Body=json.dumps(messages, indent=2),
            ContentType="application/json",
        )
    else:
        #Local file storage
        os.makedirs(MEMORY_DIR, exist_ok=True)
        file_path=os.path.join(MEMORY_DIR, get_memory_path(session_id))
        with open(file_path,"w") as f:
            json.dump(messages, f, indent=2)
            

@app.get("/")
async def root():
    return{
        "message":"AI Digital Twin API",
        "memory_enabled": True,
        "storage":"S3" if USE_S3 else "local",
    }
    
@app.get("/health")
async def health_check():
    return {"status":"healthy","use_s3":USE_S3}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        if violates_input_guardrails(request.message):
            raise HTTPException(
                status_code=400,
                detail="I can't help override safeguards or disclose internal instructions. I can help with professional questions about the digital twin instead.",
            )

        #Generate session ID if not available
        session_id = request.session_id or str(uuid.uuid4())
        
        #Load conversation history
        conversation = load_conversation(session_id)
        
        # Retrieve only relevant profile material and this visitor's past messages.
        retrieved = rag.retrieve(request.message, session_id=session_id)
        messages = [{"role":"system", "content": prompt(format_retrieval_context(retrieved))}]
        
        # Preserve immediate turn-taking; longer-term memory is supplied through RAG.
        for msg in conversation[-6:]:
            messages.append({"role":msg["role"], "content": msg["content"]})
            
        #Add current user message
        messages.append({"role":"user", "content":request.message})
        
        #Call OpenAI API
        response = client.chat.completions.create(
            model = "openai/gpt-oss-20b",
            messages=messages
        )
        
        assistant_response = response.choices[0].message.content
        if not assistant_response:
            raise RuntimeError("The model returned an empty response")
        
        #Update conversation history
        user_timestamp = datetime.now().isoformat()
        assistant_timestamp = datetime.now().isoformat()
        user_message = {"role":"user", "content":request.message, "timestamp":user_timestamp}
        assistant_message = {"role":"assistant", "content":assistant_response, "timestamp":assistant_timestamp}
        conversation.extend([user_message, assistant_message])
        
        # Save conversation
        save_conversation(session_id, conversation)
        rag.remember(session_id, "user", request.message, user_timestamp)
        rag.remember(session_id, "assistant", assistant_response, assistant_timestamp)

        return ChatResponse(response=assistant_response, session_id=session_id)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/conversation/{session_id}")
async def get_conversation(session_id: str):
    """Retrieve conversation history"""
    try:
        if not valid_session_id(session_id):
            raise HTTPException(status_code=400, detail="Invalid session_id")
        conversation = load_conversation(session_id)
        return {"session_id": session_id, "messages": conversation}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
