import calendar
from datetime import date, datetime, time, timedelta

import streamlit as st
from groq import APIError

from ai_service import (
    TaskDraft,
    api_key_available,
    create_assistant,
    extract_task_drafts,
    generate_daily_briefing,
)
from database import Todo, init_db
from services import (
    TASK_PRIORITIES,
    TASK_STATUSES,
    accept_schedule,
    delete_task,
    get_day_schedule,
    get_setting,
    list_milestones,
    list_projects,
    list_tasks,
    parse_date,
    productivity_summary,
    project_progress,
    propose_day_schedule,
    rank_tasks,
    save_manual_schedule,
    save_milestone,
    save_project,
    save_task,
    set_setting,
)

init_db()
st.set_page_config(
    page_title="TaskMind | AI Productivity",
    page_icon="T",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root { color-scheme: dark; }
    .stApp { background: #0b1020; }
    [data-testid="stSidebar"] { background: #10172a; border-right: 1px solid #202a40; }
    [data-testid="stMetric"] {
        background: #121b30; border: 1px solid #24314b; border-radius: 14px;
        padding: 16px 18px;
    }
    div[data-testid="stForm"] {
        background: #10182a; border: 1px solid #26324a; border-radius: 14px;
        padding: 18px;
    }
    .eyebrow { color: #8da4cc; font-size: 0.8rem; letter-spacing: .12em; text-transform: uppercase; }
    .muted { color: #a7b3c9; }
    </style>
    """,
    unsafe_allow_html=True,
)


def friendly_error(error: Exception) -> None:
    st.error(f"{type(error).__name__}: {error}")


def project_choices() -> tuple[list[int | None], dict[int | None, str]]:
    projects = list_projects()
    ids: list[int | None] = [None, *(project.id for project in projects)]
    labels: dict[int | None, str] = {None: "No project"}
    labels.update({project.id: project.name for project in projects})
    return ids, labels


def save_task_form(
    task: Todo | None,
    key_prefix: str,
    project_ids: list[int | None],
    project_labels: dict[int | None, str],
) -> None:
    default_due = parse_date(task.due_date) if task is not None else None
    with st.form(f"{key_prefix}-{task.id if task else 'new'}"):
        title = st.text_input("Task title", value=task.title if task else "")
        description = st.text_area(
            "Notes", value=task.description if task else "", height=80
        )
        col_priority, col_status, col_due = st.columns(3)
        with col_priority:
            priority = st.selectbox(
                "Priority",
                TASK_PRIORITIES,
                index=TASK_PRIORITIES.index(task.priority)
                if task and task.priority in TASK_PRIORITIES
                else 1,
                key=f"{key_prefix}-priority-{task.id if task else 'new'}",
            )
        with col_status:
            status = st.selectbox(
                "Status",
                TASK_STATUSES,
                index=TASK_STATUSES.index(task.status)
                if task and task.status in TASK_STATUSES
                else 0,
                key=f"{key_prefix}-status-{task.id if task else 'new'}",
            )
        with col_due:
            has_due_date = st.checkbox(
                "Has a due date",
                value=default_due is not None,
                key=f"{key_prefix}-has-due-{task.id if task else 'new'}",
            )
            due = st.date_input(
                "Due date",
                value=default_due or date.today(),
                disabled=not has_due_date,
                key=f"{key_prefix}-due-{task.id if task else 'new'}",
            )
        col_duration, col_actual, col_project = st.columns(3)
        with col_duration:
            estimated = st.number_input(
                "Estimated minutes",
                min_value=1,
                max_value=1440,
                value=task.estimated_minutes if task else 30,
                step=15,
                key=f"{key_prefix}-estimate-{task.id if task else 'new'}",
            )
        with col_actual:
            actual = st.number_input(
                "Actual minutes",
                min_value=0,
                max_value=100000,
                value=task.actual_minutes if task else 0,
                step=15,
                key=f"{key_prefix}-actual-{task.id if task else 'new'}",
            )
        with col_project:
            current_project = task.project_id if task else None
            project_index = (
                project_ids.index(current_project)
                if current_project in project_ids
                else 0
            )
            selected_project = st.selectbox(
                "Project",
                project_ids,
                index=project_index,
                format_func=lambda value: project_labels[value],
                key=f"{key_prefix}-project-{task.id if task else 'new'}",
            )
        tags = st.text_input(
            "Tags (comma-separated)", value=task.tags if task else ""
        )
        category = st.text_input("Category", value=task.category if task else "")
        submitted = st.form_submit_button(
            "Save task" if task else "Add task", type="primary"
        )
    if submitted:
        try:
            save_task(
                todo_id=task.id if task else None,
                title=title,
                description=description,
                priority=priority,
                status=status,
                due_date=due.isoformat() if has_due_date else "",
                estimated_minutes=int(estimated),
                actual_minutes=int(actual),
                project_id=selected_project,
                tags=tags,
                category=category,
            )
            st.success("Task saved.")
            st.rerun()
        except ValueError as error:
            friendly_error(error)


def render_task_editor(
    task: Todo, project_ids: list[int | None], project_labels: dict[int | None, str]
) -> None:
    due_label = f" · due {task.due_date}" if task.due_date else ""
    with st.expander(f"{task.title}  ·  {task.priority.title()}{due_label}"):
        st.caption(
            f"#{task.id} · {task.status.replace('_', ' ').title()} · "
            f"{task.estimated_minutes} min"
        )
        save_task_form(task, "edit", project_ids, project_labels)
        if st.button("Delete task", key=f"delete-{task.id}"):
            try:
                delete_task(task.id)
                st.success("Task deleted.")
                st.rerun()
            except ValueError as error:
                friendly_error(error)


def page_dashboard() -> None:
    current_hour = datetime.now().hour
    greeting = "Good morning" if current_hour < 12 else (
        "Good afternoon" if current_hour < 18 else "Good evening"
    )
    st.markdown('<p class="eyebrow">Your personal command center</p>', unsafe_allow_html=True)
    st.title(f"{greeting}.")
    tasks = list_tasks()
    summary = productivity_summary()
    metric_cols = st.columns(4)
    metric_cols[0].metric("Done today", summary["completed_today"])
    metric_cols[1].metric("Due today", summary["remaining_today"])
    metric_cols[2].metric("Overdue", summary["overdue"])
    metric_cols[3].metric(
        "Weekly completion", f'{summary["weekly_completion_rate"]}%'
    )

    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Today's priorities")
        top_tasks = rank_tasks(tasks)[:3]
        if top_tasks:
            for task in top_tasks:
                due = f" · due {task.due_date}" if task.due_date else ""
                st.markdown(
                    f"**{task.title}**  \n"
                    f'<span class="muted">{task.priority.title()} priority · '
                    f'{task.estimated_minutes} min{due}</span>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No open tasks. Enjoy the breathing room.")
    with right:
        st.subheader("AI daily briefing")
        if st.button("Generate briefing", disabled=not api_key_available()):
            facts = "\n".join(
                f"- {task.title}; {task.priority} priority; due "
                f"{task.due_date or 'not set'}; {task.estimated_minutes} minutes"
                for task in top_tasks
            )
            try:
                st.session_state["briefing"] = generate_daily_briefing(facts)
            except (APIError, RuntimeError, ValueError) as error:
                friendly_error(error)
        if not api_key_available():
            st.caption("Add GROQ_API_KEY to enable AI features. Task management works without it.")
        if st.session_state.get("briefing"):
            st.info(st.session_state["briefing"])
        elif not api_key_available():
            st.info("Set up Groq to get a task-aware daily briefing.")

    st.subheader("Quick add")
    with st.form("quick-add", clear_on_submit=True):
        quick_title = st.text_input("What do you need to do?")
        quick_cols = st.columns([1, 1, 2])
        quick_priority = quick_cols[0].selectbox("Priority", TASK_PRIORITIES, index=1)
        quick_due_enabled = quick_cols[1].checkbox("Set a due date")
        quick_due = quick_cols[2].date_input(
            "Due date", value=date.today(), disabled=not quick_due_enabled
        )
        if st.form_submit_button("Add task", type="primary"):
            try:
                save_task(
                    title=quick_title,
                    priority=quick_priority,
                    due_date=quick_due.isoformat() if quick_due_enabled else "",
                )
                st.success("Task added.")
                st.rerun()
            except ValueError as error:
                friendly_error(error)

    st.subheader("Upcoming deadlines")
    upcoming = [
        task
        for task in tasks
        if task.status != "done"
        and (due := parse_date(task.due_date)) is not None
        and date.today() <= due <= date.today() + timedelta(days=7)
    ]
    if upcoming:
        st.dataframe(
            [
                {
                    "Task": task.title,
                    "Due": task.due_date,
                    "Priority": task.priority.title(),
                    "Status": task.status.replace("_", " ").title(),
                }
                for task in sorted(upcoming, key=lambda item: parse_date(item.due_date))
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("No deadlines in the next seven days.")


def page_tasks() -> None:
    st.title("My tasks")
    project_ids, project_labels = project_choices()
    with st.expander("Create a task", expanded=True):
        task_tab, ai_tab = st.tabs(["Add manually", "Draft with AI"])
        with task_tab:
            save_task_form(None, "create", project_ids, project_labels)
        with ai_tab:
            if not api_key_available():
                st.info("Add GROQ_API_KEY in app secrets to draft tasks with AI.")
            with st.form("ai-task-draft"):
                natural_request = st.text_area(
                    "Describe one or more tasks",
                    placeholder="Prepare for my interview tomorrow and finish the report by Friday.",
                )
                draft_submitted = st.form_submit_button(
                    "Create editable draft", disabled=not api_key_available()
                )
            if draft_submitted:
                try:
                    drafts = extract_task_drafts(natural_request)
                    if not drafts:
                        st.warning("The request did not contain a clear task to add.")
                    else:
                        st.session_state["task_drafts"] = [
                            draft.model_dump() for draft in drafts
                        ]
                        st.rerun()
                except (APIError, RuntimeError, ValueError) as error:
                    friendly_error(error)
            for draft_index, raw_draft in enumerate(
                st.session_state.get("task_drafts", [])
            ):
                draft = TaskDraft.model_validate(raw_draft)
                draft_due = parse_date(draft.due_date)
                with st.form(f"approve-ai-draft-{draft_index}"):
                    st.caption("Review and edit before saving")
                    draft_title = st.text_input(
                        "Title", value=draft.title, key=f"draft-title-{draft_index}"
                    )
                    draft_description = st.text_area(
                        "Description",
                        value=draft.description,
                        key=f"draft-description-{draft_index}",
                    )
                    dcol1, dcol2, dcol3 = st.columns(3)
                    draft_priority = dcol1.selectbox(
                        "Priority",
                        TASK_PRIORITIES,
                        index=TASK_PRIORITIES.index(draft.priority)
                        if draft.priority in TASK_PRIORITIES
                        else 1,
                        key=f"draft-priority-{draft_index}",
                    )
                    draft_has_due = dcol2.checkbox(
                        "Has a due date",
                        value=draft_due is not None,
                        key=f"draft-has-due-{draft_index}",
                    )
                    draft_due_date = dcol2.date_input(
                        "Due date",
                        value=draft_due or date.today(),
                        disabled=not draft_has_due,
                        key=f"draft-due-{draft_index}",
                    )
                    draft_minutes = dcol3.number_input(
                        "Minutes",
                        min_value=1,
                        max_value=1440,
                        value=max(1, draft.estimated_minutes),
                        step=15,
                        key=f"draft-minutes-{draft_index}",
                    )
                    approve = st.form_submit_button("Save this task", type="primary")
                if approve:
                    try:
                        save_task(
                            title=draft_title,
                            description=draft_description,
                            priority=draft_priority,
                            due_date=draft_due_date.isoformat()
                            if draft_has_due
                            else "",
                            estimated_minutes=int(draft_minutes),
                            category=draft.category,
                        )
                        remaining_drafts = st.session_state.get("task_drafts", [])
                        remaining_drafts.pop(draft_index)
                        st.session_state["task_drafts"] = remaining_drafts
                        st.success("Task saved.")
                        st.rerun()
                    except ValueError as error:
                        friendly_error(error)

    st.divider()
    search_cols = st.columns([2, 1, 1])
    search = search_cols[0].text_input("Search tasks")
    status_filter = search_cols[1].selectbox(
        "Status", ["All", *TASK_STATUSES], key="task-status-filter"
    )
    priority_filter = search_cols[2].selectbox(
        "Priority", ["All", *TASK_PRIORITIES], key="task-priority-filter"
    )
    filtered = list_tasks(
        status=status_filter, priority=priority_filter, search=search
    )
    view_choice = st.radio(
        "Task view", ["List", "Kanban"], horizontal=True, label_visibility="collapsed"
    )
    if view_choice == "List":
        st.caption(f"{len(filtered)} task(s)")
        bulk_ids = st.multiselect(
            "Select tasks for a bulk status update",
            [task.id for task in filtered],
            format_func=lambda task_id: next(
                f"#{task.id} · {task.title}"
                for task in filtered
                if task.id == task_id
            ),
            key="bulk-task-selection",
        )
        bulk_cols = st.columns([1, 1, 4])
        bulk_status = bulk_cols[0].selectbox(
            "Set selected to", TASK_STATUSES, key="bulk-status"
        )
        if bulk_cols[1].button("Apply", disabled=not bulk_ids):
            for task_id in bulk_ids:
                task = next(item for item in filtered if item.id == task_id)
                save_task(
                    todo_id=task.id,
                    title=task.title,
                    description=task.description,
                    priority=task.priority,
                    status=bulk_status,
                    due_date=task.due_date,
                    estimated_minutes=task.estimated_minutes,
                    actual_minutes=task.actual_minutes,
                    project_id=task.project_id,
                    tags=task.tags,
                    category=task.category,
                )
            st.success(f"Updated {len(bulk_ids)} task(s).")
            st.rerun()
        for task in filtered:
            render_task_editor(task, project_ids, project_labels)
    else:
        columns = st.columns(len(TASK_STATUSES))
        for column, status in zip(columns, TASK_STATUSES):
            with column:
                st.subheader(status.replace("_", " ").title())
                for task in filtered:
                    if task.status != status:
                        continue
                    st.markdown(f"**{task.title}**")
                    st.caption(
                        f"{task.priority.title()} · {task.estimated_minutes} min"
                        + (f" · {task.due_date}" if task.due_date else "")
                    )
                    next_status = (
                        "done" if status != "done" else "pending"
                    )
                    if st.button(
                        f"Move to {next_status.replace('_', ' ')}",
                        key=f"kanban-{task.id}",
                    ):
                        save_task(
                            todo_id=task.id,
                            title=task.title,
                            description=task.description,
                            priority=task.priority,
                            status=next_status,
                            due_date=task.due_date,
                            estimated_minutes=task.estimated_minutes,
                            actual_minutes=task.actual_minutes,
                            project_id=task.project_id,
                            tags=task.tags,
                            category=task.category,
                        )
                        st.rerun()
                    with st.expander("Edit"):
                        render_task_editor(task, project_ids, project_labels)


def page_planner() -> None:
    st.title("AI planner")
    st.caption(
        "A deterministic planner ranks deadlines and priority, preserves accepted blocks, "
        "reserves a lunch break, and adds short buffers."
    )
    planner_date = st.date_input("Plan for", value=date.today(), key="planner-date")
    try:
        work_start = time.fromisoformat(get_setting("work_start", "09:00"))
        work_end = time.fromisoformat(get_setting("work_end", "17:00"))
    except ValueError:
        work_start, work_end = time(9, 0), time(17, 0)
    daily_limit = int(get_setting("daily_limit", "360"))
    if work_start >= work_end:
        st.error("Update settings so the work day ends after it starts.")
        return
    proposals, warnings = propose_day_schedule(
        planner_date,
        list_tasks(),
        work_start,
        work_end,
        daily_limit,
    )
    current_blocks = get_day_schedule(planner_date)
    if current_blocks:
        st.subheader("Accepted blocks")
        st.dataframe(
            [
                {
                    "Start": block.starts_at[11:16],
                    "End": block.ends_at[11:16],
                    "Task": block.title,
                }
                for block in current_blocks
            ],
            width="stretch",
            hide_index=True,
        )
    if proposals:
        st.subheader("Proposed schedule")
        st.dataframe(
            [
                {
                    "Start": str(item["start"])[11:16],
                    "End": str(item["end"])[11:16],
                    "Task": item["title"],
                    "Minutes": item["minutes"],
                    "Why this order": item["reason"],
                }
                for item in proposals
            ],
            width="stretch",
            hide_index=True,
        )
        st.session_state["schedule_proposal"] = proposals
        action_cols = st.columns(2)
        if action_cols[0].button("Accept proposed blocks", type="primary"):
            try:
                count = accept_schedule(st.session_state["schedule_proposal"])
                st.session_state.pop("schedule_proposal", None)
                st.success(f"Accepted {count} schedule block(s).")
                st.rerun()
            except ValueError as error:
                friendly_error(error)
        if action_cols[1].button("Reject proposal"):
            st.session_state.pop("schedule_proposal", None)
            st.info("Proposal discarded; no schedule was changed.")
    else:
        st.info("No open tasks fit this plan, or your day is already fully scheduled.")
    for warning in warnings:
        st.warning(warning)


def page_projects() -> None:
    st.title("Projects")
    with st.expander("Create project", expanded=not list_projects()):
        with st.form("create-project"):
            name = st.text_input("Project name")
            description = st.text_area("Description")
            if st.form_submit_button("Create project", type="primary"):
                try:
                    save_project(name, description)
                    st.success("Project created.")
                    st.rerun()
                except ValueError as error:
                    friendly_error(error)
    projects = list_projects()
    if not projects:
        st.info("Create a project to group tasks and milestones.")
        return
    _, project_labels = project_choices()
    selected_project = st.selectbox(
        "Project",
        [project.id for project in projects],
        format_func=lambda project_id: project_labels[project_id],
    )
    project = next(item for item in projects if item.id == selected_project)
    done, total = project_progress(project.id)
    st.subheader(project.name)
    st.write(project.description or "No description yet.")
    st.progress(done / total if total else 0.0, text=f"{done} of {total} tasks complete")
    tasks = list_tasks(project_id=project.id)
    for task in tasks:
        st.write(
            f"{'✓' if task.status == 'done' else '○'} **{task.title}** · "
            f"{task.status.replace('_', ' ').title()} · {task.priority.title()}"
        )
        if task.status != "done" and st.button(
            "Mark complete", key=f"project-complete-{task.id}"
        ):
            save_task(
                todo_id=task.id,
                title=task.title,
                description=task.description,
                priority=task.priority,
                status="done",
                due_date=task.due_date,
                estimated_minutes=task.estimated_minutes,
                actual_minutes=task.actual_minutes,
                project_id=task.project_id,
                tags=task.tags,
                category=task.category,
            )
            st.rerun()

    st.subheader("Milestones")
    with st.form("create-milestone"):
        milestone_title = st.text_input("Milestone")
        milestone_has_date = st.checkbox("Set a milestone date")
        milestone_date = st.date_input(
            "Date", value=date.today(), disabled=not milestone_has_date
        )
        if st.form_submit_button("Add milestone"):
            try:
                save_milestone(
                    project.id,
                    milestone_title,
                    milestone_date.isoformat() if milestone_has_date else "",
                )
                st.success("Milestone added.")
                st.rerun()
            except ValueError as error:
                friendly_error(error)
    for milestone in list_milestones(project.id):
        st.caption(
            f"{'✓' if milestone.status == 'done' else '○'} {milestone.title}"
            + (f" · {milestone.due_date}" if milestone.due_date else "")
        )


def page_calendar() -> None:
    st.title("Calendar")
    focus_day = st.date_input("Choose a month and day", value=date.today())
    year, month = focus_day.year, focus_day.month
    st.subheader(f"{calendar.month_name[month]} {year}")
    tasks = list_tasks()
    due_by_date: dict[date, list[str]] = {}
    for task in tasks:
        task_due = parse_date(task.due_date)
        if task_due and task_due.year == year and task_due.month == month:
            due_by_date.setdefault(task_due, []).append(task.title)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for column, day_name in zip(st.columns(7), day_names):
        column.markdown(f"**{day_name}**")
    for week in calendar.monthcalendar(year, month):
        columns = st.columns(7)
        for column, day_number in zip(columns, week):
            with column:
                if not day_number:
                    st.write(" ")
                    continue
                current_day = date(year, month, day_number)
                st.markdown(
                    f"**{day_number}**"
                    + (" · today" if current_day == date.today() else "")
                )
                for title in due_by_date.get(current_day, [])[:3]:
                    st.caption(f"• {title}")
                extra = len(due_by_date.get(current_day, [])) - 3
                if extra > 0:
                    st.caption(f"+ {extra} more")

    st.subheader(f"Schedule for {focus_day.isoformat()}")
    day_blocks = get_day_schedule(focus_day)
    day_tasks = [task for task in tasks if parse_date(task.due_date) == focus_day]
    if day_blocks:
        st.dataframe(
            [
                {
                    "Start": block.starts_at[11:16],
                    "End": block.ends_at[11:16],
                    "Task": block.title,
                }
                for block in day_blocks
            ],
            width="stretch",
            hide_index=True,
        )
    if day_tasks:
        for task in day_tasks:
            st.write(f"• {task.title} · {task.status.replace('_', ' ').title()}")
    if not day_blocks and not day_tasks:
        st.caption("No deadlines or accepted time blocks on this day.")

    st.subheader("Add a time block")
    task_options = [None, *(task.id for task in tasks if task.status != "done")]
    task_labels = {None: "No linked task"}
    task_labels.update(
        {
            task.id: f"#{task.id} · {task.title}"
            for task in tasks
            if task.status != "done"
        }
    )
    with st.form("manual-schedule-block"):
        block_title = st.text_input("Title")
        linked_task = st.selectbox(
            "Link to task",
            task_options,
            format_func=lambda task_id: task_labels[task_id],
        )
        start_col, end_col = st.columns(2)
        starts_at = start_col.time_input("Start time", value=time(9, 0))
        ends_at = end_col.time_input("End time", value=time(10, 0))
        if st.form_submit_button("Save accepted block"):
            try:
                save_manual_schedule(
                    block_title,
                    datetime.combine(focus_day, starts_at),
                    datetime.combine(focus_day, ends_at),
                    linked_task,
                )
                st.success("Schedule block saved.")
                st.rerun()
            except ValueError as error:
                friendly_error(error)


def page_analytics() -> None:
    st.title("Analytics")
    tasks = list_tasks()
    summary = productivity_summary()
    metrics = st.columns(5)
    metrics[0].metric("Total tasks", len(tasks))
    metrics[1].metric("Completed", sum(task.status == "done" for task in tasks))
    metrics[2].metric("Overdue", summary["overdue"])
    metrics[3].metric("On-time completion", f'{summary["on_time_rate"]}%')
    metrics[4].metric(
        "Weekly completion rate", f'{summary["weekly_completion_rate"]}%'
    )

    today = date.today()
    days = [today - timedelta(days=offset) for offset in reversed(range(7))]
    completions = {}
    for day in days:
        completions[day.strftime("%a")] = sum(
            task.status == "done"
            and bool(task.completed_at)
            and parse_date(task.completed_at) == day
            for task in tasks
        )
    st.subheader("Tasks completed · last 7 days")
    st.line_chart(completions)

    left, right = st.columns(2)
    with left:
        st.subheader("Open tasks by priority")
        priority_counts = {
            priority.title(): sum(
                task.status != "done" and task.priority == priority for task in tasks
            )
            for priority in TASK_PRIORITIES
        }
        st.bar_chart(priority_counts)
    with right:
        st.subheader("Project completion")
        projects = list_projects()
        if projects:
            project_rates = {}
            for project in projects:
                done, total = project_progress(project.id)
                project_rates[project.name] = round(done / total * 100) if total else 0
            st.bar_chart(project_rates)
        else:
            st.caption("Add projects to see their completion trends.")
    if tasks:
        st.subheader("Planned versus actual time")
        st.dataframe(
            [
                {
                    "Task": task.title,
                    "Estimated (min)": task.estimated_minutes,
                    "Actual (min)": task.actual_minutes,
                }
                for task in tasks
            ],
            width="stretch",
            hide_index=True,
        )


def page_assistant() -> None:
    st.title("AI assistant")
    st.caption("Use natural language to query tasks or request changes.")
    if not api_key_available():
        st.info("Add GROQ_API_KEY in Streamlit Secrets to enable the assistant.")
        return
    if "assistant" not in st.session_state:
        try:
            st.session_state["assistant"] = create_assistant()
        except (APIError, RuntimeError, ValueError) as error:
            friendly_error(error)
            return
    history = st.session_state.setdefault("assistant_history", [])
    for item in history:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])
    prompt = st.chat_input("Ask about your tasks…")
    if prompt:
        history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        try:
            result = st.session_state["assistant"].invoke(
                {"messages": history},
                {"configurable": {"thread_id": "portfolio-demo"}},
            )
            answer = str(result["messages"][-1].content)
            history.append({"role": "assistant", "content": answer})
            with st.chat_message("assistant"):
                st.markdown(answer)
        except (APIError, RuntimeError, ValueError) as error:
            friendly_error(error)


def page_settings() -> None:
    st.title("Settings")
    st.caption("Settings apply to this shared demo.")
    try:
        saved_start = time.fromisoformat(get_setting("work_start", "09:00"))
        saved_end = time.fromisoformat(get_setting("work_end", "17:00"))
    except ValueError:
        saved_start, saved_end = time(9, 0), time(17, 0)
    with st.form("work-settings"):
        start_col, end_col = st.columns(2)
        work_start = start_col.time_input("Workday starts", value=saved_start)
        work_end = end_col.time_input("Workday ends", value=saved_end)
        daily_limit = st.number_input(
            "Daily planned-work limit (minutes)",
            min_value=30,
            max_value=720,
            value=int(get_setting("daily_limit", "360")),
            step=30,
        )
        timezone_name = st.text_input(
            "Timezone label (for reference)",
            value=get_setting("timezone", "Local time"),
        )
        if st.form_submit_button("Save settings", type="primary"):
            if work_start >= work_end:
                st.error("Workday end must be later than its start.")
            else:
                set_setting("work_start", work_start.isoformat(timespec="minutes"))
                set_setting("work_end", work_end.isoformat(timespec="minutes"))
                set_setting("daily_limit", str(int(daily_limit)))
                set_setting("timezone", timezone_name.strip() or "Local time")
                st.success("Settings saved.")
                st.rerun()
    st.warning(
        "This is a shared, unauthenticated portfolio demo. Do not enter private or "
        "sensitive tasks. Settings and tasks are visible to every visitor."
    )


with st.sidebar:
    st.markdown("## TaskMind")
    st.caption("AI productivity workspace")
    selected_page = st.radio(
        "Navigate",
        [
            "Overview",
            "My tasks",
            "AI planner",
            "Projects",
            "Calendar",
            "Analytics",
            "AI assistant",
            "Settings",
        ],
        label_visibility="collapsed",
        key="navigation",
    )
    st.divider()
    st.caption("Shared public demo · avoid sensitive data")

page_routes = {
    "Overview": page_dashboard,
    "My tasks": page_tasks,
    "AI planner": page_planner,
    "Projects": page_projects,
    "Calendar": page_calendar,
    "Analytics": page_analytics,
    "AI assistant": page_assistant,
    "Settings": page_settings,
}
page_routes[selected_page]()
