"""Chat assistant API endpoints."""

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from modules.chat_agent import chat_agent

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    message: str
    project_id: Optional[str] = None
    attachments: list[str] = Field(default_factory=list)


class ChatMessageResponse(BaseModel):
    reply: str
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(body: ChatMessageRequest) -> ChatMessageResponse:
    """Send a message to the AI chat assistant."""
    result = await chat_agent.process_message(
        message=body.message,
        project_id=body.project_id,
        attachments=body.attachments,
    )
    return ChatMessageResponse(**result)
