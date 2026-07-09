// ── STATE ──
let allTasks = [];
let progressData = {};
let currentFilter = "all";
let isChatLoading = false;
let addFormCollapsed = false;

// ── INIT ──
document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("task-form").addEventListener("submit", handleAddTask);
    document.getElementById("chat-form").addEventListener("submit", handleSendMessage);
    document.getElementById("goal-form").addEventListener("submit", handleAddGoal);
    document.getElementById("habit-form").addEventListener("submit", handleAddHabit);

    const today = new Date().toISOString().split("T")[0];
    const due = document.getElementById("task-due");
    if (due) due.min = today;

    checkApiStatus();
    refreshDashboard();
    fetchBriefing();
    loadChatHistory();
});

// ── SIDEBAR ──
function openSidebar() {
    document.getElementById("sidebar").classList.add("open");
    document.getElementById("sidebar-overlay").classList.add("open");
}
function closeSidebar() {
    document.getElementById("sidebar").classList.remove("open");
    document.getElementById("sidebar-overlay").classList.remove("open");
}

// ── NAVIGATION ──
function showView(name) {
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    document.querySelectorAll(".mobile-nav-item").forEach(n => n.classList.remove("active"));

    document.getElementById("view-" + name).classList.add("active");
    ["nav-" + name, "mnav-" + name].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add("active");
    });

    const titles = { tasks: "My Tasks", goals: "Goals", habits: "Habits", progress: "Progress", chat: "AI Chat", calendar: "Calendar" };
    document.getElementById("topbar-title").textContent = titles[name] || name;

    if (name === "progress") renderProgress();
    if (name === "goals") fetchGoals();
    if (name === "habits") fetchHabits();
    if (name === "calendar") { renderCalendar(); }
    closeSidebar();
}

function toggleAddForm() {
    addFormCollapsed = !addFormCollapsed;
    document.getElementById("add-task-form-body").style.display = addFormCollapsed ? "none" : "";
    document.getElementById("collapse-btn").classList.toggle("collapsed", addFormCollapsed);
}

// ── API STATUS ──
async function checkApiStatus() {
    try {
        const res = await fetch("/api/tasks");
        if (!res.ok) throw new Error();
        setOnline(true);
        const r = await fetch("/api/chat", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: "__ping__" })
        });
        const d = await r.json();
        if (d.missing_api_key) showKeyWarning();
    } catch { setOnline(false); }
}

function setOnline(online) {
    const dot = document.getElementById("status-dot");
    const txt = document.getElementById("api-status-text");
    const agentDot = document.getElementById("agent-dot");
    if (dot) dot.className = "dot " + (online ? "online" : "offline");
    if (txt) txt.textContent = online ? "Agent Online" : "Server Offline";
    if (agentDot) agentDot.style.background = online ? "var(--low)" : "var(--text3)";
}

// ── TASKS ──
async function fetchTasks() {
    try {
        const res = await fetch("/api/tasks");
        if (!res.ok) throw new Error("Server error " + res.status);
        allTasks = await res.json();
        renderTasks();
        updateMiniStats();
    } catch (e) {
        console.error("fetchTasks:", e);
        const container = document.getElementById("tasks-list");
        if (container) container.innerHTML = `<div class="empty-state"><i class="fa-solid fa-triangle-exclamation"></i><p>Failed to load tasks. Try refreshing.</p></div>`;
    }
}

function updateMiniStats() {
    const pending = allTasks.filter(t => !t.completed).length;
    const done = allTasks.filter(t => t.completed).length;
    const high = allTasks.filter(t => !t.completed && t.priority === "high").length;
    const total = allTasks.length;
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    setEl("stat-pending", pending); setEl("stat-done", done);
    setEl("stat-high", high); setEl("stat-pct", pct + "%");
}

function setFilter(filter, el) {
    currentFilter = filter;
    document.querySelectorAll(".filter-chip").forEach(c => c.classList.remove("active"));
    el.classList.add("active");
    renderTasks();
}

