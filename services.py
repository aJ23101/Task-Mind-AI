from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from database import AppSetting, LocalSession, Milestone, Project, ScheduleBlock, Todo, timestamp_now

TASK_STATUSES = ("pending", "in_progress", "blocked", "done")
TASK_PRIORITIES = ("low", "medium", "high")


def parse_date(value: str | date | None) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip()).date()
    except ValueError:
        pass
    for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value.strip(), date_format).date()
        except ValueError:
            continue
    return None


def list_tasks(
    status: str = "All",
    priority: str = "All",
    project_id: int | None = None,
    search: str = "",
) -> list[Todo]:
    with LocalSession() as session:
        query = select(Todo)
        if status != "All":
            query = query.where(Todo.status == status)
        if priority != "All":
            query = query.where(Todo.priority == priority)
        if project_id is not None:
            query = query.where(Todo.project_id == project_id)
        if search.strip():
            needle = f"%{search.strip()}%"
            query = query.where(
                Todo.title.ilike(needle) | Todo.description.ilike(needle)
            )
        return list(session.scalars(query.order_by(Todo.id.desc())))


def get_task(todo_id: int) -> Todo | None:
    with LocalSession() as session:
        return session.get(Todo, todo_id)


def save_task(
    *,
    title: str,
    description: str = "",
    priority: str = "medium",
    status: str = "pending",
    due_date: str = "",
    estimated_minutes: int = 30,
    actual_minutes: int = 0,
    project_id: int | None = None,
    tags: str = "",
    category: str = "",
    todo_id: int | None = None,
) -> int:
    if not title.strip():
        raise ValueError("Task title is required.")
    if priority not in TASK_PRIORITIES:
        raise ValueError("Choose low, medium, or high priority.")
    if status not in TASK_STATUSES:
        raise ValueError("Choose a valid task status.")
    if estimated_minutes < 1 or actual_minutes < 0:
        raise ValueError("Estimated duration must be positive; actual duration cannot be negative.")
    if due_date and parse_date(due_date) is None:
        raise ValueError("Enter the due date in YYYY-MM-DD format.")

    now = timestamp_now()
    with LocalSession.begin() as session:
        task = session.get(Todo, todo_id) if todo_id is not None else None
        if todo_id is not None and task is None:
            raise ValueError(f"Task #{todo_id} no longer exists.")
        if task is None:
            task = Todo(
                title=title.strip(),
                created_at=now,
                status=status,
            )
            session.add(task)
        was_completed = task.status == "done"
        task.title = title.strip()
        task.description = description.strip()
        task.priority = priority
        task.status = status
        task.due_date = due_date
        task.updated_at = now
        task.completed_at = now if status == "done" and not was_completed else (
            "" if status != "done" else task.completed_at
        )
        task.estimated_minutes = estimated_minutes
        task.actual_minutes = actual_minutes
        task.project_id = project_id
        task.tags = tags.strip()
        task.category = category.strip()
        session.flush()
        return task.id


def delete_task(todo_id: int) -> None:
    with LocalSession.begin() as session:
        task = session.get(Todo, todo_id)
        if task is None:
            raise ValueError(f"Task #{todo_id} no longer exists.")
        session.delete(task)


def list_projects() -> list[Project]:
    with LocalSession() as session:
        return list(session.scalars(select(Project).order_by(Project.name)))


def save_project(name: str, description: str = "", project_id: int | None = None) -> int:
    if not name.strip():
        raise ValueError("Project name is required.")
    with LocalSession.begin() as session:
        project = session.get(Project, project_id) if project_id is not None else None
        if project is None:
            project = Project(name=name.strip(), created_at=timestamp_now())
            session.add(project)
        project.name = name.strip()
        project.description = description.strip()
        session.flush()
        return project.id


def project_progress(project_id: int) -> tuple[int, int]:
    tasks = list_tasks(project_id=project_id)
    done = sum(task.status == "done" for task in tasks)
    return done, len(tasks)


def list_milestones(project_id: int | None = None) -> list[Milestone]:
    with LocalSession() as session:
        query = select(Milestone)
        if project_id is not None:
            query = query.where(Milestone.project_id == project_id)
        return list(session.scalars(query.order_by(Milestone.due_date, Milestone.id)))


def save_milestone(
    project_id: int, title: str, due_date: str = "", milestone_id: int | None = None
) -> int:
    if not title.strip():
        raise ValueError("Milestone title is required.")
    if due_date and parse_date(due_date) is None:
        raise ValueError("Enter the milestone date in YYYY-MM-DD format.")
    with LocalSession.begin() as session:
        milestone = (
            session.get(Milestone, milestone_id) if milestone_id is not None else None
        )
        if milestone is None:
            milestone = Milestone(
                project_id=project_id,
                title=title.strip(),
                created_at=timestamp_now(),
            )
            session.add(milestone)
        milestone.project_id = project_id
        milestone.title = title.strip()
        milestone.due_date = due_date
        session.flush()
        return milestone.id


