import os
from datetime import date

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

load_dotenv()


class TaskDraft(BaseModel):
    title: str = Field(description="Short actionable task title")
    description: str = Field(default="", description="Optional task detail")
    priority: str = Field(default="medium", description="One of low, medium, high")
    due_date: str = Field(default="", description="Due date in YYYY-MM-DD format, or empty if unspecified")
    estimated_minutes: int = Field(default=30, ge=1, le=1440)
    category: str = Field(default="")


class TaskDrafts(BaseModel):
    tasks: list[TaskDraft] = Field(default_factory=list)


def api_key_available() -> bool:
    return bool(os.getenv("GROQ_API_KEY", "").strip())


def get_chat_model() -> ChatGroq:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Groq is not configured. Add GROQ_API_KEY to your local .env file "
            "or Streamlit app secrets."
        )
    model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    return ChatGroq(model=model_name, api_key=api_key, temperature=0.2)


def extract_task_drafts(request: str, today: date | None = None) -> list[TaskDraft]:
    if not request.strip():
        raise ValueError("Describe the task or tasks you want to add.")
    today = today or date.today()
    structured_model = get_chat_model().with_structured_output(TaskDrafts)
    result = structured_model.invoke(
        [
            SystemMessage(
                content=(
                    "Extract only tasks the user explicitly requested. Do not invent deadlines, "
                    "projects, or details. Resolve clear relative dates using the supplied date. "
                    "Return dates as YYYY-MM-DD; leave due_date empty if unspecified or ambiguous. "
                    "Priority must be low, medium, or high. Keep estimates realistic and positive. "
                    f"Today's local date is {today.isoformat()}."
                )
            ),
            HumanMessage(content=request),
        ]
    )
    return result.tasks


def create_assistant():
    from langchain.agents import create_agent

    from tools import create_todo, delete_todo, list_todos, update_todos

    return create_agent(
        model=get_chat_model(),
        tools=[create_todo, list_todos, update_todos, delete_todo],
        system_prompt=(
            "You are a concise, friendly task assistant. Use tools for all database changes "
            "and factual task listings. Confirm mutations only after the tool succeeds. "
            "Supported statuses: pending, in_progress, blocked, done. "
            "Supported priorities: low, medium, high. "
            "Do not claim that you changed a task unless a tool confirms it."
        ),
    )


def generate_daily_briefing(task_facts: str) -> str:
    if not task_facts.strip():
        return "You have a clear slate today. Add a task when you are ready."
    response = get_chat_model().invoke(
        [
            SystemMessage(
                content=(
                    "Write a short daily task briefing using only the supplied task data. "
                    "Prioritize urgent work; never invent tasks or deadlines."
                )
            ),
            HumanMessage(content=task_facts),
        ]
    )
    return str(response.content)
