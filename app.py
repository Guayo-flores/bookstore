import os
import psycopg2
from flask import (
    Flask,
    render_template,
    request,
    url_for,
    redirect,
    session,
    flash,
    current_app,
    abort,
)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from psycopg2 import errors
from psycopg2.extras import RealDictCursor
import uuid
from pathlib import Path
from werkzeug.utils import secure_filename
import itertools
from flask_wtf import CSRFProtect
from datetime import date
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "COUGS")

is_prod = os.getenv("FLASK_ENV") == "production"
app.config.update(
    WTF_CSRF_TIME_LIMIT=None,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=is_prod,  # True in production (HTTPS)
    SESSION_COOKIE_SAMESITE="Lax",
    WTF_CSRF_ENABLED=False,
)

# Where to save files relative to your project root
BASE_DIR = Path(__file__).resolve().parent
COVERS_DIR = BASE_DIR / "static" / "uploads" / "covers"
FILES_DIR = BASE_DIR / "static" / "uploads" / "files"
COVERS_DIR.mkdir(parents=True, exist_ok=True)
FILES_DIR.mkdir(parents=True, exist_ok=True)

# Max upload size (e.g., 16 MB)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

ALLOWED_COVER_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_FILE_EXTS = {"pdf", "epub", "mobi", "txt"}

UPLOAD_DIR_COVER = os.path.join("static", "uploads", "cover")
UPLOAD_DIR_FILE = os.path.join("static", "uploads", "files")
os.makedirs(UPLOAD_DIR_COVER, exist_ok=True)
os.makedirs(UPLOAD_DIR_FILE, exist_ok=True)


def allowed(filename: str, allowed_set: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_set


def save_unique(dirpath, original):
    safe = secure_filename(original)
    stem, ext = os.path.splitext(safe)
    candidate = safe
    for i in itertools.count(1):
        path = dirpath / candidate
        if not path.exists():
            return candidate, path
        candidate = f"{stem}_{i}{ext}"


def get_db_connection():
    url = os.getenv("DATABASE_URL")
    if url:
        if "sslmode=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}sslmode=require"
        conn = psycopg2.connect(url)
    else:
        conn = psycopg2.connect(
            host="localhost", database="flask_db", user="postgres", password="Lalo"
        )
    with conn.cursor() as cur:
        cur.execute("SET search_path TO public;")
    return conn


# --- INSERT ONE ADMIN (run once, then comment it out) ---
def seed_admin(full_name, email, raw_password, conn):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM admin WHERE email=%s;", (email,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO admin (full_name, email, password_hash) VALUES (%s, %s, %s);",
            (full_name, email, generate_password_hash(raw_password)),
        )
        conn.commit()
    cur.close()


# --- Fetchers ---
def get_admin_by_email(conn, email):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, full_name, email, password_hash FROM admin WHERE email=%s;",
        (email,),
    )
    row = cur.fetchone()
    cur.close()
    return row  # (id, full_name, email, password_hash) or None


def get_user_by_email(conn, email):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, full_name, email, password_hash FROM users WHERE email=%s;",
        (email,),
    )
    row = cur.fetchone()
    cur.close()
    return row


# --- Session guards ---
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session or "role" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapper


def role_required(required_role):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("role") != required_role:
                # optionally flash a message
                return redirect(url_for("login"))
            return f(*args, **kwargs)

        return wrapper

    return deco


# try:
#     conn = get_db_connection()
#     seed_admin("Eduardo Flores", "admin@example.com", "admin", conn)
#     conn.close()
# except Exception as e:
#     print("Admin seed error:", e)


# --- Dashboards ---


