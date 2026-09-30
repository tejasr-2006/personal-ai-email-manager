# 🤖 Personal AI Email Manager

An AI-powered email management system that connects to Gmail, analyzes emails using AI, and helps users identify important messages, required actions, and upcoming deadlines.

## ✨ Features

- 📧 Gmail email synchronization
- 🤖 AI-powered email classification
- 🔥 Priority detection — High / Medium / Low
- ⚡ Action-required email detection
- 📅 Deadline detection
- 🏷️ Automatic email categorization
- 🔎 Email search and filtering
- 📖 Unread/read email tracking
- 🔔 Browser notifications for important emails
- 📝 AI-generated email summaries
- 📊 Email analytics
- 🧠 AI daily briefing
- 🗄️ MongoDB email storage

## 🛠️ Tech Stack

### Frontend
- React
- Vite
- Axios
- JavaScript
- CSS

### Backend
- Python
- FastAPI
- Gmail API
- Google OAuth 2.0

### AI
- Google Gemini API

### Database
- MongoDB Atlas

## 🏗️ Architecture

```text
                    ┌───────────────┐
                    │     Gmail     │
                    │      API      │
                    └───────┬───────┘
                            │
                            ▼
                 ┌────────────────────┐
                 │   FastAPI Backend  │
                 │                    │
                 │ Gmail Service      │
                 │ AI Service         │
                 │ MongoDB Service    │
                 └─────────┬──────────┘
                           │
                ┌──────────┴──────────┐
                ▼                     ▼
        ┌──────────────┐      ┌──────────────┐
        │ Gemini AI    │      │ MongoDB Atlas │
        │ Classification│      │   Database   │
        └──────────────┘      └──────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │  React Frontend │
                  │    Dashboard    │
                  └─────────────────┘