def set_setting(key: str, value: str) -> None:
    with LocalSession.begin() as session:
        setting = session.get(AppSetting, key)
        if setting is None:
            setting = AppSetting(key=key, value=value)
            session.add(setting)
        else:
            setting.value = value


def get_setting(key: str, default: str) -> str:
    with LocalSession() as session:
        setting = session.get(AppSetting, key)
        return setting.value if setting else default


def get_day_schedule(day: date) -> list[ScheduleBlock]:
    prefix = day.isoformat()
    with LocalSession() as session:
        return list(
            session.scalars(
                select(ScheduleBlock)
                .where(ScheduleBlock.starts_at.startswith(prefix))
                .order_by(ScheduleBlock.starts_at)
            )
        )


def priority_score(task: Todo, today: date | None = None) -> tuple[int, int, int]:
    today = today or date.today()
    due = parse_date(task.due_date)
    priority_weight = {"high": 0, "medium": 1, "low": 2}.get(task.priority, 1)
    overdue_weight = 0 if due is not None and due < today else 1
    days_until_due = (due - today).days if due is not None else 3650
    return overdue_weight, priority_weight, days_until_due


def rank_tasks(tasks: list[Todo], today: date | None = None) -> list[Todo]:
    return sorted(
        (task for task in tasks if task.status != "done"),
        key=lambda task: priority_score(task, today),
    )