# Home page (fetches books)
@app.route("/")
def index():
    conn = get_db_connection()
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        # New arrivals / main grid (newest first)
        cur.execute(
            """
            SELECT b.id, b.title,
                   a.name AS author,
                   c.name AS category,
                   b.description, b.price, b.cover, b.file, b.id AS sort_id
            FROM books b
            JOIN authors a ON a.id = b.author_id
            JOIN categories c ON c.id = b.category_id
            ORDER BY sort_id DESC
            LIMIT 24;
        """
        )
        new_books = cur.fetchall()

        # Featured (use newest 5 for now)
        cur.execute(
            """
            SELECT b.id, b.title,
                   a.name AS author,
                   c.name AS category,
                   b.description, b.price, b.cover, b.file
            FROM books b
            JOIN authors a ON a.id = b.author_id
            JOIN categories c ON c.id = b.category_id
            ORDER BY b.id DESC
            LIMIT 5;
        """
        )
        featured_books = cur.fetchall()

        # Categories for hero chips (with counts)
        cur.execute(
            """
            SELECT c.id, c.name, COUNT(b.id) AS book_count
            FROM categories c
            LEFT JOIN books b ON b.category_id = c.id
            GROUP BY c.id, c.name
            ORDER BY c.name;
        """
        )
        categories = cur.fetchall()

        # Simple counts
        cur.execute("SELECT COUNT(*) AS n FROM books;")
        books_count = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM authors;")
        authors_count = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM categories;")
        categories_count = cur.fetchone()["n"]

    conn.close()
    return render_template(
        "index.html",
        # The template looks for these:
        books=new_books,  # fallback collection
        new_books=new_books,  # "New Arrivals" grid
        featured_books=featured_books,  # carousel + editor's pick
        categories=categories,  # chips
        books_count=books_count,
        authors_count=authors_count,
        categories_count=categories_count,
        current_year=date.today().year,
    )


# Store page (separate from index if you want a dedicated list view)
@app.route("/store")
def store():
    # ---- Query params ----
    q = (request.args.get("q") or "").strip()
    sort = request.args.get("sort", "newest")
    page = request.args.get("page", "1")
    try:
        page = max(1, int(page))
    except ValueError:
        page = 1

    category_id_raw = request.args.get("category_id")
    category_id = None
    if category_id_raw and category_id_raw.isdigit():
        category_id = int(category_id_raw)

    per_page = 12

    # Safe ORDER BY map
    order_map = {
        "newest": "b.id DESC",
        "title_asc": "b.title ASC",
        "price_asc": "b.price ASC NULLS LAST",
        "price_desc": "b.price DESC NULLS LAST",
    }
    order_by = order_map.get(sort, order_map["newest"])

    conn = get_db_connection()
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ---- Build WHERE + params ----
        where = []
        params = []
        if q:
            where.append("(b.title ILIKE %s OR a.name ILIKE %s OR c.name ILIKE %s)")
            like = f"%{q}%"
            params += [like, like, like]
        if category_id:
            where.append("b.category_id = %s")
            params.append(category_id)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # ---- Count for pagination ----
        cur.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM books b
            JOIN authors a ON a.id = b.author_id
            JOIN categories c ON c.id = b.category_id
            {where_sql}
            """,
            params,
        )
        total_count = cur.fetchone()["n"]
        total_pages = max(1, (total_count + per_page - 1) // per_page)

        # Clamp page to range and recompute offset
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        # ---- Fetch books (paged) ----
        cur.execute(
            f"""
            SELECT
              b.id,
              b.title,
              a.name AS author,
              c.name AS category,
              b.description,
              b.price,
              b.cover,
              b.file
            FROM books b
            JOIN authors a ON a.id = b.author_id
            JOIN categories c ON c.id = b.category_id
            {where_sql}
            ORDER BY {order_by}
            LIMIT %s OFFSET %s;
            """,
            params + [per_page, offset],
        )
        books = cur.fetchall()

        # ---- Categories for chips (global counts) ----
        cur.execute(
            """
            SELECT c.id, c.name, COUNT(b.id) AS book_count
            FROM categories c
            LEFT JOIN books b ON b.category_id = c.id
            GROUP BY c.id, c.name
            ORDER BY c.name;
            """
        )
        categories = cur.fetchall()

    conn.close()

    return render_template(
        "store.html",
        books=books,
        categories=categories,
        total_pages=total_pages,
        books_total=total_count,
        # these are optional; template reads from request.args, but passing doesn't hurt
        page=page,
        sort=sort,
    )


def current_user_id():
    """Return the logged-in user_id from session, or None."""
    return session.get("user_id")


@app.route("/book/<int:book_id>")
def book_view(book_id):
    conn = get_db_connection()
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT b.id, b.title, b.description, b.price, b.cover, b.file,
                   b.author_id, b.category_id,
                   a.name AS author, c.name AS category
            FROM books b
            JOIN authors a ON a.id = b.author_id
            JOIN categories c ON c.id = b.category_id
            WHERE b.id = %s;
        """,
            (book_id,),
        )
        book = cur.fetchone()
        if not book:
            conn.close()
            abort(404)

        cur.execute(
            """
            SELECT b.id, b.title, b.description, b.price, b.cover, b.file,
                   a.name AS author, c.name AS category
            FROM books b
            JOIN authors a ON a.id = b.author_id
            JOIN categories c ON c.id = b.category_id
            WHERE b.category_id = %s AND b.id <> %s
            ORDER BY b.id DESC
            LIMIT 8;
        """,
            (book["category_id"], book_id),
        )
        related = cur.fetchall()
    conn.close()

    return render_template("view.html", book=book, related=related)


