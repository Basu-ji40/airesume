import os

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import RealDictCursor
from flask import Flask, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hyrizon-local-secret-key")

PGHOST = os.environ.get("PGHOST", "localhost")
PGPORT = os.environ.get("PGPORT", "5432")
PGDATABASE = os.environ.get("PGDATABASE", "project_db")
PGUSER = os.environ.get("PGUSER", "postgres")
PGPASSWORD = os.environ.get("PGPASSWORD", "Developer@Basu")


class Database:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=PGHOST,
            port=PGPORT,
            dbname=PGDATABASE,
            user=PGUSER,
            password=PGPASSWORD,
            cursor_factory=RealDictCursor,
        )

    def execute(self, query, params=None):
        cursor = self.conn.cursor()
        cursor.execute(query.replace("?", "%s"), params or ())
        return cursor

    def executemany(self, query, values):
        cursor = self.conn.cursor()
        cursor.executemany(query.replace("?", "%s"), values)
        return cursor

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def ensure_database_exists():
    conn = psycopg2.connect(
        host=PGHOST,
        port=PGPORT,
        dbname="postgres",
        user=PGUSER,
        password=PGPASSWORD,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PGDATABASE,))
    exists = cursor.fetchone()
    if not exists:
        cursor.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(PGDATABASE))
        )
    cursor.close()
    conn.close()


def get_db():
    if "db" not in g:
        g.db = Database()
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    ensure_database_exists()
    with app.app_context():
        db = get_db()
        db.execute(
            
            """CREATE TABLE IF NOT EXISTS roles (
                role_id SERIAL PRIMARY KEY,
                role_name VARCHAR(30) NOT NULL UNIQUE,
                description VARCHAR(100),
                is_active BOOLEAN DEFAULT TRUE
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id SERIAL PRIMARY KEY,
                first_name VARCHAR(60) NOT NULL,
                last_name VARCHAR(60),
                email VARCHAR(120) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                role_id INTEGER REFERENCES roles(role_id),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            );
            """
        )
        db.executemany(
            """
            INSERT INTO roles (role_name, description, is_active)
            VALUES (?, ?, TRUE)
            ON CONFLICT (role_name) DO NOTHING
            """,
            [
                ("admin", "System administrator"),
                ("user", "Registered user"),
            ],
        )
        db.commit()


def row_value(name, default=""):
    value = request.form.get(name, default)
    return value.strip() if isinstance(value, str) else value


def role_id(role_name):
    db = get_db()
    role = db.execute(
        "SELECT role_id FROM roles WHERE role_name = ?", (role_name,)
    ).fetchone()
    return role["role_id"] if role else None


@app.after_request
def prepare_existing_links_and_forms(response):
    if not response.content_type.startswith("text/html"):
        return response

    html = response.get_data(as_text=True)
    if request.path == "/login" and request.args.get("error"):
        error_html = """
<div class="alert alert-danger text-center py-2 mb-3" role="alert">
    Invalid email or password.
</div>
"""
        html = html.replace(
            '<h6 class="text-center text-secondary fw-normal mb-4">',
            error_html + '\n<h6 class="text-center text-secondary fw-normal mb-4">',
            1,
        )

    if request.path == "/dashboard":
        html = html.replace(
            '<a class="dropdown-item" href="#">Logout</a>',
            '<a class="dropdown-item" href="/logout">Logout</a>',
            1,
        )

    helper_script = """
<script>
(function () {
    if (window.location.pathname !== '/login') return;
    const form = document.querySelector('form');
    if (!form) return;
    form.method = 'POST';
    form.action = '/login';

    const inputs = form.querySelectorAll('input');
    if (inputs[0] && !inputs[0].name) inputs[0].name = 'email';
    if (inputs[1] && !inputs[1].name) inputs[1].name = 'password';

    const loginLink = Array.from(form.querySelectorAll('a.btn')).find(
        el => el.textContent.trim().toLowerCase() === 'login'
    );
    if (loginLink) {
        const button = document.createElement('button');
        button.type = 'submit';
        button.className = loginLink.className;
        button.innerHTML = loginLink.innerHTML;
        loginLink.replaceWith(button);
    }
})();
</script>
"""
    if "</body>" in html:
        html = html.replace("</body>", helper_script + "\n</body>")
        response.set_data(html)
    return response


@app.route("/")
def index():
    return render_template("index.html" ,active_page="index")

    
@app.route("/about")
def About():
    return render_template("about.html", active_page="about")


@app.route("/feature")
def Feature_page():
    return render_template("feature.html", active_page="feature")


@app.route("/contact")
def Contact():
    return render_template("contact.html", active_page="contact")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = row_value("email")
        password = row_value("password")
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ? AND is_active = TRUE",
            (email,),
        ).fetchone()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["user_id"]
            session["email"] = user["email"]
            db.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user["user_id"],),
            )
            db.commit()
            return redirect(url_for("dashboard"))

        return redirect(url_for("login", error="invalid"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = row_value("first_name")
        middle_name = row_value("middle_name")
        last_name = row_value("last_name")
        email = row_value("email")  
        password = row_value("password")
        confirm_password = row_value("confirm_password")

        if not first_name or not last_name or not email or password != confirm_password:
            return redirect(url_for("register"))

  
        db = get_db()
        existing = db.execute(
            "SELECT user_id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            return redirect(url_for("login"))

        full_first_name = f"{first_name} {middle_name}".strip()
        cursor = db.execute(
            """
            INSERT INTO users
                (first_name, last_name, email, password, role_id, is_active)
            VALUES (?, ?, ?, ?, ?, TRUE)
            RETURNING user_id
            """,
            (
                full_first_name,
                last_name,
                email,
                generate_password_hash(password),
                role_id("user"),
            ),
        )
        cursor.fetchone()
        db.commit()

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/home")
def home():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/resume", methods=["GET", "POST"])
def resume():
    if request.method == "POST":
        return redirect(url_for("resume"))
    return render_template("resume.html")


@app.route("/job", methods=["GET", "POST"])
def job():
    if request.method == "POST":
        return redirect(url_for("job"))
    return render_template("job.html")


@app.route("/candidates", methods=["GET", "POST"])
def candidates():
    if request.method == "POST":
        return redirect(url_for("candidates"))
    return render_template("candidates.html")


@app.route("/analysis", methods=["GET", "POST"])
def analysis():
    if request.method == "POST":
        return redirect(url_for("analysis"))
     
    return render_template("analysis.html")


@app.route("/interview", methods=["GET", "POST"])
def interview():
    if request.method == "POST":
        return redirect(url_for("interview"))
    return render_template("interview.html")


@app.route("/analytics")
def analytics():
    monthly_trends = {
        "labels": ["Feb", "Mar", "Apr", "May", "Jun", "Jul"],
        "applications": [98, 122, 141, 165, 178, 116],
    }

    return render_template(
        "analytics.html",
        monthly_trends=monthly_trends,
    )


@app.route("/reports")
def reports():
    return render_template("reports.html")


@app.route("/settings")
def settings():
    return render_template("settings.html")


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