function renderTasks() {
    const container = document.getElementById("tasks-list");
    const search = (document.getElementById("search-input").value || "").toLowerCase().trim();
    let tasks = [...allTasks];
    if (currentFilter === "pending") tasks = tasks.filter(t => !t.completed);
    else if (currentFilter === "completed") tasks = tasks.filter(t => t.completed);
    if (search) tasks = tasks.filter(t =>
        t.title.toLowerCase().includes(search) ||
        (t.description && t.description.toLowerCase().includes(search))
    );
    if (!tasks.length) {
        container.innerHTML = `<div class="empty-state"><i class="fa-solid fa-inbox"></i>
            <p>${search ? "No tasks match your search." : currentFilter === "completed" ? "No completed tasks yet." : "No pending tasks. Add one above!"}</p></div>`;
        return;
    }
    container.innerHTML = "";
    tasks.forEach(task => {
        const card = document.createElement("div");
        card.className = `task-card priority-${task.priority}-border${task.completed ? " completed-task" : ""}`;
        let dueHTML = "";
        if (task.due_date) {
            const due = new Date(task.due_date + "T00:00:00");
            const now = new Date(); now.setHours(0, 0, 0, 0);
            const overdue = !task.completed && due < now;
            dueHTML = `<span class="task-due-badge${overdue ? " overdue" : ""}">
                <i class="fa-regular fa-calendar"></i>
                ${due.toLocaleDateString(undefined, { month: "short", day: "numeric" })}${overdue ? " · Overdue" : ""}
            </span>`;
        }
        const habitBadge = task.is_habit ? `<span class="badge" style="background:rgba(167,139,250,.15);color:var(--xp)">🔁 Habit</span>` : "";
        card.innerHTML = `
            <label class="task-checkbox-wrapper">
                <input type="checkbox" ${task.completed ? "checked disabled" : ""} onclick="handleCompleteTask(${task.id})">
                <span class="checkmark"></span>
            </label>
            <div class="task-info">
                <div class="task-card-title">${escapeHTML(task.title)}</div>
                ${task.description ? `<div class="task-card-desc">${escapeHTML(task.description)}</div>` : ""}
                <div class="task-meta">
                    <span class="badge badge-${task.priority}">${task.priority}</span>
                    ${habitBadge}
                    ${dueHTML}
                </div>
            </div>
            <button class="task-delete-btn" onclick="handleDeleteTask(${task.id})" title="Delete">
                <i class="fa-regular fa-trash-can"></i>
            </button>`;
        container.appendChild(card);
    });
}

// ── TASK ACTIONS ──
async function handleAddTask(e) {
    e.preventDefault();
    const titleEl = document.getElementById("task-title");
    const descEl = document.getElementById("task-desc");
    const dueEl = document.getElementById("task-due");
    const priorityEl = document.querySelector('#task-form input[name="priority"]:checked');
    const btn = document.getElementById("add-task-btn");
    const title = titleEl.value.trim();
    if (!title) { showToast("Please enter a task title"); return; }
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Adding...';
    try {
        const res = await fetch("/api/tasks", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                title, description: descEl.value.trim() || null,
                priority: priorityEl ? priorityEl.value : "medium",
                due_date: dueEl.value || null
            })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Error " + res.status);
        titleEl.value = ""; descEl.value = ""; dueEl.value = "";
        document.getElementById("p-medium").checked = true;
        await refreshDashboard();
        showToast("Task added ✓");
    } catch (err) {
        showToast("Failed: " + (err.message || "Unknown error"));
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-plus"></i> Add Task';
    }
}

async function handleCompleteTask(id) {
    try {
        const res = await fetch(`/api/tasks/${id}/complete`, { method: "POST" });
        if (!res.ok) throw new Error();
        const data = await res.json();
        triggerConfetti();
        showXpToast(data.xp_earned);
        appendMessage("agent", data.appreciation);
        await refreshDashboard();
    } catch { showToast("Failed to complete task"); }
}

async function handleDeleteTask(id) {
    if (!confirm("Delete this task?")) return;
    try {
        const res = await fetch(`/api/tasks/${id}`, { method: "DELETE" });
        if (!res.ok) throw new Error();
        await refreshDashboard();
        showToast("Task deleted");
    } catch { showToast("Failed to delete task"); }
}

