from datetime import date, datetime, time
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import services
from ai_service import get_chat_model
from database import Base


@pytest.fixture
def isolated_database(monkeypatch):
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    test_sessions = sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(services, "LocalSession", test_sessions)
    yield
    test_engine.dispose()


def test_task_crud_persists_fields_and_completion(isolated_database):
    task_id = services.save_task(
        title="Prepare demo",
        priority="high",
        due_date="2026-10-10",
        estimated_minutes=45,
        tags="portfolio, demo",
    )
    task = services.get_task(task_id)
    assert task is not None
    assert task.title == "Prepare demo"
    assert task.status == "pending"

    services.save_task(
        todo_id=task_id,
        title=task.title,
        priority=task.priority,
        status="done",
        due_date=task.due_date,
        estimated_minutes=task.estimated_minutes,
        tags=task.tags,
    )
    completed_task = services.get_task(task_id)
    assert completed_task is not None
    assert completed_task.status == "done"
    assert completed_task.completed_at

    services.delete_task(task_id)
    assert services.get_task(task_id) is None


def test_task_input_validation(isolated_database):
    with pytest.raises(ValueError, match="title"):
        services.save_task(title=" ")
    with pytest.raises(ValueError, match="priority"):
        services.save_task(title="Task", priority="urgent")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        services.save_task(title="Task", due_date="sometime Friday")


def test_prioritization_and_planning_preserve_accepted_blocks(isolated_database):
    high = services.save_task(
        title="High priority",
        priority="high",
        due_date="2026-10-09",
        estimated_minutes=120,
    )
    low = services.save_task(title="Low priority", priority="low", estimated_minutes=30)
    tasks = services.list_tasks()
    ranked = services.rank_tasks(tasks, date(2026, 10, 9))
    assert [task.id for task in ranked][:2] == [high, low]

    proposals, warnings = services.propose_day_schedule(
        date(2026, 10, 9),
        tasks,
        work_start=time(9, 0),
        work_end=time(17, 0),
        max_daily_minutes=180,
    )
    assert proposals
    assert not warnings
    assert all(
        datetime.fromisoformat(str(block["end"]))
        <= datetime.combine(date(2026, 10, 9), time(12, 30))
        or datetime.fromisoformat(str(block["start"]))
        >= datetime.combine(date(2026, 10, 9), time(13, 0))
        for block in proposals
    )

    accepted_count = services.accept_schedule(proposals)
    assert accepted_count == len(proposals)
    accepted_before = services.get_day_schedule(date(2026, 10, 9))
    next_proposal, _ = services.propose_day_schedule(
        date(2026, 10, 9),
        tasks,
        max_daily_minutes=360,
    )
    assert len(services.get_day_schedule(date(2026, 10, 9))) == len(accepted_before)
    assert all(
        str(item["start"]) != block.starts_at
        for item in next_proposal
        for block in accepted_before
    )


def test_manual_schedule_rejects_overlaps(isolated_database):
    day = date(2026, 10, 9)
    services.save_manual_schedule(
        "Focus block",
        datetime.combine(day, time(10)),
        datetime.combine(day, time(11)),
    )
    with pytest.raises(ValueError, match="overlaps"):
        services.save_manual_schedule(
            "Conflicting block",
            datetime.combine(day, time(10, 30)),
            datetime.combine(day, time(11, 30)),
        )


def test_projects_and_milestones(isolated_database):
    project_id = services.save_project("Portfolio", "Public demo")
    task_id = services.save_task(title="Deploy", project_id=project_id)
    services.save_milestone(project_id, "First release", "2026-10-10")
    assert services.project_progress(project_id) == (0, 1)
    services.save_task(
        todo_id=task_id,
        title="Deploy",
        status="done",
        project_id=project_id,
    )
    assert services.project_progress(project_id) == (1, 1)
    assert services.list_milestones(project_id)[0].title == "First release"


def test_productivity_summary_calculates_on_time_rate(isolated_database):
    on_time_id = services.save_task(title="On time", due_date="2026-10-10")
    late_id = services.save_task(title="Late", due_date="2026-10-08")
    for task_id in (on_time_id, late_id):
        task = services.get_task(task_id)
        assert task is not None
        services.save_task(
            todo_id=task_id,
            title=task.title,
            status="done",
            due_date=task.due_date,
        )
    summary = services.productivity_summary(date(2026, 10, 9))
    assert summary["on_time_rate"] == 50.0


def test_ai_client_reports_missing_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        get_chat_model()


def test_parse_date_accepts_legacy_and_iso_values():
    assert services.parse_date("25-03-2026") == date(2026, 3, 25)
    assert services.parse_date("2026-10-09T18:58+05:30") == date(2026, 10, 9)
    assert services.parse_date("not a date") is None


def test_planner_schedules_estimated_work_left_after_accepted_block(
    isolated_database,
):
    task_id = services.save_task(title="Build feature", estimated_minutes=90)
    services.save_manual_schedule(
        "Existing focus",
        datetime(2026, 10, 9, 9, 0),
        datetime(2026, 10, 9, 9, 30),
        todo_id=task_id,
    )
    proposals, _ = services.propose_day_schedule(
        date(2026, 10, 9), services.list_tasks()
    )
    assert sum(int(proposal["minutes"]) for proposal in proposals) == 60


def test_streamlit_navigation_pages_render_without_exceptions():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "app.py",
        default_timeout=20,
    ).run()
    assert not app.exception, [exception.message for exception in app.exception]
    for page in (
        "My tasks",
        "AI planner",
        "Projects",
        "Calendar",
        "Analytics",
        "AI assistant",
        "Settings",
        "Overview",
    ):
        app.session_state["navigation"] = page
        app.run()
        assert not app.exception, (
            f"{page}: {[exception.message for exception in app.exception]}"
        )
