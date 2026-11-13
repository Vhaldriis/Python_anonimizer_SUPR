from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class MessageIn(BaseModel):
    role: str
    content: str


class FileAttachment(BaseModel):
    name: str
    type: str
    size: int
    base64: str  # base64 без data:...base64, префикса


class ChatRequest(BaseModel):
    messages: List[MessageIn]
    session_id: str = "default"
    user_id: int = 1
    provider: str = "claude"
    model: Optional[str] = None
    max_tokens: int = 2048
    temperature: float = 0.7
    files: List[FileAttachment] = []


class ChatResponse(BaseModel):
    success: bool
    text: Optional[str] = None
    error: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    model: Optional[str] = None
    provider: Optional[str] = None


class MapItem(BaseModel):
    pseudonym: str
    original: str
    field_type: str


class MapResponse(BaseModel):
    success: bool
    map: List[MapItem] = []
