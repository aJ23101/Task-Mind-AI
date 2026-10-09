from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///todos.db"  ### PGsQL,

engine = create_engine(DATABASE_URL)
LocalSession = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(String(500), default="")
    status = Column(String(20), default="pending")  ##pending | in_progress | done
    priority = Column(String(20), default="medium")  ## low, medium, high
    due_date = Column(String(20), default="")
    created_at = Column(String(20), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "due_date": self.due_date,
            "created_at": self.created_at,
        }


def init_db():
    Base.metadata.create_all(engine)
