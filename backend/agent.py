import os
import json
import re
from datetime import datetime
from backend.database import SessionLocal, Task, UserProgress
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# ── Tool implementations (plain functions, no @tool decorator needed) ──────────

def _add_task(title, description=None, priority="medium", due_date=None):
    db = SessionLocal()
    try:
        p = (priority or "medium").lower()
        if p not in ["low", "medium", "high"]:
            p = "medium"
        task = Task(title=title, description=description, priority=p,
                    due_date=due_date, completed=False)
        db.add(task)
        db.commit()
        db.refresh(task)
        return f"✅ Added: '{task.title}' (ID:{task.id}, {task.priority} priority)"
    except Exception as e:
        return f"Error adding task: {e}"
    finally:
        db.close()

def _list_tasks(status="all"):
    db = SessionLocal()
    try:
        query = db.query(Task)
        if status == "pending":
            query = query.filter(Task.completed == False)
        elif status == "completed":
            query = query.filter(Task.completed == True)
        tasks = query.all()
        if not tasks:
            return f"No {status} tasks."
        lines = []
        for t in tasks:
            icon = "✅" if t.completed else "⏳"
            due = f" | Due:{t.due_date}" if t.due_date else ""
            lines.append(f"{icon} [{t.id}] {t.title} ({t.priority}{due})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
    finally:
        db.close()

def _complete_task(task_id):
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == int(task_id)).first()
        if not task:
            return f"Task ID {task_id} not found."
        if task.completed:
            return f"'{task.title}' already completed!"
        task.completed = True
        task.completed_at = datetime.utcnow()
        db.commit()
        return f"🎉 Completed: '{task.title}' (ID:{task.id})"
    except Exception as e:
        return f"Error: {e}"
    finally:
        db.close()

def _suggest_next():
    db = SessionLocal()
    try:
        pending = db.query(Task).filter(Task.completed == False).all()
        if not pending:
            return "🏆 All tasks done! Add something new."
        def key(t):
            p = {"high": 3, "medium": 2, "low": 1}.get(t.priority.lower(), 2)
            due = t.due_date or "9999-12-31"
            return (-p, due)
        top = sorted(pending, key=key)[0]
        others = len(pending) - 1
        rest = f" | {others} more pending" if others else ""
        return f"👉 Next: **{top.title}** (ID:{top.id} | {top.priority}{rest})"
    except Exception as e:
        return f"Error: {e}"
    finally:
        db.close()

