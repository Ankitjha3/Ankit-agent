import os
import base64
from datetime import datetime, date, timedelta
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from backend.database import get_db, init_db, Task, UserProgress, ChatMemory, Goal, Habit, DailyBriefing
from backend.agent import get_agent_executor, run_agent
from langchain_core.messages import HumanMessage, AIMessage

app = FastAPI(title="Ankit Agent")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_db()

# ─── Pydantic Models ───────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    description: str = None
    priority: str = "medium"
    due_date: str = None
    is_habit: bool = False
    habit_frequency: str = None
    goal_id: int = None

class ChatMessage(BaseModel):
    message: str

class GoalCreate(BaseModel):
    title: str
    description: str = None
    timeframe: str = "weekly"
    deadline: str = None

class HabitCreate(BaseModel):
    title: str
    description: str = None
    frequency: str = "daily"

class HabitCheck(BaseModel):
    habit_id: int

# ─── Helpers ──────────────────────────────────────────────────────────────────

XP_PER_TASK = {"high": 30, "medium": 20, "low": 10}

LEVELS = [
    (0,    "Beginner",   "🌱"),
    (100,  "Apprentice", "⚡"),
    (300,  "Achiever",   "🔥"),
    (600,  "Hustler",    "💪"),
    (1000, "Pro",        "🚀"),
    (1500, "Expert",     "🌟"),
    (2500, "Master",     "👑"),
    (4000, "Legend",     "🏆"),
]

def get_level_info(total_xp: int) -> dict:
    level_num, title, emoji, next_xp = 1, LEVELS[0][1], LEVELS[0][2], LEVELS[1][0]
    for i, (xp_req, lvl_title, lvl_emoji) in enumerate(LEVELS):
        if total_xp >= xp_req:
            level_num = i + 1
            title = lvl_title
            emoji = lvl_emoji
            next_xp = LEVELS[i + 1][0] if i + 1 < len(LEVELS) else xp_req
        else:
            break
    cur = LEVELS[level_num - 1][0]
    xp_in = total_xp - cur
    xp_need = next_xp - cur
    pct = min(100, int((xp_in / xp_need) * 100)) if xp_need > 0 else 100
    return {
        "level": level_num, "title": title, "emoji": emoji,
        "total_xp": total_xp, "xp_in_level": xp_in,
        "xp_to_next": xp_need - xp_in, "progress_pct": pct,
        "next_level_title": LEVELS[level_num][1] if level_num < len(LEVELS) else title,
    }

def calculate_streak(db: Session) -> dict:
    records = db.query(UserProgress).order_by(UserProgress.date.desc()).all()
    dates = sorted([r.date for r in records], reverse=True)
    if not dates:
        return {"current_streak": 0, "longest_streak": 0, "active_today": False}
    today = date.today().isoformat()
    active_today = dates[0] == today
    current_streak = 0
    check = today if active_today else (date.today() - timedelta(days=1)).isoformat()
    for d in dates:
        if d == check:
            current_streak += 1
            check = (date.fromisoformat(check) - timedelta(days=1)).isoformat()
        else:
            break
    longest, run = 0, 1
    for i in range(1, len(sorted(dates))):
        s = sorted(dates)
        if (date.fromisoformat(s[i]) - date.fromisoformat(s[i-1])).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    if dates:
        longest = max(longest, 1)
    return {"current_streak": current_streak, "longest_streak": longest, "active_today": active_today}

def record_daily_activity(db: Session, xp: int):
    today = date.today().isoformat()
    rec = db.query(UserProgress).filter(UserProgress.date == today).first()
    if rec:
        rec.tasks_completed += 1
        rec.xp_earned += xp
    else:
        db.add(UserProgress(date=today, tasks_completed=1, xp_earned=xp))
    db.commit()

def get_appreciation_message(task_title: str) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or "your_groq_api_key_here" in api_key:
        return f"Great job completing '{task_title}'! 🎉"
    try:
        import httpx
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "temperature": 0.8, "max_tokens": 100,
                  "messages": [{"role": "user", "content": f"User completed: '{task_title}'. Give 1-2 sentence enthusiastic praise with emojis."}]},
            timeout=15.0, verify=False
        )
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return f"Awesome work on '{task_title}'! 🚀"

def load_chat_history(db: Session, limit: int = 20):
    """Load recent chat history from DB as langchain messages."""
    rows = db.query(ChatMemory).order_by(ChatMemory.created_at.desc()).limit(limit).all()
    rows.reverse()
    messages = []
    for r in rows:
        if r.role == "user":
            messages.append(HumanMessage(content=r.content))
        else:
            messages.append(AIMessage(content=r.content))
    return messages

