# 🍳 Smart Pantry & Kitchen Manager

A smart, AI-powered kitchen management system designed to track inventory, minimize food waste, and automate meal planning for Indian households. Built with **Streamlit** and powered by **Groq (Llama 3)**.

## 🌟 Features

### 🧠 AI Intelligence
* **Morning Rush Planner:** Generates breakfast and lunchbox plans based on family schedules (who leaves first) and available inventory.
* **Bill Scanner:** Upload receipts to automatically extract items, prices, and quantities using Llama Vision.
* **Leftover Wizard:** Suggests recipes to reuse leftover food.
* **Smart Auto-Fill:** Predicts category and shelf life for new ingredients automatically.

### 🏡 Family Management
* **Family Setup:** Define members, roles (e.g., Father, Son), and health conditions (Diabetes, etc.).
* **Schedule Tracking:** Tracks wake-up and leave times to prioritize cooking order.

### 📦 Inventory Control
* **Real-time Dashboard:** Tracks stock levels, expiry dates, and total inventory value.
* **Critical Alerts:** Highlights items expiring within 3 days or running low.
* **Logs & History:** Tracks price fluctuations and consumption history over time.
* **Analytics:** Forecasts future demand using predictive models.

## 🛠️ Tech Stack
* **Frontend:** Streamlit (Python)
* **Backend Logic:** Python (Pandas, Plotly)
* **Database:** MySQL (Hosted on Filess.io or Local)
* **AI/LLM:** Groq API (Llama-3.3-70b-versatile & Llama-Vision)
* **Visualization:** Plotly Express

## 🚀 Setup & Installation

### 1. Clone the Repository
```bash
git clone [https://github.com/your-username/smart-pantry-app.git](https://github.com/your-username/smart-pantry-app.git)
cd smart-pantry-app