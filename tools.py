from langchain.tools import tool

from services import (
    TASK_PRIORITIES,
    TASK_STATUSES,
    delete_task,
    get_task,
    list_tasks,
    save_task,
)


@tool
def create_todo(
    title: str,
    description: str = "",
    priority: str = "medium",
    due_date: str = "",
    estimated_minutes: int = 30,
    category: str = "",
):
    """Create a task. Dates should be YYYY-MM-DD; priority is low, medium, or high."""
    if priority.lower() not in TASK_PRIORITIES:
        return "Choose low, medium, or high priority."
    task_id = save_task(
        title=title,
        description=description,
        priority=priority.lower(),
        due_date=due_date,
        estimated_minutes=estimated_minutes,
        category=category,
    )
    return f"Task #{task_id} created: {title}"


@tool
def list_todos(status: str = "all", priority: str = "all"):
    """List tasks, optionally filtered by status or priority."""
    normalized_status = status.lower()
    normalized_priority = priority.lower()
    if normalized_status != "all" and normalized_status not in TASK_STATUSES:
        return "Choose pending, in_progress, blocked, done, or all for status."
    if normalized_priority != "all" and normalized_priority not in TASK_PRIORITIES:
        return "Choose low, medium, high, or all for priority."
    return [
        task.to_dict()
        for task in list_tasks(
            status="All" if normalized_status == "all" else normalized_status,
            priority="All" if normalized_priority == "all" else normalized_priority,
        )
    ]


@tool
def update_todos(
    todo_id: int,
    title: str = "",
    description: str = "",
    status: str = "",
    priority: str = "",
    due_date: str = "",
    estimated_minutes: int | None = None,
):
    """Update the supplied fields of a task by ID; leave unchanged fields empty."""
    task = get_task(todo_id)
    if task is None:
        return f"Task #{todo_id} was not found."
    normalized_status = status.lower() if status else task.status
    normalized_priority = priority.lower() if priority else task.priority
    try:
        save_task(
            todo_id=todo_id,
            title=title or task.title,
            description=description or task.description,
            status=normalized_status,
            priority=normalized_priority,
            due_date=due_date or task.due_date,
            estimated_minutes=estimated_minutes or task.estimated_minutes,
            actual_minutes=task.actual_minutes,
            project_id=task.project_id,
            tags=task.tags,
            category=task.category,
        )
    except ValueError as error:
        return str(error)
    return f"Task #{todo_id} updated: {title or task.title}"


@tool
def delete_todo(todo_id: int):
    """Permanently delete a task by ID."""
    try:
        task = get_task(todo_id)
        if task is None:
            return f"Task #{todo_id} was not found."
        title = task.title
        delete_task(todo_id)
        return f"Task #{todo_id} ({title}) deleted."
    except ValueError as error:
        return str(error)
