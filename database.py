import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import Column, ForeignKey, Integer, String, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///todos.db")
engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_options)
LocalSession = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    description = Column(String(1000), default="")
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(String(30), nullable=False)


class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(String(500), default="")
    status = Column(String(20), default="pending")
    priority = Column(String(20), default="medium")
    due_date = Column(String(20), default="")
    created_at = Column(String(20), nullable=False)
    updated_at = Column(String(30), default="")
    completed_at = Column(String(30), default="")
    estimated_minutes = Column(Integer, default=30, nullable=False)
    actual_minutes = Column(Integer, default=0, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    tags = Column(String(500), default="")
    category = Column(String(80), default="")
    start_at = Column(String(30), default="")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "due_date": self.due_date,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "estimated_minutes": self.estimated_minutes,
            "actual_minutes": self.actual_minutes,
            "project_id": self.project_id,
            "tags": self.tags,
            "category": self.category,
            "start_at": self.start_at,
        }


class Milestone(Base):
    __tablename__ = "milestones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    title = Column(String(160), nullable=False)
    due_date = Column(String(20), default="")
    status = Column(String(20), default="pending", nullable=False)
    created_at = Column(String(30), nullable=False)


class ScheduleBlock(Base):
    __tablename__ = "schedule_blocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    todo_id = Column(Integer, ForeignKey("todos.id"), nullable=True)
    title = Column(String(200), nullable=False)
    starts_at = Column(String(30), nullable=False)
    ends_at = Column(String(30), nullable=False)
    accepted = Column(Integer, default=0, nullable=False)
    created_at = Column(String(30), nullable=False)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(80), primary_key=True)
    value = Column(String(500), nullable=False)


_TODO_ADDITIONS = {
    "updated_at": "VARCHAR(30) NOT NULL DEFAULT ''",
    "completed_at": "VARCHAR(30) NOT NULL DEFAULT ''",
    "estimated_minutes": "INTEGER NOT NULL DEFAULT 30",
    "actual_minutes": "INTEGER NOT NULL DEFAULT 0",
    "project_id": "INTEGER",
    "tags": "VARCHAR(500) NOT NULL DEFAULT ''",
    "category": "VARCHAR(80) NOT NULL DEFAULT ''",
    "start_at": "VARCHAR(30) NOT NULL DEFAULT ''",
}


def init_db() -> None:
    """Create new tables and add missing task columns without replacing existing rows."""
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    existing_columns = {column["name"] for column in inspector.get_columns("todos")}
    with engine.begin() as connection:
        for column_name, column_definition in _TODO_ADDITIONS.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE todos ADD COLUMN {column_name} "
                        f"{column_definition}"
                    )
                )


def timestamp_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="minutes")