def propose_day_schedule(
    day: date,
    tasks: list[Todo],
    work_start: time = time(9, 0),
    work_end: time = time(17, 0),
    max_daily_minutes: int | None = None,
) -> tuple[list[dict[str, str | int]], list[str]]:
    """Build a deterministic proposal without changing saved/accepted schedule blocks."""
    existing = get_day_schedule(day)
    accepted = [block for block in existing if block.accepted]
    day_start = datetime.combine(day, work_start)
    day_end = datetime.combine(day, work_end)
    lunch_start = datetime.combine(day, time(12, 30))
    lunch_end = datetime.combine(day, time(13, 0))
    windows: list[tuple[datetime, datetime]] = []
    if work_start < time(12, 30) and work_end > time(12, 30):
        windows.append((day_start, min(day_end, lunch_start)))
        if work_end > time(13, 0):
            windows.append((max(day_start, lunch_end), day_end))
    else:
        windows.append((day_start, day_end))
    for block in accepted:
        occupied_start = datetime.fromisoformat(block.starts_at)
        occupied_end = datetime.fromisoformat(block.ends_at)
        next_windows = []
        for start, end in windows:
            if occupied_end <= start or occupied_start >= end:
                next_windows.append((start, end))
            else:
                if start < occupied_start:
                    next_windows.append((start, occupied_start))
                if occupied_end < end:
                    next_windows.append((occupied_end, end))
        windows = next_windows

    proposals: list[dict[str, str | int]] = []
    warnings: list[str] = []
    cursor_index = 0
    accepted_minutes = sum(
        max(
            0,
            int(
                (
                    datetime.fromisoformat(block.ends_at)
                    - datetime.fromisoformat(block.starts_at)
                ).total_seconds()
                // 60
            ),
        )
        for block in accepted
    )
    remaining_daily_minutes = (
        max(0, max_daily_minutes - accepted_minutes)
        if max_daily_minutes is not None
        else None
    )
    ranked = rank_tasks(tasks, day)
    accepted_minutes_by_task: dict[int, int] = {}
    for block in accepted:
        if block.todo_id is None:
            continue
        duration = int(
            (
                datetime.fromisoformat(block.ends_at)
                - datetime.fromisoformat(block.starts_at)
            ).total_seconds()
            // 60
        )
        accepted_minutes_by_task[block.todo_id] = (
            accepted_minutes_by_task.get(block.todo_id, 0) + duration
        )
    for task in ranked:
        due = parse_date(task.due_date)
        if due is not None and due < day:
            warnings.append(f"Task #{task.id} is overdue: {task.title}.")
        remaining_task_minutes = max(
            0,
            (task.estimated_minutes or 30)
            - accepted_minutes_by_task.get(task.id, 0),
        )
        if remaining_task_minutes == 0:
            continue
        minutes_left = remaining_task_minutes
        while minutes_left and cursor_index < len(windows):
            start, end = windows[cursor_index]
            if start >= end:
                cursor_index += 1
                continue
            block_minutes = min(minutes_left, int((end - start).total_seconds() // 60))
            if remaining_daily_minutes is not None:
                block_minutes = min(block_minutes, remaining_daily_minutes)
            if block_minutes <= 0:
                cursor_index += 1
                continue
            block_end = start + timedelta(minutes=block_minutes)
            proposals.append(
                {
                    "todo_id": task.id,
                    "title": task.title,
                    "start": start.isoformat(timespec="minutes"),
                    "end": block_end.isoformat(timespec="minutes"),
                    "minutes": block_minutes,
                    "reason": f"{task.priority.title()} priority"
                    + (f"; due {due.isoformat()}" if due else "; no deadline set"),
                }
            )
            minutes_left -= block_minutes
            if remaining_daily_minutes is not None:
                remaining_daily_minutes -= block_minutes
            windows[cursor_index] = (block_end + timedelta(minutes=10), end)
            if windows[cursor_index][0] >= end:
                cursor_index += 1
        if minutes_left:
            warnings.append(
                f"Not enough working time for all of “{task.title}”; "
                f"{minutes_left} min remain unscheduled."
            )
    return proposals, warnings


def accept_schedule(proposals: list[dict[str, str | int]]) -> int:
    now = timestamp_now()
    with LocalSession.begin() as session:
        inserted = 0
        for proposal in proposals:
            starts_at = str(proposal["start"])
            ends_at = str(proposal["end"])
            conflicting = session.scalar(
                select(ScheduleBlock.id).where(
                    ScheduleBlock.accepted == 1,
                    ScheduleBlock.starts_at < ends_at,
                    ScheduleBlock.ends_at > starts_at,
                )
            )
            if conflicting is not None:
                raise ValueError("Schedule changed since this plan was generated. Refresh and re-plan.")
            session.add(
                ScheduleBlock(
                    todo_id=int(proposal["todo_id"]),
                    title=str(proposal["title"]),
                    starts_at=starts_at,
                    ends_at=ends_at,
                    accepted=1,
                    created_at=now,
                )
            )
            inserted += 1
        return inserted


def save_manual_schedule(
    title: str, starts_at: datetime, ends_at: datetime, todo_id: int | None = None
) -> int:
    if not title.strip() or ends_at <= starts_at:
        raise ValueError("Enter a title and an end time later than the start time.")
    with LocalSession.begin() as session:
        conflicting = session.scalar(
            select(ScheduleBlock.id).where(
                ScheduleBlock.accepted == 1,
                ScheduleBlock.starts_at < ends_at.isoformat(timespec="minutes"),
                ScheduleBlock.ends_at > starts_at.isoformat(timespec="minutes"),
            )
        )
        if conflicting is not None:
            raise ValueError("That time overlaps an accepted schedule block.")
        block = ScheduleBlock(
            todo_id=todo_id,
            title=title.strip(),
            starts_at=starts_at.isoformat(timespec="minutes"),
            ends_at=ends_at.isoformat(timespec="minutes"),
            accepted=1,
            created_at=timestamp_now(),
        )
        session.add(block)
        session.flush()
        return block.id


def productivity_summary(today: date | None = None) -> dict[str, int | float]:
    today = today or date.today()
    tasks = list_tasks()
    completed_today = sum(
        task.status == "done"
        and (parse_date(task.completed_at) == today if task.completed_at else False)
        for task in tasks
    )
    active = [task for task in tasks if task.status != "done"]
    overdue = sum(
        (due := parse_date(task.due_date)) is not None and due < today for task in active
    )
    remaining_today = sum(parse_date(task.due_date) == today for task in active)
    completed_week = sum(
        task.status == "done"
        and (completed := parse_date(task.completed_at)) is not None
        and completed >= today - timedelta(days=6)
        for task in tasks
    )
    completed_with_deadline = [
        task
        for task in tasks
        if task.status == "done"
        and parse_date(task.due_date) is not None
        and parse_date(task.completed_at) is not None
    ]
    on_time_count = sum(
        parse_date(task.completed_at) <= parse_date(task.due_date)
        for task in completed_with_deadline
    )
    week_total = sum(
        (created := parse_date(task.created_at)) is not None
        and created >= today - timedelta(days=6)
        for task in tasks
    )
    return {
        "completed_today": completed_today,
        "remaining_today": remaining_today,
        "overdue": overdue,
        "completed_week": completed_week,
        "weekly_completion_rate": round(completed_week / week_total * 100, 1)
        if week_total
        else 0.0,
        "on_time_rate": round(on_time_count / len(completed_with_deadline) * 100, 1)
        if completed_with_deadline
        else 0.0,
    }
