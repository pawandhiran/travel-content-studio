"""Chat assistant API endpoints -- messaging, rules, skills, and history."""

from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from modules.chat_agent import chat_agent

router = APIRouter(prefix="/chat", tags=["chat"])


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

class ChatMessageRequest(BaseModel):
    message: str
    project_id: Optional[str] = None
    attachments: list[str] = Field(default_factory=list)
    directories: list[str] = Field(default_factory=list)


class ChatMessageResponse(BaseModel):
    reply: str
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    model_used: Optional[str] = None
    intent: Optional[str] = None
    review: Optional[dict[str, Any]] = None


class AddRuleRequest(BaseModel):
    rule: str
    category: str = "general"


class AddRuleResponse(BaseModel):
    id: str
    status: str = "ok"


class AddSkillRequest(BaseModel):
    name: str
    description: str
    steps: list[dict[str, Any]]


class AddSkillResponse(BaseModel):
    id: str
    status: str = "ok"


class RunSkillRequest(BaseModel):
    project_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    message_id: str
    rating: Literal["up", "down"]
    project_id: Optional[str] = None


# ------------------------------------------------------------------
# Chat messaging
# ------------------------------------------------------------------

@router.post("/message", response_model=ChatMessageResponse)
async def send_message(body: ChatMessageRequest) -> ChatMessageResponse:
    """Send a message to the AI chat assistant."""
    msg = body.message.strip()

    # Handle /run as a skill execution
    if msg.lower().startswith("/run "):
        skill_name = msg[5:].strip()
        skill = chat_agent.rules.find_skill_by_name(skill_name)
        if not skill:
            return ChatMessageResponse(
                reply=f"Skill \"{skill_name}\" not found. Use /skills to see available skills."
            )
        result = await chat_agent.run_skill(skill["id"], project_id=body.project_id)
        return ChatMessageResponse(**result)

    all_attachments = list(body.attachments) + list(body.directories)
    result = await chat_agent.process_message(
        message=body.message,
        project_id=body.project_id,
        attachments=all_attachments,
    )
    return ChatMessageResponse(**result)


# ------------------------------------------------------------------
# Rules
# ------------------------------------------------------------------

@router.get("/rules")
async def list_rules() -> list[dict[str, Any]]:
    return chat_agent.rules.list_rules()


@router.post("/rules", response_model=AddRuleResponse)
async def add_rule(body: AddRuleRequest) -> AddRuleResponse:
    rule_id = chat_agent.rules.add_rule(body.rule, body.category)
    return AddRuleResponse(id=rule_id)


@router.delete("/rules/{rule_id}")
async def remove_rule(rule_id: str):
    removed = chat_agent.rules.remove_rule(rule_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "ok"}


# ------------------------------------------------------------------
# Skills
# ------------------------------------------------------------------

@router.get("/skills")
async def list_skills() -> list[dict[str, Any]]:
    return chat_agent.rules.list_skills()


@router.post("/skills", response_model=AddSkillResponse)
async def add_skill(body: AddSkillRequest) -> AddSkillResponse:
    skill_id = chat_agent.rules.add_skill(body.name, body.description, body.steps)
    return AddSkillResponse(id=skill_id)


@router.delete("/skills/{skill_id}")
async def remove_skill(skill_id: str):
    removed = chat_agent.rules.remove_skill(skill_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Skill not found or is built-in")
    return {"status": "ok"}


@router.post("/skills/{skill_id}/run", response_model=ChatMessageResponse)
async def run_skill(skill_id: str, body: RunSkillRequest) -> ChatMessageResponse:
    result = await chat_agent.run_skill(skill_id, project_id=body.project_id)
    return ChatMessageResponse(**result)


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------

@router.get("/history")
async def get_history(
    project_id: Optional[str] = None, limit: int = 100
) -> dict[str, Any]:
    messages = chat_agent.memory.get_history(project_id, limit=limit)
    stats = chat_agent.memory.get_stats()
    return {"messages": messages, "stats": stats}


@router.get("/conversations")
async def list_conversations() -> list[dict[str, Any]]:
    """List all saved conversations with preview info."""
    return chat_agent.memory.list_conversations()


@router.delete("/history")
async def clear_history(project_id: Optional[str] = None):
    chat_agent.memory.clear_history(project_id)
    return {"status": "ok"}


@router.get("/history/search")
async def search_history(q: str) -> list[dict[str, Any]]:
    return chat_agent.memory.search_history(q)


# ------------------------------------------------------------------
# Feedback (thumbs up/down on individual messages)
# ------------------------------------------------------------------

@router.post("/feedback")
async def record_chat_feedback(body: FeedbackRequest):
    chat_agent.record_feedback(body.message_id, body.rating, body.project_id)
    return {"status": "ok"}