// ── SUGGESTION ──
async function fetchSuggestion() {
    try {
        const res = await fetch("/api/suggest");
        if (!res.ok) throw new Error();
        const data = await res.json();
        document.getElementById("next-task-suggestion").innerHTML = parseMarkdown(data.suggestion);
        const c = document.getElementById("suggestion-action-container");
        c.innerHTML = "";
        if (data.task_id) {
            const btn = document.createElement("button");
            btn.className = "suggestion-action-btn";
            btn.innerHTML = `<i class="fa-solid fa-check"></i> Mark done`;
            btn.onclick = () => handleCompleteTask(data.task_id);
            c.appendChild(btn);
        }
    } catch { /* silent */ }
}

// ── DAILY BRIEFING ──
async function fetchBriefing() {
    try {
        const res = await fetch("/api/briefing");
        if (!res.ok) return;
        const data = await res.json();
        if (data.briefing && data.fresh) {
            document.getElementById("briefing-text").innerHTML = parseMarkdown(data.briefing);
            document.getElementById("briefing-card").classList.remove("hidden");
        }
    } catch { /* silent */ }
}

// ── GOALS ──
async function fetchGoals() {
    try {
        const res = await fetch("/api/goals");
        if (!res.ok) throw new Error("Server error " + res.status);
        renderGoals(await res.json());
    } catch (e) {
        console.error("fetchGoals:", e);
        document.getElementById("goals-list").innerHTML = `<div class="empty-state"><i class="fa-solid fa-bullseye"></i><p>Failed to load goals. Try refreshing.</p></div>`;
    }
}

function renderGoals(goals) {
    const container = document.getElementById("goals-list");
    if (!goals.length) {
        container.innerHTML = `<div class="empty-state"><i class="fa-solid fa-bullseye"></i><p>No goals yet. Set one above — AI will break it into tasks!</p></div>`;
        return;
    }
    container.innerHTML = goals.map(g => `
        <div class="goal-card">
            <div class="goal-card-header">
                <div>
                    <div class="goal-card-title">${escapeHTML(g.title)}</div>
                    ${g.description ? `<div class="task-card-desc" style="margin-top:.2rem">${escapeHTML(g.description)}</div>` : ""}
                </div>
                <button class="task-delete-btn" style="opacity:1" onclick="handleDeleteGoal(${g.id})" title="Delete goal">
                    <i class="fa-regular fa-trash-can"></i>
                </button>
            </div>
            <div class="goal-card-meta">
                <span class="goal-badge ${g.timeframe}">${g.timeframe}</span>
                ${g.deadline ? `<span class="task-due-badge"><i class="fa-regular fa-calendar"></i> ${g.deadline}</span>` : ""}
                <span class="goal-tasks-txt">${g.tasks_done}/${g.task_count} tasks done</span>
            </div>
            <div class="goal-progress-row">
                <div class="goal-pbar-track"><div class="goal-pbar-fill" style="width:${g.progress_pct}%"></div></div>
                <span class="goal-pct">${g.progress_pct}%</span>
            </div>
        </div>`).join("");
}

async function handleAddGoal(e) {
    e.preventDefault();
    const title = document.getElementById("goal-title").value.trim();
    const desc = document.getElementById("goal-desc").value.trim();
    const timeframe = document.getElementById("goal-timeframe").value;
    const deadline = document.getElementById("goal-deadline").value;
    if (!title) return;
    const btn = document.getElementById("add-goal-btn");
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> AI is creating tasks...';
    try {
        const res = await fetch("/api/goals", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, description: desc || null, timeframe, deadline: deadline || null })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Error");
        document.getElementById("goal-title").value = "";
        document.getElementById("goal-desc").value = "";
        document.getElementById("goal-deadline").value = "";
        showToast(data.message || "Goal created!");
        await fetchGoals();
        await refreshDashboard();
    } catch (err) {
        showToast("Failed: " + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Create Goal + Auto-generate Tasks';
    }
}