def save_chat_message(db: Session, role: str, content: str):
    """Persist a chat message to DB."""
    db.add(ChatMemory(role=role, content=content))
    db.commit()
    # Keep only last 100 messages
    total = db.query(ChatMemory).count()
    if total > 100:
        oldest = db.query(ChatMemory).order_by(ChatMemory.created_at.asc()).first()
        if oldest:
            db.delete(oldest)
            db.commit()

# ─── Task Endpoints ────────────────────────────────────────────────────────────

@app.get("/api/tasks")
def list_tasks_api(completed: bool = None, db: Session = Depends(get_db)):
    query = db.query(Task)
    if completed is not None:
        query = query.filter(Task.completed == completed)
    return [t.to_dict() for t in query.order_by(Task.completed.asc(), Task.created_at.desc()).all()]

@app.post("/api/tasks")
def create_task_api(payload: TaskCreate, db: Session = Depends(get_db)):
    p = (payload.priority or "medium").lower()
    if p not in ["low", "medium", "high"]:
        p = "medium"
    if not payload.title or not payload.title.strip():
        raise HTTPException(status_code=400, detail="Task title cannot be empty")
    task = Task(
        title=payload.title.strip(), description=payload.description,
        priority=p, due_date=payload.due_date or None, completed=False,
        is_habit=payload.is_habit, habit_frequency=payload.habit_frequency,
        goal_id=payload.goal_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task.to_dict()

@app.post("/api/tasks/{task_id}/complete")
def complete_task_api(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.completed:
        return {"task": task.to_dict(), "appreciation": "Already done! 🙌", "xp_earned": 0}
    task.completed = True
    task.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    xp = XP_PER_TASK.get(task.priority, 20)
    record_daily_activity(db, xp)
    appreciation = get_appreciation_message(task.title)
    save_chat_message(db, "assistant", appreciation)
    return {"task": task.to_dict(), "appreciation": appreciation, "xp_earned": xp}

@app.delete("/api/tasks/{task_id}")
def delete_task_api(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"status": "success"}

# ─── Progress Endpoint ─────────────────────────────────────────────────────────

@app.get("/api/progress")
def get_progress_api(db: Session = Depends(get_db)):
    import sqlalchemy
    all_tasks = db.query(Task).all()
    completed_tasks = [t for t in all_tasks if t.completed]
    pending_tasks = [t for t in all_tasks if not t.completed]
    xp_tasks = sum(XP_PER_TASK.get(t.priority, 20) for t in completed_tasks)
    hist_xp = db.query(sqlalchemy.func.sum(UserProgress.xp_earned)).scalar() or 0
    total_xp = max(xp_tasks, hist_xp)
    level_info = get_level_info(total_xp)
    streak_info = calculate_streak(db)
    daily = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        rec = db.query(UserProgress).filter(UserProgress.date == d).first()
        daily.append({"date": d, "tasks_completed": rec.tasks_completed if rec else 0,
                      "xp_earned": rec.xp_earned if rec else 0})
    return {
        "total_tasks": len(all_tasks), "completed": len(completed_tasks),
        "pending": len(pending_tasks),
        "completion_rate": round(len(completed_tasks)/len(all_tasks)*100, 1) if all_tasks else 0,
        "high_priority_pending": sum(1 for t in pending_tasks if t.priority == "high"),
        **level_info, **streak_info, "daily_activity": daily,
    }

# ─── Daily Briefing Endpoint ───────────────────────────────────────────────────

@app.get("/api/briefing")
def get_daily_briefing(db: Session = Depends(get_db)):
    today = date.today().isoformat()
    existing = db.query(DailyBriefing).filter(DailyBriefing.date == today).first()
    if existing:
        return {"briefing": existing.content, "fresh": False}

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or "your_groq_api_key_here" in api_key:
        return {"briefing": None, "fresh": False}

    try:
        # Build context for briefing
        pending = db.query(Task).filter(Task.completed == False).all()
        habits = db.query(Habit).all()
        goals = db.query(Goal).filter(Goal.completed == False).all()
        streak = calculate_streak(db)

        import sqlalchemy
        hist_xp = db.query(sqlalchemy.func.sum(UserProgress.xp_earned)).scalar() or 0
        level = get_level_info(hist_xp)

        context = f"""Today is {today} (day of week: {date.today().strftime('%A')}).

User stats:
- Level {level['level']} {level['emoji']} {level['title']} | {hist_xp} XP
- Current streak: {streak['current_streak']} days
- Pending tasks: {len(pending)}
- Active goals: {len(goals)}
- Habits to track: {len(habits)}

Pending tasks:
{chr(10).join([f"- [{t.priority}] {t.title}" + (f" (due {t.due_date})" if t.due_date else "") for t in pending[:8]]) or "None"}

Active goals:
{chr(10).join([f"- {g.title} ({g.timeframe})" for g in goals[:3]]) or "None"}

Habits:
{chr(10).join([f"- {h.title} | streak: {h.current_streak} days" for h in habits[:5]]) or "None"}"""

        from langchain_groq import ChatGroq
        llm = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=api_key, temperature=0.7)
        prompt = f"""You are Ankit Agent. Generate a short, energetic daily briefing for Ankit.

{context}

Write a 3-4 sentence briefing that:
1. Greets based on day/time feel
2. Highlights the top 1-2 tasks to focus on today
3. Mentions streak if > 1 (celebrate it!)
4. One motivational push

Use Hinglish style, emojis, keep it punchy. Max 4 sentences."""

        briefing = llm.invoke(prompt).content.strip()
        db.add(DailyBriefing(date=today, content=briefing))
        db.commit()
        return {"briefing": briefing, "fresh": True}
    except Exception as e:
        return {"briefing": None, "fresh": False, "error": str(e)}

# ─── Goals Endpoints ───────────────────────────────────────────────────────────

@app.get("/api/goals")
def list_goals(db: Session = Depends(get_db)):
    goals = db.query(Goal).order_by(Goal.created_at.desc()).all()
    result = []
    for g in goals:
        tasks = db.query(Task).filter(Task.goal_id == g.id).all()
        done = sum(1 for t in tasks if t.completed)
        d = g.to_dict()
        d["task_count"] = len(tasks)
        d["tasks_done"] = done
        d["progress_pct"] = round(done / len(tasks) * 100) if tasks else 0
        result.append(d)
    return result

@app.post("/api/goals")
def create_goal(payload: GoalCreate, db: Session = Depends(get_db)):
    goal = Goal(title=payload.title, description=payload.description,
                timeframe=payload.timeframe, deadline=payload.deadline)
    db.add(goal)
    db.commit()
    db.refresh(goal)

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or "your_groq_api_key_here" in api_key:
        return {"goal": goal.to_dict(), "tasks_created": [], "message": "Goal created. Add API key to auto-generate tasks."}

    # Auto-generate tasks using AI
    try:
        from langchain_groq import ChatGroq
        import json as _json
        llm = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=api_key, temperature=0.5)
        prompt = f"""Break down this goal into 4-7 specific, actionable tasks.

Goal: "{payload.title}"
Description: {payload.description or 'None'}
Timeframe: {payload.timeframe}
Deadline: {payload.deadline or 'Not set'}

Return ONLY a JSON array like:
[
  {{"title": "Task name", "priority": "high|medium|low", "description": "brief detail"}},
  ...
]
Keep tasks concrete and achievable. No extra text."""

        resp = llm.invoke(prompt).content.strip()
        import re, json
        match = re.search(r'\[[\s\S]*\]', resp)
        tasks_created = []
        if match:
            tasks_data = json.loads(match.group())
            for td in tasks_data:
                t = Task(
                    title=td.get("title", ""), description=td.get("description"),
                    priority=td.get("priority", "medium"), goal_id=goal.id, completed=False,
                )
                db.add(t)
                tasks_created.append(td.get("title"))
            db.commit()
        return {"goal": goal.to_dict(), "tasks_created": tasks_created,
                "message": f"Goal set! {len(tasks_created)} tasks created automatically."}
    except Exception as e:
        return {"goal": goal.to_dict(), "tasks_created": [], "message": f"Goal created. Task generation failed: {e}"}

