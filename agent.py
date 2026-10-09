from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_groq import ChatGroq
from tools import *
from dotenv import load_dotenv
from database import init_db

load_dotenv()
init_db()

## agent = llm, tools, system_prompt, user

llm = ChatGroq(model="openai/gpt-oss-20b")

all_tools = [create_todo, list_todos, update_todos, delete_todo]


SYSTEM_PROMPT = """You are a smart and friendly Todo Manager AI assistant.

You help users manage their tasks using a database. You can:
  - Create new tasks
  - List / filter tasks by status or priority
  - Update any field of a task (title, description, status, priority, due date)
  - Delete tasks by ID

Guidelines:
- Always confirm what action you took after each tool call.
- When listing todos, present them in a readable table format.
- "mark as done"      → update with status='done'
- "start working on"  → update with status='in_progress'
- "show pending"      → list with status='pending'
- "high priority"     → list with priority='high'
- Be concise and friendly.

Status values:   pending | in_progress | done

Use Status Icons with staus value: 
  pending - 🕣 Pnding 
  in_progress - ⏳ In Progress
  done - ✅ Done
Priority values: low | medium | high
"""


memery = InMemorySaver()


def createAgent():
    agent = create_agent(
        model=llm, tools=all_tools, system_prompt=SYSTEM_PROMPT, checkpointer=memery
    )
    return agent


def call_agent(query: str):
    agent = createAgent()
    res = agent.invoke(
        {"messages": [{"role": "user", "content": query}]},
        {"configurable": {"thread_id": "1"}},
    )

    answer = res["messages"][-1].content
    print(answer)


# call_agent("List my all the task ?")