async function handleDeleteGoal(id) {
    if (!confirm("Delete this goal?")) return;
    try {
        await fetch(`/api/goals/${id}`, { method: "DELETE" });
        fetchGoals();
        showToast("Goal deleted");
    } catch { showToast("Failed to delete goal"); }
}

// ── HABITS ──
async function fetchHabits() {
    try {
        const res = await fetch("/api/habits");
        if (!res.ok) throw new Error("Server error " + res.status);
        renderHabits(await res.json());
    } catch (e) {
        console.error("fetchHabits:", e);
        document.getElementById("habits-list").innerHTML = `<div class="empty-state"><i class="fa-solid fa-fire"></i><p>Failed to load habits. Try refreshing.</p></div>`;
    }
}

function renderHabits(habits) {
    const container = document.getElementById("habits-list");
    if (!habits.length) {
        container.innerHTML = `<div class="empty-state"><i class="fa-solid fa-fire"></i><p>No habits yet. Add daily habits to track your consistency!</p></div>`;
        return;
    }
    const today = new Date().toISOString().split("T")[0];
    container.innerHTML = habits.map(h => {
        const checkedToday = h.last_checked === today;
        return `<div class="habit-card">
            <div class="habit-streak-badge ${h.current_streak > 0 ? 'active' : ''}">
                <span class="habit-streak-num">${h.current_streak}</span>
                <span class="habit-streak-icon">🔥</span>
            </div>
            <div class="habit-info">
                <div class="habit-title">${escapeHTML(h.title)}</div>
                <div class="habit-meta">${h.frequency} · Best: ${h.longest_streak} days${h.description ? " · " + escapeHTML(h.description) : ""}</div>
            </div>
            <button class="habit-check-btn ${checkedToday ? 'checked-today' : ''}" 
                onclick="${checkedToday ? '' : `handleCheckHabit(${h.id})`}"
                ${checkedToday ? 'disabled' : ''}>
                <i class="fa-solid ${checkedToday ? 'fa-check' : 'fa-circle-check'}"></i>
                ${checkedToday ? 'Done!' : 'Check In'}
            </button>
            <button class="habit-delete-btn" onclick="handleDeleteHabit(${h.id})"><i class="fa-regular fa-trash-can"></i></button>
        </div>`;
    }).join("");
}

async function handleAddHabit(e) {
    e.preventDefault();
    const title = document.getElementById("habit-title").value.trim();
    const desc = document.getElementById("habit-desc").value.trim();
    const freq = document.querySelector('input[name="habit-freq"]:checked').value;
    if (!title) return;
    const btn = document.getElementById("add-habit-btn");
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Adding...';
    try {
        const res = await fetch("/api/habits", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, description: desc || null, frequency: freq })
        });
        if (!res.ok) throw new Error("Error");
        document.getElementById("habit-title").value = "";
        document.getElementById("habit-desc").value = "";
        showToast("Habit added ✓");
        fetchHabits();
    } catch { showToast("Failed to add habit"); }
    finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-plus"></i> Add Habit';
    }
}

async function handleCheckHabit(id) {
    try {
        const res = await fetch(`/api/habits/${id}/check`, { method: "POST" });
        if (!res.ok) throw new Error();
        const data = await res.json();
        showXpToast(data.xp_earned);
        showToast(data.message);
        if (data.habit.current_streak > 1) triggerConfetti();
        fetchHabits();
        fetchProgress();
    } catch { showToast("Failed to check habit"); }
}

async function handleDeleteHabit(id) {
    if (!confirm("Delete this habit?")) return;
    try {
        await fetch(`/api/habits/${id}`, { method: "DELETE" });
        fetchHabits();
        showToast("Habit deleted");
    } catch { showToast("Failed to delete habit"); }
}

// ── PROGRESS ──
async function fetchProgress() {
    try {
        const res = await fetch("/api/progress");
        if (!res.ok) throw new Error();
        progressData = await res.json();
        updateSidebarLevel(progressData);
    } catch (e) { console.error("fetchProgress:", e); }
}