@app.delete("/api/goals/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_db)):
    goal = db.query(Goal).filter(Goal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    db.delete(goal)
    db.commit()
    return {"status": "success"}

# ─── Habits Endpoints ──────────────────────────────────────────────────────────

@app.get("/api/habits")
def list_habits(db: Session = Depends(get_db)):
    return [h.to_dict() for h in db.query(Habit).order_by(Habit.created_at.desc()).all()]

@app.post("/api/habits")
def create_habit(payload: HabitCreate, db: Session = Depends(get_db)):
    habit = Habit(title=payload.title, description=payload.description, frequency=payload.frequency)
    db.add(habit)
    db.commit()
    db.refresh(habit)
    return habit.to_dict()

@app.post("/api/habits/{habit_id}/check")
def check_habit(habit_id: int, db: Session = Depends(get_db)):
    habit = db.query(Habit).filter(Habit.id == habit_id).first()
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if habit.last_checked == today:
        return {"habit": habit.to_dict(), "message": "Already checked in today!", "xp_earned": 0}
    # Update streak
    if habit.last_checked == yesterday or habit.last_checked is None:
        habit.current_streak += 1
    else:
        habit.current_streak = 1   # streak broken, restart
    habit.longest_streak = max(habit.longest_streak, habit.current_streak)
    habit.last_checked = today
    db.commit()
    db.refresh(habit)
    xp = 15  # flat XP for habits
    record_daily_activity(db, xp)
    return {"habit": habit.to_dict(), "message": f"✅ {habit.title} done! Streak: {habit.current_streak} days 🔥", "xp_earned": xp}

@app.delete("/api/habits/{habit_id}")
def delete_habit(habit_id: int, db: Session = Depends(get_db)):
    habit = db.query(Habit).filter(Habit.id == habit_id).first()
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    db.delete(habit)
    db.commit()
    return {"status": "success"}

# ─── Chat Endpoint ─────────────────────────────────────────────────────────────

@app.post("/api/chat")
def chat_api(payload: ChatMessage, db: Session = Depends(get_db)):
    if payload.message == "__ping__":
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        return {"response": "", "missing_api_key": not api_key or "your_groq_api_key_here" in api_key}

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or "your_groq_api_key_here" in api_key:
        return {"response": "Set `GROQ_API_KEY` in `.env` and restart.", "missing_api_key": True}

    # Load persistent history from DB
    history = load_chat_history(db, limit=16)
    ai_response = run_agent(payload.message, history)

    if ai_response is None:
        return {"response": "Could not initialize AI Agent.", "missing_api_key": True}

    save_chat_message(db, "user", payload.message)
    save_chat_message(db, "assistant", ai_response)

    return {"response": ai_response, "missing_api_key": False}

# ─── Suggest Endpoint ──────────────────────────────────────────────────────────

@app.get("/api/suggest")
def get_suggestion(db: Session = Depends(get_db)):
    pending = db.query(Task).filter(Task.completed == False).all()
    if not pending:
        return {"suggestion": "All tasks done! Add something new 🎉", "task_id": None}
    def sort_key(t):
        p = {"high": 3, "medium": 2, "low": 1}.get(t.priority.lower(), 2)
        return (-p, t.due_date or "9999-12-31")
    top = sorted(pending, key=sort_key)[0]
    due = f" (due {top.due_date})" if top.due_date else ""
    return {"suggestion": f"Focus on **{top.title}** — **{top.priority}** priority{due}.", "task_id": top.id}

# ─── Image Chat Endpoint ───────────────────────────────────────────────────────

@app.post("/api/chat/image")
async def chat_image_api(
    image: UploadFile = File(...),
    message: str = Form(default="Please read this image and create tasks from what you see."),
    db: Session = Depends(get_db)
):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or "your_groq_api_key_here" in api_key:
        return {"response": "Groq API key missing.", "missing_api_key": True}
    try:
        img_data = await image.read()
        b64 = base64.b64encode(img_data).decode("utf-8")
        mime = image.content_type or "image/jpeg"
        from langchain_groq import ChatGroq
        vision_llm = ChatGroq(model="meta-llama/llama-4-scout-17b-16e-instruct", groq_api_key=api_key, temperature=0.3)
        vision_msg = HumanMessage(content=[
            {"type": "text", "text": f"Extract ALL tasks/to-dos/goals from this image as a numbered list. Note deadlines or priorities if visible. User says: {message}"},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        ])
        extracted = vision_llm.invoke([vision_msg]).content.strip()
        full_msg = f"Photo content:\n{extracted}\n\nCreate tasks for everything above and tell me what to start with."
        history = load_chat_history(db, limit=10)
        ai_response = run_agent(full_msg, history) or f"Photo se ye mila:\n{extracted}"
        save_chat_message(db, "user", f"[Photo] {message}")
        save_chat_message(db, "assistant", ai_response)
        return {"response": ai_response, "missing_api_key": False, "extracted_text": extracted}
    except Exception as e:
        return {"response": f"Image error: {e}", "error": True}

# ─── Static Files ──────────────────────────────────────────────────────────────

# Use absolute path so it works on Railway and local
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def read_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