def _get_progress():
    from backend.main import get_level_info, calculate_streak, XP_PER_TASK
    from datetime import date, timedelta
    import sqlalchemy
    db = SessionLocal()
    try:
        all_tasks = db.query(Task).all()
        completed = [t for t in all_tasks if t.completed]
        pending = [t for t in all_tasks if not t.completed]
        xp_tasks = sum(XP_PER_TASK.get(t.priority, 20) for t in completed)
        hist_xp = db.query(sqlalchemy.func.sum(UserProgress.xp_earned)).scalar() or 0
        total_xp = max(xp_tasks, hist_xp)
        lv = get_level_info(total_xp)
        sk = calculate_streak(db)
        rate = round(len(completed) / len(all_tasks) * 100, 1) if all_tasks else 0
        daily = []
        for i in range(6, -1, -1):
            d = (date.today() - timedelta(days=i)).isoformat()
            rec = db.query(UserProgress).filter(UserProgress.date == d).first()
            count = rec.tasks_completed if rec else 0
            daily.append(f"  {d}: {'█'*min(count,5) if count else '·'} ({count})")
        return (
            f"📊 **Progress Report**\n"
            f"🏆 Level {lv['level']} — {lv['emoji']} {lv['title']}\n"
            f"⚡ {total_xp} XP | {lv['xp_to_next']} to {lv['next_level_title']}\n"
            f"🔥 Streak: {sk['current_streak']} days | Best: {sk['longest_streak']}\n"
            f"{'✅ Active today!' if sk['active_today'] else '⚠️ No activity today!'}\n"
            f"📋 {len(completed)}/{len(all_tasks)} done ({rate}%) | {len(pending)} pending\n"
            f"📅 Last 7 days:\n" + "\n".join(daily)
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        db.close()

# ── Tool dispatch ──────────────────────────────────────────────────────────────

TOOLS_SCHEMA = """
You have these ACTIONS. Always output them as a JSON array inside a code block.
THEN the last action MUST be "reply" with your actual message to the user.

```json
[
  {"action": "add_task", "params": {"title": "...", "description": null, "priority": "high|medium|low", "due_date": null}},
  {"action": "reply", "params": {"text": "Your friendly message here"}}
]
```

Available actions:
- add_task: {"title", "description", "priority", "due_date"}
- list_tasks: {"status": "all|pending|completed"}
- complete_task: {"task_id": int}
- suggest_next: {}
- get_progress: {}
- reply: {"text": str}  ← ALWAYS include this last with your message to the user

RULE: The "reply" text must be your actual conversational response — NOT the JSON itself.
If you only need to reply without any tool, just output:
```json
[{"action": "reply", "params": {"text": "your message"}}]
```
"""

SYSTEM_PROMPT = """You are Ankit Agent — a sharp AI productivity coach for Ankit.

""" + TOOLS_SCHEMA + """

## BEHAVIOR
1. When Ankit mentions goals/tasks → use add_task multiple times, then reply with what you created and what to start with
2. When Ankit says "done/ho gaya/kar liya/complete" → use list_tasks(pending) to find the task, then complete_task, then suggest_next, then reply with celebration
3. When asked for progress/streak → use get_progress, then reply
4. When asked what to do next → use suggest_next, then reply
5. You know about Ankit's habits and goals — reference them when relevant
6. Speak Hinglish — match Ankit's energy, use emojis 🎉🔥💪
7. Be concise and energetic

## EXAMPLES
User: "gym jana hai aur python padhna hai"
→ Add tasks, suggest first one, reply in Hinglish with energy

User: "ho gaya gym"
→ list_tasks to find gym task ID, complete_task, suggest_next, celebrate

User: "mera progress?"
→ get_progress, give energetic summary
"""

def _execute_action(action: str, params: dict) -> str:
    if action == "add_task":
        return _add_task(
            title=params.get("title", ""),
            description=params.get("description"),
            priority=params.get("priority", "medium"),
            due_date=params.get("due_date")
        )
    elif action == "list_tasks":
        return _list_tasks(params.get("status", "all"))
    elif action == "complete_task":
        return _complete_task(params.get("task_id"))
    elif action == "suggest_next":
        return _suggest_next()
    elif action == "get_progress":
        return _get_progress()
    return ""

def run_agent(user_message: str, chat_history: list) -> str:
    """Run agent using JSON action parsing — avoids Groq tool_call compatibility issues."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key.strip() == "" or "your_groq_api_key_here" in api_key:
        return None

    llm = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=api_key, temperature=0.5)

    # Clean history — only plain text exchanges
    clean_history = []
    for msg in chat_history:
        if isinstance(msg, HumanMessage):
            clean_history.append(msg)
        elif isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
            clean_history.append(AIMessage(content=msg.content))

    messages = [SystemMessage(content=SYSTEM_PROMPT)] + clean_history[-10:] + [HumanMessage(content=user_message)]

    for round_num in range(3):
        response = llm.invoke(messages)
        raw = response.content

        actions = _parse_actions(raw)

        if not actions:
            # No JSON found — plain text response, return as-is
            return raw.strip()

        # Execute non-reply actions first, collect results
        tool_results = []
        final_reply = None

        for item in actions:
            action = item.get("action", "")
            params = item.get("params", {})

            if action == "reply":
                final_reply = params.get("text", "").strip()
            else:
                result = _execute_action(action, params)
                tool_results.append(f"[{action}]: {result}")

        # If we have a reply, return it (with tool context prepended if useful)
        if final_reply:
            return final_reply

        # No reply yet but we ran tools — ask model to now give the reply
        if tool_results and round_num < 2:
            context = "\n".join(tool_results)
            messages.append(AIMessage(content=raw))
            messages.append(HumanMessage(content=
                f"Tool results:\n{context}\n\n"
                f"Now reply to the user in a friendly Hinglish way. "
                f"Output ONLY a reply action JSON:\n"
                f'```json\n{{"action": "reply", "params": {{"text": "your message here"}}}}\n```'
            ))
            continue

        # Fallback — just return tool results as text
        if tool_results:
            return "\n".join(tool_results)

        return raw.strip()

    return "Kuch issue aaya. Please dobara try karo."


def _parse_actions(text: str) -> list:
    """Extract JSON action(s) from model output."""
    # Try to find JSON array or object in code blocks
    patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'(\[[\s\S]*?\])',
        r'(\{[\s\S]*?\})',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                parsed = json.loads(match.strip())
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict) and "action" in parsed:
                    return [parsed]
            except Exception:
                continue
    return []


# Keep for backward compatibility
def get_agent_executor():
    return None