@app.post("/wishlist/toggle/<int:book_id>")
@login_required
def wishlist_toggle(book_id):
    uid = current_user_id()
    next_url = request.form.get("next") or request.referrer or url_for("me")

    conn = get_db_connection()
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT 1 FROM wishlists WHERE user_id=%s AND book_id=%s;", (uid, book_id)
        )
        exists = cur.fetchone()
        if exists:
            cur.execute(
                "DELETE FROM wishlists WHERE user_id=%s AND book_id=%s;", (uid, book_id)
            )
            flash("Removed from wishlist.", "info")
        else:
            cur.execute(
                """
                INSERT INTO wishlists (user_id, book_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING;
            """,
                (uid, book_id),
            )
            flash("Added to wishlist.", "success")
    conn.close()
    return redirect(next_url)


@app.route("/me")
@login_required
def me():
    uid = current_user_id()
    conn = get_db_connection()
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT b.id, b.title, a.name AS author, c.name AS category,
                   b.description, b.price, b.cover, b.file, w.created_at
            FROM wishlists w
            JOIN books b ON b.id = w.book_id
            JOIN authors a ON a.id = b.author_id
            JOIN categories c ON c.id = b.category_id
            WHERE w.user_id = %s
            ORDER BY w.created_at DESC
            LIMIT 24;
        """,
            (uid,),
        )
        wishlist = cur.fetchall()
    conn.close()
    return render_template("user.html", wishlist=wishlist)


# Login page
@app.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        # honor ?next=/path and also allow a hidden input in the form
        next_url = request.args.get("next") or request.form.get("next")

        conn = get_db_connection()
        try:
            # 1) Check admin table first
            row = get_admin_by_email(
                conn, email
            )  # expected: (id, name, email, password_hash, ...)
            if row and check_password_hash(row[3], password):
                session.clear()  # prevent session fixation
                session.permanent = True  # optional: use permanent sessions
                session["user_id"] = row[0]
                session["role"] = "admin"
                session["name"] = row[1]
                return redirect(next_url or url_for("admin"))

            # 2) Else check users table
            row = get_user_by_email(
                conn, email
            )  # expected: (id, name, email, password_hash, ...)
            if row and check_password_hash(row[3], password):
                session.clear()
                session.permanent = True
                session["user_id"] = row[0]
                session["role"] = "user"
                session["name"] = row[1]
                # 👇 send regular users to the profile page we created
                return redirect(next_url or url_for("me"))

            # Invalid credentials
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))
        finally:
            conn.close()

    # GET: render page and pass through ?next= so the form can keep it
    return render_template("login.html", next=request.args.get("next"))


# About page
@app.route("/about")
def about():
    conn = get_db_connection()
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT COUNT(*) AS n FROM books;")
        books_count = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) AS n FROM authors;")
        authors_count = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) AS n FROM categories;")
        categories_count = cur.fetchone()["n"]
    conn.close()

    return render_template(
        "about.html",
        books_count=books_count,
        authors_count=authors_count,
        categories_count=categories_count,
        current_year=date.today().year,
    )


# Contact page
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        website = request.form.get("website")  # honeypot
        if website:
            flash("Thanks!", "success")
            return redirect(url_for("contact"))

        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()
        subject = (request.form.get("subject") or "").strip()
        message = (request.form.get("message") or "").strip()
        want_copy = bool(request.form.get("copy"))
        if not (name and email and subject and message):
            flash("Please complete all fields.", "warning")
            return redirect(url_for("contact"))

        ip = request.remote_addr
        ua = request.headers.get("User-Agent", "")

        conn = get_db_connection()
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO contact_messages (name, email, subject, message, want_copy, ip, user_agent)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """,
                (name, email, subject, message, want_copy, ip, ua),
            )
            msg_id = cur.fetchone()["id"]
        conn.close()

        flash("Message sent! We'll get back to you soon.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html", current_year=date.today().year)