function updateSidebarLevel(d) {
    if (!d) return;
    setEl("sb-level-badge", "Lv." + d.level);
    setEl("sb-level-title", d.emoji + " " + d.title);
    setStyle("sb-level-bar", "width", d.progress_pct + "%");
    setEl("sb-level-xp", d.total_xp + " XP");
}

function renderProgress() {
    if (!progressData || !progressData.level) return;
    const d = progressData;
    setEl("p-level-num", d.level);
    setEl("p-level-title", d.emoji + " " + d.title);
    setEl("p-xp-info", `${d.total_xp} XP · ${d.xp_to_next} XP to ${d.next_level_title}`);
    setStyle("p-level-fill", "width", d.progress_pct + "%");
    setEl("p-streak", d.current_streak);
    setEl("p-longest", d.longest_streak);
    setEl("p-xp", d.total_xp);
    setEl("p-rate", d.completion_rate + "%");
    const todayEl = document.getElementById("today-status");
    const todayTxt = document.getElementById("today-status-text");
    if (d.active_today) {
        todayEl.className = "today-status active-day";
        todayTxt.textContent = "Active today! Keep the streak going 🔥";
    } else {
        todayEl.className = "today-status inactive-day";
        todayTxt.textContent = "No activity today yet — complete a task to keep your streak!";
    }
    setStyle("progress-fill", "width", d.completion_rate + "%");
    setEl("progress-pct", d.completion_rate + "%");
    setEl("progress-label", d.total_tasks === 0 ? "No active tasks. Add tasks to track completion!" :
        d.completion_rate === 100 ? "🎉 All done! You're on fire!" : `${d.completed} of ${d.total_tasks} tasks completed`);
    renderActivityChart(d.daily_activity || []);
    const total = d.total_tasks || 1;
    const high = allTasks.filter(t => t.priority === "high").length;
    const medium = allTasks.filter(t => t.priority === "medium").length;
    const low = allTasks.filter(t => t.priority === "low").length;
    setStyle("pb-high", "width", (high / total * 100) + "%"); setEl("pb-high-n", high);
    setStyle("pb-medium", "width", (medium / total * 100) + "%"); setEl("pb-medium-n", medium);
    setStyle("pb-low", "width", (low / total * 100) + "%"); setEl("pb-low-n", low);
}

function renderActivityChart(days) {
    const chart = document.getElementById("activity-chart");
    if (!chart) return;
    const maxTasks = Math.max(...days.map(d => d.tasks_completed), 1);
    const today = new Date().toISOString().split("T")[0];
    const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    chart.innerHTML = days.map(day => {
        const dt = new Date(day.date + "T00:00:00");
        const label = day.date === today ? "Today" : dayNames[dt.getDay()];
        const heightPct = Math.max(8, Math.round((day.tasks_completed / maxTasks) * 100));
        const cls = day.date === today ? "today" : day.tasks_completed > 0 ? "has-tasks" : "";
        return `<div class="activity-bar-wrap">
            <span class="activity-count-lbl">${day.tasks_completed > 0 ? day.tasks_completed : ""}</span>
            <div class="activity-bar ${cls}" style="height:${heightPct}%"></div>
            <span class="activity-day-lbl">${label}</span>
        </div>`;
    }).join("");
}

