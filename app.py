from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, session, abort
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
from datetime import datetime, date
import calendar
import hmac
import secrets
import os
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "concept_tracking.db"
UPLOAD_DIR = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "local-concept-tracking-change-this-key")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)



def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_code TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        father_name TEXT,
        cnic TEXT,
        phone TEXT NOT NULL,
        alternate_phone TEXT,
        email TEXT,
        address TEXT,
        city TEXT,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        registration_no TEXT NOT NULL,
        vehicle_type TEXT NOT NULL,
        make_model TEXT,
        model_year TEXT,
        color TEXT,
        engine_no TEXT,
        chassis_no TEXT,
        tracker_imei TEXT,
        sim_number TEXT,
        installation_date TEXT,
        tracker_status TEXT NOT NULL DEFAULT 'Active',
        notes TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        amount REAL NOT NULL,
        duration_months INTEGER NOT NULL DEFAULT 12,
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        vehicle_id INTEGER NOT NULL,
        plan_id INTEGER NOT NULL,
        start_date TEXT NOT NULL,
        expiry_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Active',
        discount REAL NOT NULL DEFAULT 0,
        FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
        FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
        FOREIGN KEY(plan_id) REFERENCES plans(id)
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        subscription_id INTEGER,
        amount REAL NOT NULL,
        payment_date TEXT NOT NULL,
        method TEXT NOT NULL DEFAULT 'Cash',
        reference TEXT,
        notes TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
        FOREIGN KEY(subscription_id) REFERENCES subscriptions(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        vehicle_id INTEGER,
        doc_type TEXT NOT NULL,
        file_name TEXT NOT NULL,
        original_name TEXT,
        uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
        FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS auth_users (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS tracker_models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_name TEXT NOT NULL UNIQUE,
        tracker_type TEXT NOT NULL DEFAULT '',
        unit_cost REAL NOT NULL DEFAULT 0,
        sale_price REAL NOT NULL DEFAULT 0,
        supplier TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS inventory_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracker_model_id INTEGER NOT NULL,
        transaction_type TEXT NOT NULL CHECK (transaction_type IN ('PURCHASE','INSTALL','ADJUSTMENT')),
        quantity INTEGER NOT NULL,
        unit_cost REAL NOT NULL DEFAULT 0,
        transaction_date TEXT NOT NULL,
        customer_id INTEGER,
        vehicle_id INTEGER,
        vehicle_registration TEXT NOT NULL DEFAULT '',
        reference TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(tracker_model_id) REFERENCES tracker_models(id),
        FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE SET NULL,
        FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_inventory_tx_model ON inventory_transactions(tracker_model_id, transaction_date);
    """)
    if conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO plans(name, amount, duration_months, description) VALUES (?,?,?,?)",
            [
                ("Annual Standard", 12000, 12, "Standard vehicle tracking service"),
                ("Annual Premium", 18000, 12, "Premium tracking + priority support"),
                ("Bike Annual", 9000, 12, "Motorbike tracking service"),
            ],
        )
    conn.commit()
    conn.close()


def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def money(value):
    return f"PKR {float(value or 0):,.0f}"


def add_months(source_date, months):
    month_index = source_date.month - 1 + months
    year = source_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@app.template_filter("money")
def money_filter(value):
    return money(value)


@app.template_filter("pretty_date")
def pretty_date(value):
    if not value:
        return "—"
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return value


@app.before_request
def require_login():
    if request.method == "POST":
        expected = session.get("csrf_token", "")
        submitted = request.form.get("_csrf_token", "")
        if not expected or not submitted or not hmac.compare_digest(expected, submitted):
            abort(400, description="The form expired or could not be verified. Refresh the page and try again.")
    public_endpoints = {"login", "setup_admin", "static"}
    if request.endpoint not in public_endpoints and not session.get("logged_in"):
        return redirect(url_for("login", next=request.path))


@app.context_processor
def inject_globals():
    stats = {"customers": 0, "vehicles": 0, "active": 0, "revenue": 0}
    if session.get("logged_in") and DB_PATH.exists():
        conn = db()
        stats = {
            "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
            "vehicles": conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0],
            "active": conn.execute("SELECT COUNT(*) FROM subscriptions WHERE status='Active'").fetchone()[0],
            "revenue": conn.execute("SELECT COALESCE(SUM(amount),0) FROM payments").fetchone()[0],
            "inventory_available": conn.execute("""SELECT COALESCE(SUM(CASE WHEN t.transaction_type='PURCHASE' THEN t.quantity WHEN t.transaction_type='INSTALL' THEN -t.quantity ELSE t.quantity END),0) FROM inventory_transactions t""").fetchone()[0],
            "inventory_installed": conn.execute("SELECT COALESCE(SUM(quantity),0) FROM inventory_transactions WHERE transaction_type='INSTALL'").fetchone()[0],
            "inventory_value": conn.execute("""SELECT COALESCE(SUM(m.unit_cost * (SELECT COALESCE(SUM(CASE WHEN t.transaction_type='PURCHASE' THEN t.quantity WHEN t.transaction_type='INSTALL' THEN -t.quantity ELSE t.quantity END),0) FROM inventory_transactions t WHERE t.tracker_model_id=m.id)),0) FROM tracker_models m""").fetchone()[0],
        }
        conn.close()
    csrf_token = session.get("csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_hex(32)
        session["csrf_token"] = csrf_token
    return {"stats": stats, "today": date.today().isoformat(), "company_name": "Concept Tracking Server Pvt. Ltd.", "csrf_token": csrf_token}


@app.route("/setup-admin", methods=["GET", "POST"])
def setup_admin():
    conn = db()
    existing = conn.execute("SELECT id FROM auth_users LIMIT 1").fetchone()
    if existing:
        conn.close()
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(username) < 3:
            flash("Username must contain at least 3 characters.", "error")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            try:
                conn.execute("INSERT INTO auth_users(id,username,password_hash) VALUES (1,?,?)",
                             (username, generate_password_hash(password)))
                conn.commit()
                conn.close()
                session.clear()
                session["logged_in"] = True
                session["username"] = username
                session.permanent = True
                flash("Administrator account created. Welcome to Concept Tracking CRM.", "success")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("That username is already in use. Choose another username.", "error")
    conn.close()
    return render_template("setup_admin.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    conn = db()
    configured = conn.execute("SELECT id FROM auth_users LIMIT 1").fetchone()
    conn.close()
    if not configured:
        return redirect(url_for("setup_admin"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = db()
        user = conn.execute("SELECT * FROM auth_users WHERE id=1").fetchone()
        conn.close()
        if user and hmac.compare_digest(username.encode("utf-8"), user["username"].encode("utf-8")) and check_password_hash(user["password_hash"], password):
            session.clear()
            session["logged_in"] = True
            session["username"] = user["username"]
            session.permanent = True
            destination = request.args.get("next", "")
            if destination.startswith("/") and not destination.startswith("//"):
                return redirect(destination)
            return redirect(url_for("dashboard"))
        flash("Incorrect username or password. Please try again.", "error")
    return render_template("login.html")


@app.route("/settings/account", methods=["GET", "POST"])
def account_settings():
    conn = db()
    user = conn.execute("SELECT * FROM auth_users WHERE id=1").fetchone()
    if not user:
        conn.close()
        return redirect(url_for("setup_admin"))
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_username = request.form.get("username", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not check_password_hash(user["password_hash"], current_password):
            flash("Current password is incorrect.", "error")
        elif len(new_username) < 3:
            flash("Username must contain at least 3 characters.", "error")
        elif new_password and len(new_password) < 8:
            flash("New password must contain at least 8 characters.", "error")
        elif new_password and new_password != confirm_password:
            flash("New passwords do not match.", "error")
        else:
            password_hash = generate_password_hash(new_password) if new_password else user["password_hash"]
            try:
                conn.execute("UPDATE auth_users SET username=?,password_hash=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
                             (new_username, password_hash))
                conn.commit()
                session["username"] = new_username
                flash("Account settings updated successfully.", "success")
                conn.close()
                return redirect(url_for("account_settings"))
            except sqlite3.IntegrityError:
                flash("That username is already in use.", "error")
    conn.close()
    return render_template("account_settings.html", user=user)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out safely.", "success")
    return redirect(url_for("login"))


@app.route("/")
def dashboard():
    conn = db()
    expiring = conn.execute("""
        SELECT s.id, c.id AS customer_id, c.full_name, c.phone, v.registration_no, s.expiry_date, p.name AS plan_name
        FROM subscriptions s
        JOIN customers c ON c.id=s.customer_id
        JOIN vehicles v ON v.id=s.vehicle_id
        JOIN plans p ON p.id=s.plan_id
        WHERE date(s.expiry_date) BETWEEN date('now') AND date('now','+30 day')
        ORDER BY date(s.expiry_date) LIMIT 8
    """).fetchall()
    recent = conn.execute("""
        SELECT p.*, c.full_name, c.phone FROM payments p
        JOIN customers c ON c.id=p.customer_id ORDER BY p.id DESC LIMIT 8
    """).fetchall()
    overdue_count = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE date(expiry_date)<date('now') AND status='Active'").fetchone()[0]
    conn.close()
    return render_template("dashboard.html", expiring=expiring, recent=recent, overdue_count=overdue_count)


@app.route("/customers")
def customers():
    q = request.args.get("q", "").strip()
    conn = db()
    pattern = f"%{q}%"
    rows = conn.execute("""
        SELECT c.*,
          (SELECT COUNT(*) FROM vehicles v WHERE v.customer_id=c.id) AS vehicle_count,
          (SELECT COALESCE(SUM(p.amount),0) FROM payments p WHERE p.customer_id=c.id) AS paid
        FROM customers c
        WHERE (?='' OR c.full_name LIKE ? OR c.phone LIKE ? OR c.cnic LIKE ? OR c.customer_code LIKE ? OR c.city LIKE ?)
        ORDER BY c.id DESC
    """, (q, pattern, pattern, pattern, pattern, pattern)).fetchall()
    conn.close()
    return render_template("customers.html", customers=rows, q=q)


CUSTOMER_FIELDS = ["full_name", "father_name", "cnic", "phone", "alternate_phone", "email", "address", "city", "notes"]
VEHICLE_FIELDS = ["registration_no", "vehicle_type", "make_model", "model_year", "color", "engine_no", "chassis_no", "tracker_imei", "sim_number", "installation_date", "tracker_status", "notes"]


@app.route("/customers/new", methods=["GET", "POST"])
def new_customer():
    if request.method == "POST":
        data = {key: request.form.get(key, "").strip() for key in CUSTOMER_FIELDS}
        if not data["full_name"] or not data["phone"]:
            flash("Customer name and phone number are required.", "error")
            return render_template("customer_form.html", customer=data, editing=False)
        conn = db()
        code = "CTS-" + datetime.now().strftime("%y%m%d%H%M%S%f")
        cur = conn.execute("""
            INSERT INTO customers(customer_code,full_name,father_name,cnic,phone,alternate_phone,email,address,city,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (code, *[data[key] for key in CUSTOMER_FIELDS]))
        conn.commit()
        cid = cur.lastrowid
        conn.close()
        flash("Customer created successfully.", "success")
        return redirect(url_for("customer_detail", customer_id=cid))
    return render_template("customer_form.html", customer={}, editing=False)


@app.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
def edit_customer(customer_id):
    conn = db()
    customer = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not customer:
        conn.close()
        flash("Customer record was not found.", "error")
        return redirect(url_for("customers"))
    if request.method == "POST":
        data = {key: request.form.get(key, "").strip() for key in CUSTOMER_FIELDS}
        if not data["full_name"] or not data["phone"]:
            flash("Customer name and phone number are required.", "error")
            conn.close()
            return render_template("customer_form.html", customer={**dict(customer), **data}, editing=True)
        conn.execute("""UPDATE customers SET full_name=?,father_name=?,cnic=?,phone=?,alternate_phone=?,email=?,address=?,city=?,notes=? WHERE id=?""",
                     (*[data[key] for key in CUSTOMER_FIELDS], customer_id))
        conn.commit()
        conn.close()
        flash("Customer details updated.", "success")
        return redirect(url_for("customer_detail", customer_id=customer_id))
    conn.close()
    return render_template("customer_form.html", customer=customer, editing=True)


@app.route("/customers/<int:customer_id>")
def customer_detail(customer_id):
    conn = db()
    customer = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not customer:
        conn.close()
        flash("Customer record was not found.", "error")
        return redirect(url_for("customers"))
    vehicles = conn.execute("SELECT * FROM vehicles WHERE customer_id=? ORDER BY id DESC", (customer_id,)).fetchall()
    subscriptions = conn.execute("""
        SELECT s.*, v.registration_no, p.name AS plan_name, p.amount AS plan_amount
        FROM subscriptions s JOIN vehicles v ON v.id=s.vehicle_id JOIN plans p ON p.id=s.plan_id
        WHERE s.customer_id=? ORDER BY date(s.expiry_date) DESC
    """, (customer_id,)).fetchall()
    payments = conn.execute("""
        SELECT p.*, s.id AS sub_id FROM payments p LEFT JOIN subscriptions s ON s.id=p.subscription_id
        WHERE p.customer_id=? ORDER BY date(p.payment_date) DESC, p.id DESC
    """, (customer_id,)).fetchall()
    documents = conn.execute("""
        SELECT d.*, v.registration_no FROM documents d LEFT JOIN vehicles v ON v.id=d.vehicle_id
        WHERE d.customer_id=? ORDER BY d.id DESC
    """, (customer_id,)).fetchall()
    plans = conn.execute("SELECT * FROM plans ORDER BY amount").fetchall()
    total_paid = sum(float(item["amount"]) for item in payments)
    total_billed = sum(max(0, float(item["plan_amount"]) - float(item["discount"])) for item in subscriptions)
    conn.close()
    return render_template("customer_detail.html", customer=customer, vehicles=vehicles,
                           subscriptions=subscriptions, payments=payments, documents=documents,
                           total_paid=total_paid, total_billed=total_billed, plans=plans,
                           balance=max(0, total_billed-total_paid))


@app.route("/vehicles/new/<int:customer_id>", methods=["POST"])
def new_vehicle(customer_id):
    data = {key: request.form.get(key, "").strip() for key in VEHICLE_FIELDS}
    if not data["registration_no"] or not data["vehicle_type"]:
        flash("Registration number and vehicle type are required.", "error")
        return redirect(url_for("customer_detail", customer_id=customer_id))
    conn = db()
    exists = conn.execute("SELECT id FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not exists:
        conn.close()
        flash("Customer record was not found.", "error")
        return redirect(url_for("customers"))
    conn.execute("""INSERT INTO vehicles(customer_id,registration_no,vehicle_type,make_model,model_year,color,engine_no,chassis_no,tracker_imei,sim_number,installation_date,tracker_status,notes)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (customer_id, *[data[key] for key in VEHICLE_FIELDS]))
    conn.commit()
    conn.close()
    flash("Vehicle added successfully.", "success")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/vehicles/<int:vehicle_id>/edit", methods=["GET", "POST"])
def edit_vehicle(vehicle_id):
    conn = db()
    vehicle = conn.execute("SELECT * FROM vehicles WHERE id=?", (vehicle_id,)).fetchone()
    if not vehicle:
        conn.close()
        flash("Vehicle record was not found.", "error")
        return redirect(url_for("customers"))
    if request.method == "POST":
        data = {key: request.form.get(key, "").strip() for key in VEHICLE_FIELDS}
        if not data["registration_no"] or not data["vehicle_type"]:
            flash("Registration number and vehicle type are required.", "error")
            conn.close()
            return render_template("vehicle_form.html", vehicle={**dict(vehicle), **data})
        conn.execute("""UPDATE vehicles SET registration_no=?,vehicle_type=?,make_model=?,model_year=?,color=?,engine_no=?,chassis_no=?,tracker_imei=?,sim_number=?,installation_date=?,tracker_status=?,notes=? WHERE id=?""",
                     (*[data[key] for key in VEHICLE_FIELDS], vehicle_id))
        customer_id = vehicle["customer_id"]
        conn.commit()
        conn.close()
        flash("Vehicle details updated.", "success")
        return redirect(url_for("customer_detail", customer_id=customer_id))
    conn.close()
    return render_template("vehicle_form.html", vehicle=vehicle)


@app.route("/subscriptions/new/<int:customer_id>", methods=["POST"])
def new_subscription(customer_id):
    try:
        vehicle_id = int(request.form.get("vehicle_id", "0"))
        plan_id = int(request.form.get("plan_id", "0"))
        start_text = request.form.get("start_date") or date.today().isoformat()
        start = datetime.strptime(start_text, "%Y-%m-%d").date()
        discount = max(0, float(request.form.get("discount") or 0))
    except (ValueError, TypeError):
        flash("Please enter valid service details.", "error")
        return redirect(url_for("customer_detail", customer_id=customer_id))
    conn = db()
    vehicle = conn.execute("SELECT id FROM vehicles WHERE id=? AND customer_id=?", (vehicle_id, customer_id)).fetchone()
    plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not vehicle or not plan:
        conn.close()
        flash("Select a valid vehicle and service plan.", "error")
        return redirect(url_for("customer_detail", customer_id=customer_id))
    expiry = add_months(start, int(plan["duration_months"]))
    conn.execute("""INSERT INTO subscriptions(customer_id,vehicle_id,plan_id,start_date,expiry_date,status,discount)
                    VALUES (?,?,?,?,?,?,?)""", (customer_id, vehicle_id, plan_id, start.isoformat(), expiry.isoformat(), "Active", discount))
    conn.commit()
    conn.close()
    flash("Service subscription created.", "success")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/payments/new/<int:customer_id>", methods=["POST"])
def new_payment(customer_id):
    try:
        amount = float(request.form.get("amount") or 0)
    except ValueError:
        amount = 0
    if amount <= 0:
        flash("Payment amount must be greater than zero.", "error")
        return redirect(url_for("customer_detail", customer_id=customer_id))
    conn = db()
    customer = conn.execute("SELECT id FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not customer:
        conn.close()
        flash("Customer record was not found.", "error")
        return redirect(url_for("customers"))
    subscription_text = request.form.get("subscription_id") or ""
    subscription_id = int(subscription_text) if subscription_text.isdigit() else None
    if subscription_id is not None and not conn.execute("SELECT id FROM subscriptions WHERE id=? AND customer_id=?", (subscription_id, customer_id)).fetchone():
        conn.close()
        flash("Select a valid subscription for this customer.", "error")
        return redirect(url_for("customer_detail", customer_id=customer_id))
    conn.execute("""INSERT INTO payments(customer_id,subscription_id,amount,payment_date,method,reference,notes)
                    VALUES (?,?,?,?,?,?,?)""", (customer_id, subscription_id, amount,
                    request.form.get("payment_date") or date.today().isoformat(), request.form.get("method") or "Cash",
                    request.form.get("reference", "").strip(), request.form.get("notes", "").strip()))
    conn.commit()
    conn.close()
    flash("Payment recorded successfully.", "success")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/documents/upload/<int:customer_id>", methods=["POST"])
def upload_document(customer_id):
    file = request.files.get("document")
    if not file or not file.filename or not allowed(file.filename):
        flash("Choose a valid PDF, JPG, PNG or WEBP file (maximum 10 MB).", "error")
        return redirect(url_for("customer_detail", customer_id=customer_id))
    conn = db()
    if not conn.execute("SELECT id FROM customers WHERE id=?", (customer_id,)).fetchone():
        conn.close()
        flash("Customer record was not found.", "error")
        return redirect(url_for("customers"))
    vehicle_text = request.form.get("vehicle_id") or ""
    vehicle_id = int(vehicle_text) if vehicle_text.isdigit() else None
    if vehicle_id and not conn.execute("SELECT id FROM vehicles WHERE id=? AND customer_id=?", (vehicle_id, customer_id)).fetchone():
        vehicle_id = None
    original = secure_filename(file.filename)
    unique = f"{customer_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{original}"
    file.save(UPLOAD_DIR / unique)
    conn.execute("INSERT INTO documents(customer_id,vehicle_id,doc_type,file_name,original_name) VALUES (?,?,?,?,?)",
                 (customer_id, vehicle_id, request.form.get("doc_type") or "Other", unique, original))
    conn.commit()
    conn.close()
    flash("Document uploaded to the local records folder.", "success")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@app.route("/plans", methods=["GET", "POST"])
def plans():
    conn = db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        try:
            amount = float(request.form.get("amount") or 0)
            duration = int(request.form.get("duration_months") or 12)
        except ValueError:
            amount, duration = 0, 0
        description = request.form.get("description", "").strip()
        if not name or amount <= 0 or duration <= 0:
            flash("Enter a plan name, a valid amount and a duration greater than zero.", "error")
        else:
            conn.execute("INSERT INTO plans(name,amount,duration_months,description) VALUES (?,?,?,?)", (name, amount, duration, description))
            conn.commit()
            flash("Service plan added.", "success")
            conn.close()
            return redirect(url_for("plans"))
    rows = conn.execute("SELECT * FROM plans ORDER BY amount").fetchall()
    conn.close()
    return render_template("plans.html", plans=rows)


@app.route("/plans/<int:plan_id>/edit", methods=["GET", "POST"])
def edit_plan(plan_id):
    conn = db()
    plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not plan:
        conn.close()
        flash("Service plan was not found.", "error")
        return redirect(url_for("plans"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        try:
            amount = float(request.form.get("amount") or 0)
            duration = int(request.form.get("duration_months") or 12)
        except ValueError:
            amount, duration = 0, 0
        description = request.form.get("description", "").strip()
        if not name or amount <= 0 or duration <= 0:
            flash("Enter a valid name, amount and duration.", "error")
            conn.close()
            return render_template("plan_form.html", plan={**dict(plan), "name": name, "amount": amount, "duration_months": duration, "description": description})
        conn.execute("UPDATE plans SET name=?,amount=?,duration_months=?,description=? WHERE id=?", (name, amount, duration, description, plan_id))
        conn.commit()
        conn.close()
        flash("Service plan updated.", "success")
        return redirect(url_for("plans"))
    conn.close()
    return render_template("plan_form.html", plan=plan)


def inventory_models(conn):
    return conn.execute("""
        SELECT m.*,
          COALESCE(SUM(CASE WHEN t.transaction_type='PURCHASE' THEN t.quantity WHEN t.transaction_type='INSTALL' THEN -t.quantity ELSE t.quantity END),0) AS available_qty,
          COALESCE(SUM(CASE WHEN t.transaction_type='PURCHASE' THEN t.quantity ELSE 0 END),0) AS purchased_qty,
          COALESCE(SUM(CASE WHEN t.transaction_type='INSTALL' THEN t.quantity ELSE 0 END),0) AS installed_qty,
          COALESCE(SUM(CASE WHEN t.transaction_type='ADJUSTMENT' THEN t.quantity ELSE 0 END),0) AS adjustment_qty
        FROM tracker_models m LEFT JOIN inventory_transactions t ON t.tracker_model_id=m.id
        GROUP BY m.id ORDER BY m.model_name COLLATE NOCASE
    """).fetchall()


def current_stock(conn, model_id):
    return int(conn.execute("""SELECT COALESCE(SUM(CASE WHEN transaction_type='PURCHASE' THEN quantity WHEN transaction_type='INSTALL' THEN -quantity ELSE quantity END),0) FROM inventory_transactions WHERE tracker_model_id=?""", (model_id,)).fetchone()[0])


@app.route("/inventory")
def inventory():
    conn = db()
    models = inventory_models(conn)
    transactions = conn.execute("""
        SELECT t.*, m.model_name, c.full_name AS customer_name, v.registration_no AS vehicle_plate
        FROM inventory_transactions t JOIN tracker_models m ON m.id=t.tracker_model_id
        LEFT JOIN customers c ON c.id=t.customer_id LEFT JOIN vehicles v ON v.id=t.vehicle_id
        ORDER BY t.id DESC LIMIT 30
    """).fetchall()
    customers = conn.execute("SELECT id,full_name,customer_code FROM customers ORDER BY full_name").fetchall()
    vehicles = conn.execute("SELECT v.id,v.customer_id,v.registration_no,v.make_model,v.vehicle_type FROM vehicles v ORDER BY v.registration_no").fetchall()
    totals = {
        "models": len(models),
        "available": sum(max(0, int(m["available_qty"])) for m in models),
        "installed": sum(int(m["installed_qty"]) for m in models),
        "value": sum(max(0, int(m["available_qty"])) * float(m["unit_cost"] or 0) for m in models),
        "low_stock": sum(1 for m in models if int(m["available_qty"]) <= 5),
    }
    conn.close()
    return render_template("inventory.html", models=models, transactions=transactions, customers=customers, vehicles=vehicles, totals=totals)


@app.route("/inventory/models/new", methods=["POST"])
def new_tracker_model():
    name = request.form.get("model_name", "").strip()
    tracker_type = request.form.get("tracker_type", "").strip()
    supplier = request.form.get("supplier", "").strip()
    notes = request.form.get("notes", "").strip()
    try:
        unit_cost = float(request.form.get("unit_cost") or 0)
        sale_price = float(request.form.get("sale_price") or 0)
    except ValueError:
        unit_cost = sale_price = -1
    if not name or unit_cost < 0 or sale_price < 0:
        flash("Enter a model name and valid tracker prices.", "error")
        return redirect(url_for("inventory"))
    conn = db()
    try:
        conn.execute("INSERT INTO tracker_models(model_name,tracker_type,unit_cost,sale_price,supplier,notes) VALUES (?,?,?,?,?,?)",
                     (name, tracker_type, unit_cost, sale_price, supplier, notes))
        conn.commit()
        flash("Tracker model added. Now use Receive Stock to record the quantity you have.", "success")
    except sqlite3.IntegrityError:
        flash("A tracker model with this name already exists.", "error")
    finally:
        conn.close()
    return redirect(url_for("inventory"))


@app.route("/inventory/models/<int:model_id>/edit", methods=["GET", "POST"])
def edit_tracker_model(model_id):
    conn = db()
    model = conn.execute("SELECT * FROM tracker_models WHERE id=?", (model_id,)).fetchone()
    if not model:
        conn.close()
        flash("Tracker model was not found.", "error")
        return redirect(url_for("inventory"))
    if request.method == "POST":
        name = request.form.get("model_name", "").strip()
        tracker_type = request.form.get("tracker_type", "").strip()
        supplier = request.form.get("supplier", "").strip()
        notes = request.form.get("notes", "").strip()
        try:
            unit_cost = float(request.form.get("unit_cost") or 0)
            sale_price = float(request.form.get("sale_price") or 0)
        except ValueError:
            unit_cost = sale_price = -1
        if not name or unit_cost < 0 or sale_price < 0:
            flash("Enter a model name and valid prices.", "error")
        else:
            try:
                conn.execute("UPDATE tracker_models SET model_name=?,tracker_type=?,unit_cost=?,sale_price=?,supplier=?,notes=? WHERE id=?",
                             (name, tracker_type, unit_cost, sale_price, supplier, notes, model_id))
                conn.commit()
                conn.close()
                flash("Tracker model updated.", "success")
                return redirect(url_for("inventory"))
            except sqlite3.IntegrityError:
                flash("Another tracker model already uses that name.", "error")
        model = {**dict(model), "model_name": name, "tracker_type": tracker_type, "unit_cost": unit_cost, "sale_price": sale_price, "supplier": supplier, "notes": notes}
    conn.close()
    return render_template("tracker_model_form.html", model=model)


@app.route("/inventory/stock-in", methods=["POST"])
def inventory_stock_in():
    try:
        model_id = int(request.form.get("tracker_model_id") or 0)
        quantity = int(request.form.get("quantity") or 0)
        unit_cost = float(request.form.get("unit_cost") or 0)
        tx_date = datetime.strptime(request.form.get("transaction_date") or date.today().isoformat(), "%Y-%m-%d").date().isoformat()
    except (ValueError, TypeError):
        flash("Enter a valid stock quantity, price and date.", "error")
        return redirect(url_for("inventory"))
    reference = request.form.get("reference", "").strip()
    notes = request.form.get("notes", "").strip()
    if model_id < 1 or quantity < 1 or unit_cost < 0:
        flash("Quantity must be at least 1 and price cannot be negative.", "error")
        return redirect(url_for("inventory"))
    conn = db()
    model = conn.execute("SELECT id FROM tracker_models WHERE id=?", (model_id,)).fetchone()
    if not model:
        conn.close()
        flash("Select a valid tracker model.", "error")
        return redirect(url_for("inventory"))
    conn.execute("INSERT INTO inventory_transactions(tracker_model_id,transaction_type,quantity,unit_cost,transaction_date,reference,notes) VALUES (?,'PURCHASE',?,?,?,?,?)",
                 (model_id, quantity, unit_cost, tx_date, reference, notes))
    conn.execute("UPDATE tracker_models SET unit_cost=? WHERE id=?", (unit_cost, model_id))
    conn.commit()
    conn.close()
    flash(f"Stock received: {quantity} tracker(s) added to inventory.", "success")
    return redirect(url_for("inventory"))


@app.route("/inventory/install", methods=["POST"])
def inventory_install():
    try:
        model_id = int(request.form.get("tracker_model_id") or 0)
        quantity = int(request.form.get("quantity") or 0)
        tx_date = datetime.strptime(request.form.get("transaction_date") or date.today().isoformat(), "%Y-%m-%d").date().isoformat()
    except (ValueError, TypeError):
        flash("Enter a valid model, quantity and installation date.", "error")
        return redirect(url_for("inventory"))
    customer_text = request.form.get("customer_id") or ""
    vehicle_text = request.form.get("vehicle_id") or ""
    customer_id = int(customer_text) if customer_text.isdigit() else None
    vehicle_id = int(vehicle_text) if vehicle_text.isdigit() else None
    notes = request.form.get("notes", "").strip()
    conn = db()
    model = conn.execute("SELECT * FROM tracker_models WHERE id=?", (model_id,)).fetchone()
    if not model or quantity < 1:
        conn.close()
        flash("Select a valid tracker model and quantity.", "error")
        return redirect(url_for("inventory"))
    available = current_stock(conn, model_id)
    if quantity > available:
        conn.close()
        flash(f"Not enough stock. Only {available} unit(s) are currently available for this model.", "error")
        return redirect(url_for("inventory"))
    vehicle = None
    if vehicle_id:
        vehicle = conn.execute("SELECT id,customer_id,registration_no FROM vehicles WHERE id=?", (vehicle_id,)).fetchone()
        if not vehicle:
            conn.close()
            flash("Selected vehicle was not found.", "error")
            return redirect(url_for("inventory"))
        if quantity != 1:
            conn.close()
            flash("When linking an installation to one vehicle, set quantity to 1. For bulk installations, leave vehicle blank.", "error")
            return redirect(url_for("inventory"))
        customer_id = vehicle["customer_id"]
    if customer_id and not conn.execute("SELECT id FROM customers WHERE id=?", (customer_id,)).fetchone():
        customer_id = None
    conn.execute("""INSERT INTO inventory_transactions(tracker_model_id,transaction_type,quantity,unit_cost,transaction_date,customer_id,vehicle_id,vehicle_registration,notes)
                    VALUES (?,'INSTALL',?,?,?,?,?,?,?)""",
                 (model_id, quantity, float(model["unit_cost"] or 0), tx_date, customer_id, vehicle_id,
                  vehicle["registration_no"] if vehicle else "", notes))
    conn.commit()
    conn.close()
    flash(f"Installation recorded. {quantity} tracker(s) moved out of available stock.", "success")
    return redirect(url_for("inventory"))


@app.route("/inventory/adjust", methods=["POST"])
def inventory_adjust():
    try:
        model_id = int(request.form.get("tracker_model_id") or 0)
        quantity = int(request.form.get("quantity") or 0)
        tx_date = datetime.strptime(request.form.get("transaction_date") or date.today().isoformat(), "%Y-%m-%d").date().isoformat()
    except (ValueError, TypeError):
        flash("Enter a valid adjustment quantity and date.", "error")
        return redirect(url_for("inventory"))
    notes = request.form.get("notes", "").strip()
    conn = db()
    model = conn.execute("SELECT id,unit_cost FROM tracker_models WHERE id=?", (model_id,)).fetchone()
    available = current_stock(conn, model_id) if model else 0
    if not model or quantity == 0 or available + quantity < 0 or not notes:
        conn.close()
        flash("Choose a model, enter a non-zero adjustment, provide a reason, and do not reduce stock below zero.", "error")
        return redirect(url_for("inventory"))
    conn.execute("""INSERT INTO inventory_transactions(tracker_model_id,transaction_type,quantity,unit_cost,transaction_date,notes)
                    VALUES (?,'ADJUSTMENT',?,?,?,?)""", (model_id, quantity, model["unit_cost"], tx_date, notes))
    conn.commit()
    conn.close()
    flash("Inventory adjustment saved.", "success")
    return redirect(url_for("inventory"))


@app.route("/reports")
def reports():
    conn = db()
    payments = conn.execute("SELECT substr(payment_date,1,7) month, SUM(amount) total FROM payments GROUP BY substr(payment_date,1,7) ORDER BY month DESC LIMIT 12").fetchall()
    vehicle_types = conn.execute("SELECT vehicle_type, COUNT(*) total FROM vehicles GROUP BY vehicle_type ORDER BY total DESC").fetchall()
    overdue = conn.execute("""SELECT c.id customer_id,c.full_name,c.phone,v.registration_no,s.expiry_date
        FROM subscriptions s JOIN customers c ON c.id=s.customer_id JOIN vehicles v ON v.id=s.vehicle_id
        WHERE date(s.expiry_date)<date('now') AND s.status='Active' ORDER BY date(s.expiry_date)""").fetchall()
    conn.close()
    return render_template("reports.html", payments=payments, vehicle_types=vehicle_types, overdue=overdue)


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    conn = db()
    pattern = f"%{q}%"
    rows = conn.execute("""SELECT c.id,c.customer_code,c.full_name,c.phone,c.cnic,v.registration_no,v.tracker_imei
        FROM customers c LEFT JOIN vehicles v ON v.customer_id=c.id
        WHERE c.full_name LIKE ? OR c.phone LIKE ? OR c.cnic LIKE ? OR c.customer_code LIKE ? OR v.registration_no LIKE ? OR v.tracker_imei LIKE ?
        ORDER BY c.id DESC LIMIT 20""", (pattern, pattern, pattern, pattern, pattern, pattern)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
