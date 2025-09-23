# Welcome to the Bookstore Analysis Project

Hi there! 👋  
This is my personal project where I’m building a full-stack **Flask web app** with a **PostgreSQL database** to manage a bookstore.  
It’s both a learning experience and a practical system to handle books, authors, categories, and more.

---

## Features
- User registration, login, and role-based access (admin vs. user)
- Admin dashboard to manage authors, categories, and books
- File uploads for book covers and digital files
- Wishlist functionality for users
- Contact form with message storage in the database

## Tech Stack
- **Backend:** Python (Flask), psycopg2, Flask-WTF
- **Database:** PostgreSQL (local + Neon cloud)
- **Frontend:** HTML, Bootstrap 5
- **Deployment:** Render (app) + Neon (database)

## Getting Started (Local)
1. Clone the repository:
   ```bash
   git clone https://github.com/<your-username>/bookstore.git
   cd bookstore
2. Install dependencies:
   pip install -r requirements.txt
3. Run the app:
   flask run
   Visit http://127.0.0.1:5000 in your browser.