function setEl(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function setStyle(id, prop, val) { const el = document.getElementById(id); if (el) el.style[prop] = val; }

// ── IMAGE UPLOAD ──
async function handleImageUpload(input) {
    const file = input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (e) => {
        const container = document.getElementById("chat-messages-container");
        const previewDiv = document.createElement("div");
        previewDiv.className = "msg user-msg";
        previewDiv.innerHTML = `<div class="msg-bubble"><img src="${e.target.result}" class="msg-image" alt="Uploaded"><div>📸 Photo sent — extracting tasks...</div></div>
            <span class="msg-time">${new Date().toLocaleTimeString(undefined, {hour:"2-digit",minute:"2-digit"})}</span>`;
        container.appendChild(previewDiv);
        container.scrollTop = container.scrollHeight;
        const typingId = showTyping();
        document.getElementById("send-btn").disabled = true;
        try {
            const formData = new FormData();
            formData.append("image", file);
            const caption = document.getElementById("chat-input").value.trim();
            if (caption) formData.append("message", caption);
            document.getElementById("chat-input").value = "";
            const res = await fetch("/api/chat/image", { method: "POST", body: formData });
            removeTyping(typingId);
            const data = await res.json();
            if (data.missing_api_key) showKeyWarning();
            if (data.response) appendMessage("agent", data.response);
            setTimeout(refreshDashboard, 700);
        } catch {
            removeTyping(typingId);
            appendMessage("agent", "Image processing mein error. Please try again.");
        } finally {
            document.getElementById("send-btn").disabled = false;
            input.value = "";
        }
    };
    reader.readAsDataURL(file);
}

// ── CHAT ──
async function handleSendMessage(e) {
    e.preventDefault();
    if (isChatLoading) return;
    const input = document.getElementById("chat-input");
    const msg = input.value.trim();
    if (!msg) return;
    input.value = "";
    appendMessage("user", msg);
    const typingId = showTyping();
    isChatLoading = true;
    document.getElementById("send-btn").disabled = true;
    try {
        const res = await fetch("/api/chat", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: msg })
        });
        removeTyping(typingId);
        const data = await res.json();
        if (data.missing_api_key) showKeyWarning();
        if (data.response) appendMessage("agent", data.response);
        setTimeout(refreshDashboard, 700);
    } catch {
        removeTyping(typingId);
        appendMessage("agent", "Connection issue. Check the server is running.");
    } finally {
        isChatLoading = false;
        document.getElementById("send-btn").disabled = false;
    }
}

function sendQuickPrompt(text) {
    document.getElementById("chat-input").value = text;
    document.getElementById("chat-form").dispatchEvent(new Event("submit", { cancelable: true }));
}

function appendMessage(sender, text) {
    if (!text || text === "__ping__") return;
    const container = document.getElementById("chat-messages-container");
    const div = document.createElement("div");
    div.className = `msg ${sender}-msg`;
    const time = new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    div.innerHTML = `<div class="msg-bubble">${parseMarkdown(text)}</div><span class="msg-time">${time}</span>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    saveMessage(sender, text);
}

function showTyping() {
    const container = document.getElementById("chat-messages-container");
    const div = document.createElement("div");
    const id = "typing-" + Date.now();
    div.id = id; div.className = "msg agent-msg";
    div.innerHTML = `<div class="msg-bubble"><div class="typing-indicator">
        <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
    </div></div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return id;
}

function removeTyping(id) { const el = document.getElementById(id); if (el) el.remove(); }

// ── CHAT HISTORY (localStorage for display) ──
function saveMessage(sender, text) {
    if (!text || text === "__ping__") return;
    let h = JSON.parse(localStorage.getItem("ankit_chat") || "[]");
    h.push({ sender, text, time: new Date().toISOString() });
    if (h.length > 60) h = h.slice(-60);
    localStorage.setItem("ankit_chat", JSON.stringify(h));
}

function loadChatHistory() {
    const h = JSON.parse(localStorage.getItem("ankit_chat") || "[]");
    if (!h.length) return;
    const container = document.getElementById("chat-messages-container");
    container.innerHTML = "";
    h.forEach(({ sender, text, time }) => {
        const div = document.createElement("div");
        div.className = `msg ${sender}-msg`;
        const t = new Date(time).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
        div.innerHTML = `<div class="msg-bubble">${parseMarkdown(text)}</div><span class="msg-time">${t}</span>`;
        container.appendChild(div);
    });
    container.scrollTop = container.scrollHeight;
}

function clearLocalChat() {
    if (!confirm("Clear chat history?")) return;
    localStorage.removeItem("ankit_chat");
    document.getElementById("chat-messages-container").innerHTML = `
        <div class="msg agent-msg">
            <div class="msg-bubble">Chat cleared! Hey Ankit 👋 Kya karna hai aaj?</div>
            <span class="msg-time">Just now</span>
        </div>`;
}