# Admin page
@app.route("/admin")
@login_required
@role_required("admin")
def admin():
    q = (request.args.get("q") or "").strip()

    conn = get_db_connection()
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        # --- Books (searchable) ---
        if q:
            cur.execute(
                """
                SELECT
                  b.id,
                  b.title,
                  a.name AS author,
                  b.description,
                  c.name AS category,
                  b.price,
                  b.cover,
                  b.file
                FROM books b
                JOIN authors a ON a.id = b.author_id
                JOIN categories c ON c.id = b.category_id
                WHERE b.title ILIKE %s
                   OR a.name ILIKE %s
                   OR c.name ILIKE %s
                ORDER BY b.id;
                """,
                (f"%{q}%", f"%{q}%", f"%{q}%"),
            )
        else:
            cur.execute(
                """
                SELECT
                  b.id,
                  b.title,
                  a.name AS author,
                  b.description,
                  c.name AS category,
                  b.price,
                  b.cover,
                  b.file
                FROM books b
                JOIN authors a ON a.id = b.author_id
                JOIN categories c ON c.id = b.category_id
                ORDER BY b.id;
                """
            )
        books = cur.fetchall()

        # --- Categories (not filtered) ---
        cur.execute(
            """
            SELECT
              c.id,
              c.name,
              COUNT(b.id) AS book_count
            FROM categories c
            LEFT JOIN books b ON b.category_id = c.id
            GROUP BY c.id, c.name
            ORDER BY c.id;
            """
        )
        categories = cur.fetchall()

        # --- Authors (not filtered) ---
        cur.execute(
            """
            SELECT
              a.id,
              a.name,
              COUNT(b.id) AS book_count
            FROM authors a
            LEFT JOIN books b ON b.author_id = a.id
            GROUP BY a.id, a.name
            ORDER BY a.id;
            """
        )
        authors = cur.fetchall()

    conn.close()

    return render_template(
        "admin.html",
        books=books,
        categories=categories,
        authors=authors,
        search_query=q,  # pass current q to template
        books_count=len(books),  # handy if you want to show "X results"
    )


# User page
@app.route("/user")
@login_required
@role_required("user")
def user():
    # Example: user profile / orders / saved books
    return render_template("user.html")


# Register page
@app.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        errors = []
        if not full_name:
            errors.append("Full name is required.")
        if not email:
            errors.append("Email is required.")
        if not password:
            errors.append("Password is required.")
        if password and len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if errors:
            return render_template(
                "register.html", errors=errors, full_name=full_name, email=email
            )

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE email=%s;", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return render_template(
                "register.html",
                errors=["Email is already registered."],
                full_name=full_name,
                email=email,
            )

        pwd_hash = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s);",
            (full_name, email, pwd_hash),
        )
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for("login"))

    return render_template("register.html")


