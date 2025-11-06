<h1 align="center">🧠 Smart Planner</h1>
<p align="center">
A personal productivity and study planner built with <b>Django</b> to help you stay organized, consistent, and focused.  
</p>

---

## 🗂️ Overview

| Feature | Description |
|----------|--------------|
| ✅ **Smart Planning** | Create subject or topic-wise study/work plans. |
| 🧩 **AI Task Generator** | Auto-generate learning steps using your topic input (via Groq API). |
| 🕒 **Pomodoro Timer** | Stay productive with focus timers and snooze controls. |
| 📈 **XP Progress System** | Level up as you complete tasks — track consistency visually. |
| 👥 **Team Collaboration** | Build and manage teams, share goals, and plan together. |
| 📜 **Task History** | Review your completed plans and daily achievements. |

---

## 🧰 Tech Stack

| Layer | Technology Used |
|--------|----------------|
| **Backend** | Django 5.x |
| **Frontend** | Bootstrap 5 + Custom CSS |
| **Database** | SQLite3 (default) |
| **AI Integration** | Groq API (through `.env`) |
| **Version Control** | Git & GitHub |

---

## ⚙️ Installation Guide

| Step | Command / Action | Description |
|------|------------------|-------------|
| **1️⃣ Clone Repository** | ```bash<br>git clone https://github.com/sachink8n/Smart-Planner.git<br>cd Smart-Planner``` | Clone project locally |
| **2️⃣ Create Virtual Environment** | ```bash<br>python -m venv my_env<br>source my_env/bin/activate``` | Use venv for isolation |
| **3️⃣ Install Dependencies** | ```bash<br>pip install -r requirements.txt``` | Installs Django and libraries |
| **4️⃣ Configure `.env` File** | ```bash<br>DJANGO_SECRET_KEY=your_secret_key<br>DJANGO_DEBUG=True<br>AI_API_KEY=your_groq_api_key``` | Keeps sensitive keys safe |
| **5️⃣ Run Server** | ```bash<br>python manage.py runserver``` | Start Django locally |
| **6️⃣ Open in Browser** | `http://127.0.0.1:8000/` | Test the app running |

---

## 📸 Screenshots

| Dashboard View | Plans Page | Team Page |
|:---------------:|:----------:|:----------:|
| ![Dashboard](https://via.placeholder.com/250x150.png?text=Dashboard) | ![Plans](https://via.placeholder.com/250x150.png?text=Plans) | ![Teams](https://via.placeholder.com/250x150.png?text=Teams) |

*(Add real screenshots later for a more complete look.)*

---

## 🚧 Folder Structure

```bash
Smart-Planner/
├── core/
│   ├── templates/
│   ├── static/
│   ├── views.py
│   ├── models.py
│   └── urls.py
├── smart_planner/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── manage.py
├── requirements.txt
└── .env.example
