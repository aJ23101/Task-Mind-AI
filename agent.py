from ai_service import create_assistant
from database import init_db

init_db()


def createAgent():
    """Backward-compatible factory used by earlier versions of the Streamlit app."""
    return create_assistant()


def call_agent(query: str) -> str:
    result = createAgent().invoke(
        {"messages": [{"role": "user", "content": query}]},
        {"configurable": {"thread_id": "1"}},
    )
    answer = result["messages"][-1].content
    return str(answer)
