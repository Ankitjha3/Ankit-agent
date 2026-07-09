# 🤖 Ankit Agent — AI Productivity Manager

A full-stack AI-powered task management agent built with FastAPI, LangChain, and Groq LLM.

## ✨ Features

- **AI Chat** — Talk to your agent in Hinglish, it creates tasks automatically
- **Smart Task Planning** — Say "I need to study, gym, and finish project" → AI creates all tasks and guides you step by step
- **XP & Level System** — Earn XP for completing tasks, level up from Beginner to Legend
- **Streak Tracking** — Daily consistency tracking with streak counter
- **Habit Tracker** — Add daily/weekly habits, track individual streaks
- **Goal Breakdown** — Set a goal, AI auto-generates actionable tasks
- **Daily Briefing** — Personalized morning briefing every day
- **Photo Input** — Send a photo of your to-do list, AI reads and creates tasks
- **Progress Dashboard** — 7-day activity chart, priority breakdown, completion stats

## 🛠️ Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy, SQLite
- **AI:** Groq (llama-3.3-70b-versatile), LangChain
- **Frontend:** Vanilla JS, HTML/CSS (no frameworks)
- **Deployment:** Railway

## 🚀 Run Locally

```bash
git clone https://github.com/Ankitjha3/Ankit-agent.git
cd Ankit-agent
pip install -r requirements.txt
cp .env.example .env
# Add your GROQ_API_KEY to .env (free at console.groq.com)
python3 run.py
```

Open `http://localhost:8000`

## 🔑 Environment Variables

```
GROQ_API_KEY=your_groq_api_key_here  # Free at console.groq.com
```

## 📸 Live Demo

[web-production-04d2f.up.railway.app](https://web-production-04d2f.up.railway.app)