// ── MODAL ──
function showKeyWarning() { document.getElementById("key-warning-modal").classList.remove("hidden"); }
function closeKeyWarning() { document.getElementById("key-warning-modal").classList.add("hidden"); }

// ── TOASTS ──
function showToast(msg) {
    const el = document.getElementById("toast");
    el.textContent = msg; el.classList.remove("hidden");
    clearTimeout(window._tt);
    window._tt = setTimeout(() => el.classList.add("hidden"), 2500);
}

function showXpToast(xp) {
    if (!xp) return;
    const el = document.getElementById("xp-toast");
    el.textContent = `+${xp} XP ⚡`; el.classList.remove("hidden");
    clearTimeout(window._xt);
    window._xt = setTimeout(() => el.classList.add("hidden"), 2500);
}

// ── CONFETTI ──
function triggerConfetti() {
    confetti({ particleCount: 60, angle: 60, spread: 55, origin: { x: 0 }, colors: ["#fff", "#a78bfa", "#aaa"] });
    confetti({ particleCount: 60, angle: 120, spread: 55, origin: { x: 1 }, colors: ["#fff", "#a78bfa", "#aaa"] });
}

// ── UTILS ──
function parseMarkdown(text) {
    if (!text) return "";
    let h = escapeHTML(String(text));
    h = h.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    h = h.replace(/\n/g, "<br>");
    return h;
}