# Logout page
@app.post("/logout")
def logout():
    session.clear()  # or pop specific keys if you prefer
    flash("You’ve been logged out.", "info")
    return redirect(url_for("index"))


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0, private"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# Add Book page (add new book)
@app.route("/add_book", methods=["GET", "POST"])
@login_required
@role_required("admin")
def add_book():
    conn = get_db_connection()
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Dropdown data
        cur.execute("SELECT id, name FROM authors ORDER BY name;")
        authors = cur.fetchall()
        cur.execute("SELECT id, name FROM categories ORDER BY name;")
        categories = cur.fetchall()

        if request.method == "POST":
            form = request.form
            files = request.files

            title = (form.get("book_title") or "").strip()
            description = (form.get("book_description") or "").strip() or None
            author_id_raw = (form.get("author_id") or "").strip()
            category_id_raw = (form.get("category_id") or "").strip()
            price_raw = (form.get("book_price") or "").strip()

            cover_file = files.get("book_cover")
            book_file = files.get("file")

            # --- Basic validation ---
            if not title:
                flash("Book title cannot be empty.", "danger")
                return redirect(url_for("add_book"))
            if not author_id_raw:
                flash("Please select an author.", "danger")
                return redirect(url_for("add_book"))
            if not category_id_raw:
                flash("Please select a category.", "danger")
                return redirect(url_for("add_book"))

            # Parse IDs
            try:
                author_id = int(author_id_raw)
                category_id = int(category_id_raw)
            except ValueError:
                flash("Invalid author or category.", "danger")
                return redirect(url_for("add_book"))

            # Parse price
            price = None
            if price_raw:
                try:
                    price = float(price_raw)
                    if price < 0:
                        raise ValueError
                except ValueError:
                    flash("Price must be a valid non-negative number.", "danger")
                    return redirect(url_for("add_book"))

            # Files required
            if not cover_file or not cover_file.filename:
                flash("Please upload a book cover.", "danger")
                return redirect(url_for("add_book"))
            if not book_file or not book_file.filename:
                flash("Please upload the book file.", "danger")
                return redirect(url_for("add_book"))

            # Extension checks
            if not allowed(cover_file.filename, ALLOWED_COVER_EXTS):
                flash(
                    "Invalid cover file type. Allowed: png, jpg, jpeg, gif, webp.",
                    "danger",
                )
                return redirect(url_for("add_book"))
            if not allowed(book_file.filename, ALLOWED_FILE_EXTS):
                flash(
                    "Invalid book file type. Allowed: pdf, epub, mobi, txt.", "danger"
                )
                return redirect(url_for("add_book"))

            # --- Generate unique safe filenames and absolute paths ---
            cover_name, cover_path = save_unique(COVERS_DIR, cover_file.filename)
            file_name, file_path = save_unique(FILES_DIR, book_file.filename)

            # --- Save files to disk ---
            try:
                cover_file.save(cover_path)
                book_file.save(file_path)
            except Exception as e:
                print("Upload save error:", e)
                flash("Failed to save uploaded files.", "danger")
                return redirect(url_for("add_book"))

            # Paths stored in DB relative to /static
            cover_rel = f"uploads/covers/{cover_name}"
            file_rel = f"uploads/files/{file_name}"

            # --- Insert DB row ---
            try:
                cur.execute(
                    """
                    INSERT INTO books (title, author_id, category_id, description, price, cover, file)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (
                        title,
                        author_id,
                        category_id,
                        description,
                        price,
                        cover_rel,
                        file_rel,
                    ),
                )
                conn.commit()
                flash(f"Book '{title}' added successfully!", "success")
                return redirect(url_for("add_book"))
            except psycopg2.Error as e:
                # Roll back and clean up saved files if DB insert failed
                conn.rollback()
                try:
                    if cover_path.exists():
                        cover_path.unlink()
                    if file_path.exists():
                        file_path.unlink()
                except Exception:
                    pass
                print("DB error:", e)
                flash("Database error while adding the book.", "danger")
                return redirect(url_for("add_book"))

    conn.close()
    return render_template("add_book.html", authors=authors, categories=categories)


# Add author page
@app.route("/add_author", methods=["GET", "POST"])
@login_required
@role_required("admin")
def add_author():
    conn = get_db_connection()
    with conn, conn.cursor() as cur:
        if request.method == "POST":
            author_name = request.form["author_name"].strip()

            # check for empty input
            if not author_name:
                flash("Invalid Author Name", "danger")
                return redirect(url_for("add_author"))

            # Check for duplicates
            cur.execute(
                "SELECT 1 FROM authors WHERE LOWER(name) = LOWER(%s);", (author_name,)
            )
            if cur.fetchone():
                flash(f"Author '{author_name}' already exists.", "warning")
                return redirect(url_for("add_author"))

            try:
                # Insert new author into DB
                cur.execute(
                    "INSERT INTO authors (name) VALUES (%s) RETURNING id;",
                    (author_name,),
                )
                conn.commit()

                flash(f"Author '{author_name}' added successfully!", "success")
                return redirect(url_for("add_author"))

            except psycopg2.Error as e:
                conn.rollback()
                flash("Error adding author. Maybe it already exists?", "danger")
                print("Database error:", e)

    conn.close()
    return render_template("add_author.html")


# Add category page
@app.route("/add_category", methods=["GET", "POST"])
@login_required
@role_required("admin")
def add_category():
    conn = get_db_connection()
    with conn, conn.cursor() as cur:
        if request.method == "POST":
            category_name = request.form["category_name"].strip()

            # Basic validation
            if not category_name:
                flash("Invalid Category Name.", "danger")
                return redirect(url_for("add_category"))
            if len(category_name) > 80:
                flash("Category name is too long (max 80 chars).", "warning")
                return redirect(url_for("add_category"))

            # Duplicate check (case-insensitive)
            cur.execute(
                "SELECT 1 FROM categories WHERE LOWER(name) = LOWER(%s);",
                (category_name,),
            )
            if cur.fetchone():
                flash(f"Category '{category_name}' already exists.", "warning")
                return redirect(url_for("add_category"))

            try:
                cur.execute(
                    "INSERT INTO categories (name) VALUES (%s) RETURNING id;",
                    (category_name,),
                )
                conn.commit()
                flash(f"Category '{category_name}' added successfully!", "success")
                return redirect(url_for("add_category"))

            except psycopg2.Error as e:
                conn.rollback()
                flash("Database error while adding category.", "danger")
                print("Database error:", e)

    conn.close()
    return render_template("add_category.html")


@app.route("/edit_category/<int:category_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_category(category_id):
    conn = get_db_connection()
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Get category
        cur.execute("SELECT id, name FROM categories WHERE id = %s;", (category_id,))
        category = cur.fetchone()
        if not category:
            flash("Category not found.", "danger")
            conn.close()
            return redirect(url_for("edit_category"))

        if request.method == "POST":
            new_name = (request.form.get("name") or "").strip()

            if not new_name:
                flash("Category name cannot be empty.", "danger")

            elif new_name.lower() == category["name"].lower():
                # Case-insensitive check: same name
                flash("No changes were made.", "info")

            else:
                # Duplicate check
                cur.execute(
                    "SELECT 1 FROM categories WHERE LOWER(name) = LOWER(%s) AND id != %s;",
                    (new_name, category_id),
                )
                if cur.fetchone():
                    flash("Category already exists.", "warning")
                else:
                    try:
                        cur.execute(
                            "UPDATE categories SET name = %s WHERE id = %s;",
                            (new_name, category_id),
                        )
                        conn.commit()
                        flash("Category updated successfully.", "success")
                        category["name"] = new_name  # update object for template
                    except Exception:
                        conn.rollback()
                        flash("Error updating category.", "danger")

    conn.close()
    return render_template("edit_category.html", category=category)


@app.route("/edit_author/<int:author_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_author(author_id):
    conn = get_db_connection()
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, name FROM authors WHERE id = %s;", (author_id,))
        author = cur.fetchone()
        if not author:
            flash("Author not found.", "danger")
            conn.close()
            return redirect(url_for("admin"))

        if request.method == "POST":
            new_name = (request.form.get("name") or "").strip()

            if not new_name:
                flash("Author name cannot be empty.", "danger")

            elif new_name.lower() == author["name"].lower():
                flash("No changes were made.", "info")

            else:
                # Duplicate (case-insensitive) check
                cur.execute(
                    "SELECT 1 FROM authors WHERE LOWER(name) = LOWER(%s) AND id != %s;",
                    (new_name, author_id),
                )
                if cur.fetchone():
                    flash("Author already exists.", "warning")
                else:
                    try:
                        cur.execute(
                            "UPDATE authors SET name = %s WHERE id = %s;",
                            (new_name, author_id),
                        )
                        conn.commit()
                        flash("Author updated successfully.", "success")
                        author["name"] = new_name  # keep the edited value on the page
                    except Exception:
                        conn.rollback()
                        flash("Error updating author.", "danger")

    conn.close()
    return render_template("edit_author.html", author=author)


@app.route("/edit_book/<int:book_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_book(book_id):
    def to_float(v):
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    conn = get_db_connection()
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Dropdowns
        cur.execute("SELECT id, name FROM authors ORDER BY name;")
        authors = cur.fetchall()
        cur.execute("SELECT id, name FROM categories ORDER BY name;")
        categories = cur.fetchall()

        # Current book
        cur.execute(
            """
            SELECT id, title, author_id, description, category_id, price, cover, file
            FROM books
            WHERE id = %s;
        """,
            (book_id,),
        )
        book = cur.fetchone()
        if not book:
            flash("Book not found.", "danger")
            conn.close()
            return redirect(url_for("admin"))

        if request.method == "POST":
            form = request.form
            files = request.files

            new_title = (form.get("book_title") or "").strip()
            new_desc = (form.get("book_description") or "").strip()
            author_raw = (form.get("author_id") or "").strip()
            category_raw = (form.get("category_id") or "").strip()
            price_raw = (form.get("book_price") or "").strip()

            cover_file = files.get("book_cover")
            book_file = files.get("file")

            # --- Validation ---
            if not new_title:
                flash("Title cannot be empty.", "danger")
                return render_template(
                    "edit_book.html", book=book, authors=authors, categories=categories
                )

            try:
                new_author_id = int(author_raw)
                new_category_id = int(category_raw)
            except ValueError:
                flash("Please select a valid author and category.", "danger")
                return render_template(
                    "edit_book.html", book=book, authors=authors, categories=categories
                )

            # Price can be empty (NULL)
            if price_raw == "":
                new_price = None
            else:
                try:
                    new_price = float(price_raw)
                    if new_price < 0:
                        raise ValueError
                except ValueError:
                    flash("Price must be a valid non-negative number.", "danger")
                    return render_template(
                        "edit_book.html",
                        book=book,
                        authors=authors,
                        categories=categories,
                    )

            # --- Optional uploads (keep existing if nothing uploaded) ---
            new_cover_rel = book["cover"]
            if cover_file and cover_file.filename:
                if not allowed(cover_file.filename, ALLOWED_COVER_EXTS):
                    flash(
                        "Invalid cover type. Allowed: png, jpg, jpeg, gif, webp.",
                        "warning",
                    )
                else:
                    cover_name, cover_path = save_unique(
                        COVERS_DIR, cover_file.filename
                    )
                    try:
                        cover_file.save(cover_path)
                        new_cover_rel = f"uploads/covers/{cover_name}"
                    except Exception:
                        flash("Failed to save new cover.", "danger")

            new_file_rel = book["file"]
            if book_file and book_file.filename:
                if not allowed(book_file.filename, ALLOWED_FILE_EXTS):
                    flash(
                        "Invalid book file type. Allowed: pdf, epub, mobi, txt.",
                        "warning",
                    )
                else:
                    file_name, file_path = save_unique(FILES_DIR, book_file.filename)
                    try:
                        book_file.save(file_path)
                        new_file_rel = f"uploads/files/{file_name}"
                    except Exception:
                        flash("Failed to save new file.", "danger")

            # --- No-change detection ---
            no_change = (
                new_title.lower() == (book["title"] or "").lower()
                and new_desc == (book["description"] or "")
                and new_author_id == book["author_id"]
                and new_category_id == book["category_id"]
                and (new_price == to_float(book["price"]))
                and new_cover_rel == book["cover"]
                and new_file_rel == book["file"]
            )
            if no_change:
                flash("No changes were made.", "info")
                return render_template(
                    "edit_book.html", book=book, authors=authors, categories=categories
                )

            # --- Optional duplicate check: same (title, author) exists elsewhere ---
            cur.execute(
                """
                SELECT 1
                FROM books
                WHERE LOWER(title) = LOWER(%s) AND author_id = %s AND id <> %s
                LIMIT 1;
            """,
                (new_title, new_author_id, book_id),
            )
            if cur.fetchone():
                flash("A book with this title and author already exists.", "warning")
                return render_template(
                    "edit_book.html", book=book, authors=authors, categories=categories
                )

            # --- Update ---
            try:
                cur.execute(
                    """
                    UPDATE books
                    SET title = %s,
                        author_id = %s,
                        description = %s,
                        category_id = %s,
                        price = %s,
                        cover = %s,
                        file = %s
                    WHERE id = %s;
                """,
                    (
                        new_title,
                        new_author_id,
                        new_desc,
                        new_category_id,
                        new_price,
                        new_cover_rel,
                        new_file_rel,
                        book_id,
                    ),
                )
                conn.commit()

                # reflect new values in memory so the page shows them
                book["title"] = new_title
                book["author_id"] = new_author_id
                book["description"] = new_desc
                book["category_id"] = new_category_id
                book["price"] = new_price
                book["cover"] = new_cover_rel
                book["file"] = new_file_rel

                flash("Book updated successfully.", "success")
            except Exception:
                conn.rollback()
                flash("Error updating book.", "danger")

    conn.close()
    return render_template(
        "edit_book.html", book=book, authors=authors, categories=categories
    )


@app.route("/delete_book/<int:book_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_book(book_id):
    conn = get_db_connection()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT cover, file FROM books WHERE id = %s;", (book_id,))
            book = cur.fetchone()
            if not book:
                flash("Book not found.", "danger")
                return redirect(url_for("admin"))

            # Delete row first (if FK blocks, files won't be touched)
            cur.execute("DELETE FROM books WHERE id = %s;", (book_id,))

        # Remove files on disk: DB paths are relative to /static
        static_dir = Path(current_app.root_path) / "static"

        def rm_static(rel_path: str | None):
            if not rel_path:
                return
            p = static_dir / rel_path.lstrip("/\\")
            try:
                p.unlink(
                    missing_ok=True
                )  # Python 3.8+: you can emulate with exists()+unlink()
            except Exception:
                pass  # Don't block UI if file is missing/locked

        rm_static(book.get("cover"))  # e.g. "uploads/covers/<name>"
        rm_static(book.get("file"))  # e.g. "uploads/files/<name>"

        flash("Book deleted successfully.", "success")
    except errors.ForeignKeyViolation:
        conn.rollback()
        flash(
            "Cannot delete this book because it’s referenced elsewhere (inventory/sales).",
            "warning",
        )
    except Exception as e:
        conn.rollback()
        flash(f"Delete failed: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for("admin"))


@app.route("/delete_category/<int:category_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_category(category_id):
    # (Optional) protect a default category ID if you use one
    PROTECTED_CATEGORY_ID = None  # e.g., 1
    if PROTECTED_CATEGORY_ID and category_id == PROTECTED_CATEGORY_ID:
        flash("You cannot delete the default category.", "warning")
        return redirect(url_for("admin"))

    conn = get_db_connection()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check existence + usage
            cur.execute(
                "SELECT id, name FROM categories WHERE id = %s;", (category_id,)
            )
            cat = cur.fetchone()
            if not cat:
                flash("Category not found.", "danger")
                return redirect(url_for("admin"))

            cur.execute(
                "SELECT COUNT(*) AS cnt FROM books WHERE category_id = %s;",
                (category_id,),
            )
            cnt = cur.fetchone()["cnt"]

            if cnt and int(cnt) > 0:
                flash(
                    f"Cannot delete '{cat['name']}' because {cnt} book(s) are assigned to it.",
                    "warning",
                )
                return redirect(url_for("admin"))

            # Safe to delete
            cur.execute("DELETE FROM categories WHERE id = %s;", (category_id,))

        flash(f"Category '{cat['name']}' deleted.", "success")
    except errors.ForeignKeyViolation:
        conn.rollback()
        flash(
            "Cannot delete this category because it’s referenced by books.", "warning"
        )
    except Exception as e:
        conn.rollback()
        flash(f"Delete failed: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for("admin"))


@app.route("/delete_author/<int:author_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_author(author_id):
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            # Check usage
            cur.execute("SELECT COUNT(*) FROM books WHERE author_id=%s;", (author_id,))
            cnt = cur.fetchone()[0]
            if cnt and int(cnt) > 0:
                flash(
                    f"Cannot delete author because {cnt} book(s) reference them.",
                    "warning",
                )
                return redirect(url_for("admin"))

            # Delete author
            cur.execute("DELETE FROM authors WHERE id=%s;", (author_id,))
        flash("Author deleted.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Delete failed: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=True)
