import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tasks.db")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    priority = Column(String, default="medium")   # low, medium, high
    due_date = Column(String, nullable=True)       # YYYY-MM-DD
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    # Habit fields
    is_habit = Column(Boolean, default=False)
    habit_frequency = Column(String, nullable=True)  # daily, weekly
    goal_id = Column(Integer, nullable=True)          # linked goal

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "due_date": self.due_date,
            "completed": self.completed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "is_habit": self.is_habit,
            "habit_frequency": self.habit_frequency,
            "goal_id": self.goal_id,
        }


class UserProgress(Base):
    __tablename__ = "user_progress"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, unique=True, index=True)   # YYYY-MM-DD
    tasks_completed = Column(Integer, default=0)
    xp_earned = Column(Integer, default=0)

    def to_dict(self):
        return {
            "date": self.date,
            "tasks_completed": self.tasks_completed,
            "xp_earned": self.xp_earned,
        }


class ChatMemory(Base):
    """Persistent chat history — survives server restarts."""
    __tablename__ = "chat_memory"
    id = Column(Integer, primary_key=True, index=True)
    role = Column(String, nullable=False)   # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Goal(Base):
    """Weekly/monthly goals that auto-generate tasks."""
    __tablename__ = "goals"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    timeframe = Column(String, default="weekly")   # weekly, monthly, custom
    deadline = Column(String, nullable=True)        # YYYY-MM-DD
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "timeframe": self.timeframe,
            "deadline": self.deadline,
            "completed": self.completed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Habit(Base):
    """Habits to track daily/weekly consistency."""
    __tablename__ = "habits"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    frequency = Column(String, default="daily")   # daily, weekly
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    last_checked = Column(String, nullable=True)   # YYYY-MM-DD last completed
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "frequency": self.frequency,
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "last_checked": self.last_checked,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DailyBriefing(Base):
    """Stores today's briefing so it's only generated once per day."""
    __tablename__ = "daily_briefings"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, unique=True, index=True)   # YYYY-MM-DD
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