function escapeHTML(str) {
    return String(str)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

// ── CALENDAR ──
let calYear = new Date().getFullYear();
let calMonth = new Date().getMonth(); // 0-indexed
let calSelectedDate = null;

const MONTH_NAMES = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const DAY_NAMES = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

function renderCalendar() {
    const title = document.getElementById("cal-month-title");
    if (title) title.textContent = `${MONTH_NAMES[calMonth]} ${calYear}`;

    const grid = document.getElementById("cal-grid");
    if (!grid) return;

    const today = new Date();
    const firstDay = new Date(calYear, calMonth, 1).getDay();
    const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
    const daysInPrev = new Date(calYear, calMonth, 0).getDate();

    // Map tasks by due date
    const tasksByDate = {};
    allTasks.forEach(t => {
        if (t.due_date) {
            if (!tasksByDate[t.due_date]) tasksByDate[t.due_date] = [];
            tasksByDate[t.due_date].push(t);
        }
    });

    // Build day names header
    const dayNamesHTML = DAY_NAMES.map(d => `<div class="cal-day-name">${d}</div>`).join("");

    // Build calendar weeks
    let weeksHTML = '<div class="cal-week">';
    let dayCount = 0;

    // Previous month padding
    for (let i = firstDay - 1; i >= 0; i--) {
        const d = daysInPrev - i;
        weeksHTML += `<div class="cal-day empty other-month"><div class="cal-day-num">${d}</div></div>`;
        dayCount++;
    }

    // Current month days
    for (let d = 1; d <= daysInMonth; d++) {
        const dateStr = `${calYear}-${String(calMonth + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
        const isToday = d === today.getDate() && calMonth === today.getMonth() && calYear === today.getFullYear();
        const isSelected = dateStr === calSelectedDate;
        const dayTasks = tasksByDate[dateStr] || [];
        const hasTasks = dayTasks.length > 0;

        const pillsHTML = dayTasks.slice(0, 3).map(t =>
            `<div class="cal-task-pill ${t.completed ? "done" : t.priority}">${escapeHTML(t.title)}</div>`
        ).join("");
        const moreHTML = dayTasks.length > 3 ? `<div class="cal-more-badge">+${dayTasks.length - 3} more</div>` : "";

        weeksHTML += `<div class="cal-day${isToday ? " today" : ""}${isSelected ? " selected" : ""}${hasTasks ? " has-tasks" : ""}" 
            onclick="calSelectDay('${dateStr}', ${d})">
            <div class="cal-day-num">${d}</div>
            <div class="cal-task-dots">${pillsHTML}${moreHTML}</div>
        </div>`;

        dayCount++;
        if (dayCount % 7 === 0 && d < daysInMonth) {
            weeksHTML += '</div><div class="cal-week">';
        }
    }

    // Next month padding
    const remaining = 7 - (dayCount % 7);
    if (remaining < 7) {
        for (let d = 1; d <= remaining; d++) {
            weeksHTML += `<div class="cal-day empty other-month"><div class="cal-day-num">${d}</div></div>`;
        }
    }
    weeksHTML += "</div>";

    grid.innerHTML = `
        <div class="cal-day-names">${dayNamesHTML}</div>
        <div class="cal-weeks">${weeksHTML}</div>`;
}

function calSelectDay(dateStr, dayNum) {
    calSelectedDate = dateStr;
    renderCalendar(); // re-render to show selected

    const panel = document.getElementById("cal-day-panel");
    const titleEl = document.getElementById("cal-selected-date-title");
    const tasksEl = document.getElementById("cal-day-tasks");

    const dateObj = new Date(dateStr + "T00:00:00");
    const label = dateObj.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
    if (titleEl) titleEl.textContent = label;

    const dayTasks = allTasks.filter(t => t.due_date === dateStr);

    if (tasksEl) {
        if (!dayTasks.length) {
            tasksEl.innerHTML = `<p style="font-size:.82rem;color:var(--text2);margin-bottom:.5rem">No tasks scheduled for this day.</p>`;
        } else {
            tasksEl.innerHTML = dayTasks.map(t => `
                <div class="cal-day-task-item ${t.priority}${t.completed ? " done" : ""}">
                    <label class="task-checkbox-wrapper" style="width:18px;height:18px;flex-shrink:0">
                        <input type="checkbox" ${t.completed ? "checked disabled" : ""} onclick="handleCompleteTask(${t.id})">
                        <span class="checkmark"></span>
                    </label>
                    <span class="cal-day-task-title">${escapeHTML(t.title)}</span>
                    <button class="task-delete-btn" style="opacity:1" onclick="handleDeleteTask(${t.id})">
                        <i class="fa-regular fa-trash-can"></i>
                    </button>
                </div>`).join("");
        }
    }

    // Set the quick-add form's date
    const form = document.getElementById("cal-quick-add");
    if (form) {
        form._selectedDate = dateStr;
        form._dayLabel = label;
        form._dayNum = dayNum;
    }

    panel.classList.remove("hidden");
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function calQuickAdd() {
    const form = document.getElementById("cal-quick-add");
    const dateStr = form._selectedDate;
    const label = form._dayLabel;
    const dayNum = form._dayNum;
    const title = document.getElementById("cal-quick-title").value.trim();
    const priority = document.querySelector('input[name="calpriority"]:checked').value;
    if (!title) return;
    try {
        const res = await fetch("/api/tasks", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, priority, due_date: dateStr })
        });
        if (!res.ok) throw new Error();
        document.getElementById("cal-quick-title").value = "";
        document.getElementById("cp-medium").checked = true;
        await refreshDashboard();
        renderCalendar();
        calSelectDay(dateStr, dayNum);
        showToast("Task added ✓");
    } catch { showToast("Failed to add task"); }
}

function calPrevMonth() {
    calMonth--;
    if (calMonth < 0) { calMonth = 11; calYear--; }
    calSelectedDate = null;
    document.getElementById("cal-day-panel").classList.add("hidden");
    renderCalendar();
}

function calNextMonth() {
    calMonth++;
    if (calMonth > 11) { calMonth = 0; calYear++; }
    calSelectedDate = null;
    document.getElementById("cal-day-panel").classList.add("hidden");
    renderCalendar();
}

function calGoToday() {
    calYear = new Date().getFullYear();
    calMonth = new Date().getMonth();
    calSelectedDate = null;
    document.getElementById("cal-day-panel").classList.add("hidden");
    renderCalendar();
}

// ── DASHBOARD ──
async function refreshDashboard() {
    await Promise.all([fetchTasks(), fetchSuggestion(), fetchProgress()]);
}
