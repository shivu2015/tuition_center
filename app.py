from flask import (
    Flask, render_template, request,
    redirect, session, url_for, flash
)
from functools import wraps
from io import BytesIO
from flask import send_file
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

import sqlite3
from datetime import date
from functools import wraps
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

app = Flask(__name__)

app.secret_key = "replace-this-with-a-long-random-secret"


# Connect to database
def get_db_connection():
    conn = sqlite3.connect("tuition.db")
    conn.row_factory = sqlite3.Row
    return conn

def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):

        if "admin_id" not in session:
            return redirect(url_for("login"))

        return route_function(*args, **kwargs)

    return wrapper

def teacher_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "teacher_account_id" not in session:
            return redirect(url_for("login", role="teacher"))

        return route_function(*args, **kwargs)

    return wrapper

# Create database table
def init_db():
    conn = get_db_connection()

            # Teacher login accounts
    conn.execute("""
            CREATE TABLE IF NOT EXISTS teacher_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL UNIQUE,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (teacher_id) REFERENCES teachers(id)
            )
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            address TEXT
        )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        subject TEXT NOT NULL,
        phone TEXT,
        email TEXT,
        qualification TEXT
        )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_name TEXT NOT NULL,
        class_name TEXT NOT NULL,
        subject TEXT NOT NULL,
        teacher_id INTEGER,
        fee REAL NOT NULL DEFAULT 0,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id)
        )
    """)

    
        # Teacher timetable
    conn.execute("""
            CREATE TABLE IF NOT EXISTS timetable (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                day_of_week TEXT NOT NULL
                    CHECK (
                        day_of_week IN (
                            'Monday',
                            'Tuesday',
                            'Wednesday',
                            'Thursday',
                            'Friday',
                            'Saturday',
                            'Sunday'
                        )
                    ),
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                room TEXT,
                FOREIGN KEY (course_id)
                    REFERENCES courses(id)
                    ON DELETE CASCADE,
                UNIQUE (course_id, day_of_week, start_time),
                CHECK (start_time < end_time)
            )
        """)


    conn.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        attendance_date TEXT NOT NULL,
        status TEXT NOT NULL
            CHECK (status IN ('Present', 'Absent')),
        UNIQUE (student_id, course_id, attendance_date),
        FOREIGN KEY (student_id) REFERENCES students(id),
        FOREIGN KEY (course_id) REFERENCES courses(id)
        )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS student_fees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        total_fee REAL NOT NULL CHECK(total_fee >= 0),
        UNIQUE(student_id, course_id),
        FOREIGN KEY (student_id) REFERENCES students(id),
        FOREIGN KEY (course_id) REFERENCES courses(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS fee_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fee_id INTEGER NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            payment_date TEXT NOT NULL,
            payment_method TEXT NOT NULL,
            notes TEXT,
            FOREIGN KEY (fee_id) REFERENCES student_fees(id)
        )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS exams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_name TEXT NOT NULL,
        course_id INTEGER NOT NULL,
        exam_date TEXT NOT NULL,
        max_marks REAL NOT NULL CHECK(max_marks > 0),
        FOREIGN KEY (course_id) REFERENCES courses(id)
    )
""")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS exam_marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            marks_obtained REAL NOT NULL CHECK(marks_obtained >= 0),
            UNIQUE(exam_id, student_id),
            FOREIGN KEY (exam_id) REFERENCES exams(id),
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
        )
    """)

        # Create the initial admin account only if none exists
    admin = conn.execute(
        "SELECT id FROM admins WHERE username = ?",
        ("admin",)
    ).fetchone()

    if admin is None:
        password_hash = generate_password_hash("Admin@123")

        conn.execute(
            """
            INSERT INTO admins (username, password_hash)
            VALUES (?, ?)
            """,
            ("admin", password_hash)
        )

    conn.execute("""
    CREATE TABLE IF NOT EXISTS enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        enrollment_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Active'
            CHECK (status IN ('Active', 'Inactive')),
        UNIQUE (student_id, course_id),
        FOREIGN KEY (student_id) REFERENCES students(id),
        FOREIGN KEY (course_id) REFERENCES courses(id)
        )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS student_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL UNIQUE,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id)
            REFERENCES students(id)
            ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

@app.route("/")
@login_required
def home():
    conn = get_db_connection()

    student_count = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    teacher_count = conn.execute(
        "SELECT COUNT(*) FROM teachers"
    ).fetchone()[0]

    course_count = conn.execute(
        "SELECT COUNT(*) FROM courses"
    ).fetchone()[0]

    exam_count = conn.execute(
        "SELECT COUNT(*) FROM exams"
    ).fetchone()[0]

    fee_record_count = conn.execute(
        "SELECT COUNT(*) FROM student_fees"
    ).fetchone()[0]

    pending_fees = conn.execute("""
        SELECT COALESCE(
            SUM(sf.total_fee - COALESCE(p.paid, 0)), 0
        )
        FROM student_fees sf
        LEFT JOIN (
            SELECT fee_id, SUM(amount) AS paid
            FROM fee_payments
            GROUP BY fee_id
        ) p ON sf.id = p.fee_id
    """).fetchone()[0]

    conn.close()

    return render_template(
        "home.html",
        student_count=student_count,
        teacher_count=teacher_count,
        course_count=course_count,
        exam_count=exam_count,
        fee_record_count=fee_record_count,
        pending_fees=pending_fees
    )


@app.route("/students")
@login_required
def students():
    conn = get_db_connection()

    search = request.args.get("search", "").strip()
    class_filter = request.args.get("class_filter", "").strip()
    sort_by = request.args.get("sort_by", "name")

    # Allow only predefined sorting columns
    sort_options = {
        "name": "name COLLATE NOCASE",
        "class": "class_name COLLATE NOCASE",
        "id": "id"
    }

    order_column = sort_options.get(sort_by, "name COLLATE NOCASE")

    query = "SELECT * FROM students WHERE 1=1"
    params = []

    if search:
        query += """
            AND (
                name LIKE ?
                OR class_name LIKE ?
                OR phone LIKE ?
            )
        """
        search_value = f"%{search}%"
        params.extend([search_value, search_value, search_value])

    if class_filter:
        query += " AND class_name = ?"
        params.append(class_filter)

    query += f" ORDER BY {order_column}"

    student_list = conn.execute(query, params).fetchall()

    classes = conn.execute("""
        SELECT DISTINCT class_name
        FROM students
        WHERE class_name IS NOT NULL AND class_name != ''
        ORDER BY class_name COLLATE NOCASE
    """).fetchall()

    conn.close()

    return render_template(
        "students.html",
        students=student_list,
        classes=classes,
        search=search,
        class_filter=class_filter,
        sort_by=sort_by
    )

# Add student
@app.route("/add_student", methods=["GET", "POST"])
@login_required
def add_student():

    if request.method == "POST":

        name = request.form.get("name")
        class_name = request.form.get("class_name")
        phone = request.form.get("phone")
        email = request.form.get("email")
        address = request.form.get("address")

        conn = get_db_connection()

        conn.execute("""
            INSERT INTO students
            (name, class_name, phone, email, address)
            VALUES (?, ?, ?, ?, ?)
        """, (
            name,
            class_name,
            phone,
            email,
            address
        ))

        conn.commit()
        conn.close()

        return redirect("/students")

    return render_template("add_student.html")

@app.route("/edit_student/<int:id>", methods=["GET", "POST"])
@login_required
def edit_student(id):

    conn = get_db_connection()

    student = conn.execute(
        "SELECT * FROM students WHERE id = ?",
        (id,)
    ).fetchone()

    if request.method == "POST":

        name = request.form["name"]
        class_name = request.form["class_name"]
        phone = request.form["phone"]
        email = request.form["email"]
        address = request.form["address"]

        conn.execute("""
            UPDATE students
            SET name = ?,
                class_name = ?,
                phone = ?,
                email = ?,
                address = ?
            WHERE id = ?
        """, (
            name,
            class_name,
            phone,
            email,
            address,
            id
        ))

        conn.commit()
        conn.close()

        return redirect("/students")

    conn.close()

    return render_template(
        "edit_student.html",
        student=student
    )

@app.route("/delete_student/<int:id>")
@login_required
def delete_student(id):

    conn = get_db_connection()

    conn.execute(
        "DELETE FROM students WHERE id = ?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/students")

    # View teachers
@app.route("/teachers")
@login_required
def teachers():

    conn = get_db_connection()

    teacher_list = conn.execute(
        "SELECT * FROM teachers ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template(
        "teachers.html",
        teachers=teacher_list
    )


# Add teacher
@app.route("/add_teacher", methods=["GET", "POST"])
@login_required
def add_teacher():

    if request.method == "POST":

        name = request.form["name"]
        subject = request.form["subject"]
        phone = request.form["phone"]
        email = request.form["email"]
        qualification = request.form["qualification"]

        conn = get_db_connection()

        conn.execute("""
            INSERT INTO teachers
            (name, subject, phone, email, qualification)
            VALUES (?, ?, ?, ?, ?)
        """, (
            name, subject, phone, email, qualification
        ))

        conn.commit()
        conn.close()

        return redirect("/teachers")

    return render_template("add_teacher.html")

    # Edit teacher
@app.route("/edit_teacher/<int:id>", methods=["GET", "POST"])
@login_required
def edit_teacher(id):

    conn = get_db_connection()

    teacher = conn.execute(
        "SELECT * FROM teachers WHERE id = ?", (id,)
    ).fetchone()

    if teacher is None:
        conn.close()
        return "Teacher not found", 404

    if request.method == "POST":

        conn.execute("""
            UPDATE teachers
            SET name = ?,
                subject = ?,
                phone = ?,
                email = ?,
                qualification = ?
            WHERE id = ?
        """, (
            request.form["name"],
            request.form["subject"],
            request.form["phone"],
            request.form["email"],
            request.form["qualification"],
            id
        ))

        conn.commit()
        conn.close()

        return redirect("/teachers")

    conn.close()

    return render_template(
        "edit_teacher.html",
        teacher=teacher
    )


# Delete teacher
@app.route("/delete_teacher/<int:id>", methods=["POST"])
@login_required
def delete_teacher(id):

    conn = get_db_connection()

    conn.execute(
        "DELETE FROM teachers WHERE id = ?", (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/teachers")

@app.route("/courses")
@login_required
def courses():

    conn = get_db_connection()

    course_list = conn.execute("""
        SELECT courses.*,
               teachers.name AS teacher_name
        FROM courses
        LEFT JOIN teachers
        ON courses.teacher_id = teachers.id
        ORDER BY courses.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "courses.html",
        courses=course_list
    )


@app.route("/add_course", methods=["GET", "POST"])
@login_required
def add_course():

    conn = get_db_connection()

    if request.method == "POST":

        course_name = request.form["course_name"].strip()
        class_name = request.form["class_name"].strip()
        subject = request.form["subject"].strip()
        teacher_id = request.form.get("teacher_id") or None

        try:
            fee = float(request.form["fee"])
            if fee < 0:
                raise ValueError
        except ValueError:
            conn.close()
            return "Please enter a valid, non-negative fee.", 400

        conn.execute("""
            INSERT INTO courses
            (course_name, class_name, subject, teacher_id, fee)
            VALUES (?, ?, ?, ?, ?)
        """, (
            course_name, class_name, subject, teacher_id, fee
        ))

        conn.commit()
        conn.close()

        return redirect("/courses")

    teachers = conn.execute(
        "SELECT id, name, subject FROM teachers ORDER BY name"
    ).fetchall()

    conn.close()

    return render_template(
        "add_course.html",
        teachers=teachers
    )

@app.route("/delete_course/<int:course_id>", methods=["POST"])
@login_required
def delete_course(course_id):
    conn = get_db_connection()

    try:
        # Start a transaction
        conn.execute("BEGIN")

        course = conn.execute(
            "SELECT id, course_name FROM courses WHERE id = ?",
            (course_id,)
        ).fetchone()

        if course is None:
            conn.rollback()
            flash("Course not found.", "error")
            return redirect(url_for("courses"))

        course_name = course["course_name"]

        # Delete payment history for this course's fee records
        conn.execute("""
            DELETE FROM fee_payments
            WHERE fee_id IN (
                SELECT id
                FROM student_fees
                WHERE course_id = ?
            )
        """, (course_id,))

        # Delete marks belonging to examinations for this course
        conn.execute("""
            DELETE FROM exam_marks
            WHERE exam_id IN (
                SELECT id
                FROM exams
                WHERE course_id = ?
            )
        """, (course_id,))

        # Delete course-related records
        conn.execute(
            "DELETE FROM attendance WHERE course_id = ?",
            (course_id,)
        )

        conn.execute(
            "DELETE FROM enrollments WHERE course_id = ?",
            (course_id,)
        )

        conn.execute(
            "DELETE FROM student_fees WHERE course_id = ?",
            (course_id,)
        )

        conn.execute(
            "DELETE FROM exams WHERE course_id = ?",
            (course_id,)
        )

        # Delete the course itself
        conn.execute(
            "DELETE FROM courses WHERE id = ?",
            (course_id,)
        )

        conn.commit()

        flash(
            f"Course '{course_name}' and its related records "
            "were permanently deleted.",
            "success"
        )

    except sqlite3.Error as error:
        conn.rollback()
        app.logger.exception("Course deletion failed")

        flash(
            f"Deletion failed. No changes were committed. "
            f"Database error: {error}",
            "error"
        )

    finally:
        conn.close()

    return redirect(url_for("courses"))


@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():

    today = date.today().isoformat()
    selected_course = None
    selected_date = today
    students = []
    existing = {}

    conn = get_db_connection()

    courses = conn.execute(
        "SELECT id, course_name, class_name FROM courses ORDER BY course_name"
    ).fetchall()

    if request.method == "POST":

        selected_course = request.form.get("course_id")
        selected_date = request.form.get("attendance_date", today)

        if selected_course:
            students = conn.execute("""
                SELECT id, name
                FROM students
                ORDER BY name
            """).fetchall()

            saved = conn.execute("""
                SELECT student_id, status
                FROM attendance
                WHERE course_id = ? AND attendance_date = ?
            """, (selected_course, selected_date)).fetchall()

            existing = {
                row["student_id"]: row["status"]
                for row in saved
            }

    records = conn.execute("""
        SELECT attendance.attendance_date,
               students.name AS student_name,
               courses.course_name,
               attendance.status
        FROM attendance
        JOIN students ON attendance.student_id = students.id
        JOIN courses ON attendance.course_id = courses.id
        ORDER BY attendance.attendance_date DESC,
                 students.name
        LIMIT 100
    """).fetchall()

    conn.close()

    return render_template(
        "attendance.html",
        courses=courses,
        students=students,
        records=records,
        existing=existing,
        today=today,
        selected_course=selected_course,
        selected_date=selected_date
    )
    
@app.route("/save_attendance", methods=["POST"])
@login_required
def save_attendance():

    course_id = request.form.get("course_id")
    attendance_date = request.form.get("attendance_date")

    if not course_id or not attendance_date:
        return "Course and date are required.", 400

    try:
        date.fromisoformat(attendance_date)
    except ValueError:
        return "Invalid attendance date.", 400

    conn = get_db_connection()

    course = conn.execute(
        "SELECT id FROM courses WHERE id = ?",
        (course_id,)
    ).fetchone()

    if course is None:
        conn.close()
        return "Course not found.", 404

    students = conn.execute(
        "SELECT id FROM students"
    ).fetchall()

    try:
        for student in students:
            student_id = student["id"]
            status = request.form.get(f"status_{student_id}")

            if status not in ("Present", "Absent"):
                continue

            conn.execute("""
                INSERT INTO attendance
                    (student_id, course_id, attendance_date, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(student_id, course_id, attendance_date)
                DO UPDATE SET status = excluded.status
            """, (
                student_id,
                course_id,
                attendance_date,
                status
            ))

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return redirect("/attendance")

    
@app.route("/fees")
@login_required
def fees():

    conn = get_db_connection()

    students = conn.execute(
        "SELECT id, name FROM students ORDER BY name"
    ).fetchall()

    courses = conn.execute(
        "SELECT id, course_name, class_name, fee FROM courses ORDER BY course_name"
    ).fetchall()

    fees = conn.execute("""
        SELECT sf.id, sf.total_fee,
               s.name AS student_name,
               c.course_name,
               COALESCE(SUM(fp.amount), 0) AS paid,
               sf.total_fee - COALESCE(SUM(fp.amount), 0) AS balance
        FROM student_fees sf
        JOIN students s ON sf.student_id = s.id
        JOIN courses c ON sf.course_id = c.id
        LEFT JOIN fee_payments fp ON sf.id = fp.fee_id
        GROUP BY sf.id
        ORDER BY s.name, c.course_name
    """).fetchall()

    conn.close()

    return render_template(
        "fees.html",
        students=students,
        courses=courses,
        fees=fees,
        today=date.today().isoformat()
    )

    
@app.route("/assign_fee", methods=["POST"])
@login_required
def assign_fee():

    student_id = request.form.get("student_id")
    course_id = request.form.get("course_id")

    try:
        total_fee = round(float(request.form.get("total_fee", "")), 2)
        if total_fee < 0:
            raise ValueError
    except ValueError:
        return "Enter a valid non-negative fee.", 400

    conn = get_db_connection()

    try:
        student = conn.execute(
            "SELECT id FROM students WHERE id = ?", (student_id,)
        ).fetchone()

        course = conn.execute(
            "SELECT id FROM courses WHERE id = ?", (course_id,)
        ).fetchone()

        if not student or not course:
            return "Please select a valid student and course.", 400

        existing = conn.execute("""
            SELECT id FROM student_fees
            WHERE student_id = ? AND course_id = ?
        """, (student_id, course_id)).fetchone()

        if existing:
            return "A fee record already exists for this student and course. Do not create a duplicate.", 409

        conn.execute("""
            INSERT INTO student_fees
                (student_id, course_id, total_fee)
            VALUES (?, ?, ?)
        """, (student_id, course_id, total_fee))

        conn.commit()

    finally:
        conn.close()

    return redirect("/fees")

    
@app.route("/record_payment", methods=["POST"])
@login_required
def record_payment():

    fee_id = request.form.get("fee_id")
    payment_date = request.form.get("payment_date")
    payment_method = request.form.get("payment_method")
    notes = request.form.get("notes", "").strip()

    try:
        amount = round(float(request.form.get("amount", "")), 2)
        if amount <= 0:
            raise ValueError
        date.fromisoformat(payment_date)
    except (ValueError, TypeError):
        return "Enter a valid amount and payment date.", 400

    if payment_method not in (
        "Cash", "UPI", "Bank Transfer", "Card"
    ):
        return "Invalid payment method.", 400

    conn = get_db_connection()

    try:
        fee = conn.execute("""
            SELECT sf.total_fee,
                   COALESCE(SUM(fp.amount), 0) AS paid
            FROM student_fees sf
            LEFT JOIN fee_payments fp ON sf.id = fp.fee_id
            WHERE sf.id = ?
            GROUP BY sf.id
        """, (fee_id,)).fetchone()

        if fee is None:
            return "Fee record not found.", 404

        balance = round(fee["total_fee"] - fee["paid"], 2)

        if amount > balance:
            return f"Payment exceeds outstanding balance of ₹{balance:.2f}.", 400

        conn.execute("""
            INSERT INTO fee_payments
                (fee_id, amount, payment_date, payment_method, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (fee_id, amount, payment_date, payment_method, notes))

        conn.commit()

    finally:
        conn.close()

    return redirect("/fees")

    
@app.route("/fee_history/<int:fee_id>")
@login_required
def fee_history(fee_id):

    conn = get_db_connection()

    fee = conn.execute("""
        SELECT sf.id, sf.total_fee,
               s.name AS student_name,
               c.course_name,
               COALESCE(SUM(fp.amount), 0) AS paid,
               sf.total_fee - COALESCE(SUM(fp.amount), 0) AS balance
        FROM student_fees sf
        JOIN students s ON sf.student_id = s.id
        JOIN courses c ON sf.course_id = c.id
        LEFT JOIN fee_payments fp ON sf.id = fp.fee_id
        WHERE sf.id = ?
        GROUP BY sf.id
    """, (fee_id,)).fetchone()

    if fee is None:
        conn.close()
        return "Fee record not found.", 404

    payments = conn.execute("""
        SELECT amount, payment_date, payment_method, notes
        FROM fee_payments
        WHERE fee_id = ?
        ORDER BY payment_date DESC, id DESC
    """, (fee_id,)).fetchall()

    conn.close()

    return render_template(
        "fee_history.html",
        fee=fee,
        payments=payments
    )

    
@app.route("/exams")
@login_required
def exams():

    conn = get_db_connection()

    courses = conn.execute("""
        SELECT id, course_name, class_name
        FROM courses
        ORDER BY course_name
    """).fetchall()

    exam_list = conn.execute("""
        SELECT exams.*, courses.course_name
        FROM exams
        JOIN courses ON exams.course_id = courses.id
        ORDER BY exams.exam_date DESC, exams.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "exams.html",
        courses=courses,
        exams=exam_list,
        today=date.today().isoformat()
    )


@app.route("/add_exam", methods=["POST"])
@login_required
def add_exam():

    exam_name = request.form.get("exam_name", "").strip()
    course_id = request.form.get("course_id")
    exam_date = request.form.get("exam_date")

    try:
        max_marks = float(request.form.get("max_marks", ""))
        date.fromisoformat(exam_date)

        if max_marks <= 0:
            raise ValueError

    except (ValueError, TypeError):
        return "Enter a valid exam date and positive maximum marks.", 400

    if not exam_name or not course_id:
        return "Exam name and course are required.", 400

    conn = get_db_connection()

    course = conn.execute(
        "SELECT id FROM courses WHERE id = ?",
        (course_id,)
    ).fetchone()

    if course is None:
        conn.close()
        return "Course not found.", 404

    conn.execute("""
        INSERT INTO exams
            (exam_name, course_id, exam_date, max_marks)
        VALUES (?, ?, ?, ?)
    """, (exam_name, course_id, exam_date, max_marks))

    conn.commit()
    conn.close()

    return redirect("/exams")


    
@app.route("/enter_marks/<int:exam_id>", methods=["GET", "POST"])
@login_required
def enter_marks(exam_id):

    conn = get_db_connection()

    exam = conn.execute("""
        SELECT exams.*, courses.course_name
        FROM exams
        JOIN courses ON exams.course_id = courses.id
        WHERE exams.id = ?
    """, (exam_id,)).fetchone()

    if exam is None:
        conn.close()
        return "Exam not found.", 404

    students = conn.execute(
        "SELECT id, name FROM students ORDER BY name"
    ).fetchall()

    if request.method == "POST":

        try:
            for student in students:
                raw_marks = request.form.get(
                    f"marks_{student['id']}", ""
                ).strip()

                marks = float(raw_marks)

                if marks < 0 or marks > exam["max_marks"]:
                    raise ValueError

                conn.execute("""
                    INSERT INTO exam_marks
                        (exam_id, student_id, marks_obtained)
                    VALUES (?, ?, ?)
                    ON CONFLICT(exam_id, student_id)
                    DO UPDATE SET marks_obtained = excluded.marks_obtained
                """, (exam_id, student["id"], marks))

            conn.commit()

        except (ValueError, TypeError):
            conn.rollback()
            conn.close()
            return "Marks must be numeric and between zero and the maximum marks.", 400

        except Exception:
            conn.rollback()
            conn.close()
            raise

        conn.close()
        return redirect("/exam_results")

    saved = conn.execute("""
        SELECT student_id, marks_obtained
        FROM exam_marks
        WHERE exam_id = ?
    """, (exam_id,)).fetchall()

    saved_marks = {
        row["student_id"]: row["marks_obtained"]
        for row in saved
    }

    conn.close()

    return render_template(
        "enter_marks.html",
        exam=exam,
        students=students,
        saved_marks=saved_marks
    )

    
@app.route("/exam_results")
@login_required
def exam_results():

    conn = get_db_connection()

    results = conn.execute("""
        SELECT students.name AS student_name,
               exams.exam_name,
               courses.course_name,
               exam_marks.marks_obtained,
               exams.max_marks
        FROM exam_marks
        JOIN students ON exam_marks.student_id = students.id
        JOIN exams ON exam_marks.exam_id = exams.id
        JOIN courses ON exams.course_id = courses.id
        ORDER BY exams.exam_date DESC, students.name
    """).fetchall()

    conn.close()

    return render_template(
        "exam_results.html",
        results=results
    )

@app.route("/delete_exam/<int:exam_id>", methods=["POST"])
@login_required
def delete_exam(exam_id):
    conn = get_db_connection()

    try:
        exam = conn.execute(
            "SELECT id FROM exams WHERE id = ?",
            (exam_id,)
        ).fetchone()

        if exam is None:
            flash("Examination not found.", "error")
            return redirect(url_for("exams"))

        # Delete the marks associated with this exam first
        conn.execute(
            "DELETE FROM exam_marks WHERE exam_id = ?",
            (exam_id,)
        )

        # Then delete the examination
        conn.execute(
            "DELETE FROM exams WHERE id = ?",
            (exam_id,)
        )

        conn.commit()
        flash(
            "Examination and its associated marks deleted successfully.",
            "success"
        )

    except sqlite3.Error:
        conn.rollback()
        flash("Could not delete the examination. Please try again.", "error")

    finally:
        conn.close()

    return redirect(url_for("exams"))

@app.route("/login", methods=["GET", "POST"])
def login():

    if "teacher_account_id" in session:
        return redirect(url_for("teacher_dashboard"))
    # Redirect users who are already logged in
    if "admin_id" in session:
        return redirect(url_for("home"))

    if "student_account_id" in session:
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":
        role = request.form.get("role", "admin")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if role not in ("admin", "teacher", "student"):
            flash("Please select a valid login role.", "error")
            return render_template(
                "login.html", selected_role="admin"
            )

        # Admin login
        if role == "admin":
            conn = get_db_connection()
            try:
                account = conn.execute(
                    "SELECT * FROM admins WHERE username = ?",
                    (username,)
                ).fetchone()
            finally:
                conn.close()

            if account and check_password_hash(
                account["password_hash"], password
            ):
                session.clear()
                session["admin_id"] = account["id"]
                session["admin_username"] = account["username"]
                return redirect(url_for("home"))

            flash("Invalid admin username or password.", "error")

        # Student login
        elif role == "student":
            conn = get_db_connection()
            try:
                account = conn.execute("""
                    SELECT id, student_id, username, password_hash
                    FROM student_accounts
                    WHERE username = ?
                """, (username,)).fetchone()
            finally:
                conn.close()

            if account and check_password_hash(
                account["password_hash"], password
            ):
                session.clear()
                session["student_account_id"] = account["id"]
                session["student_id"] = account["student_id"]
                session["student_username"] = account["username"]

                return redirect(url_for("student_dashboard"))

            flash("Invalid student username or password.", "error")

        # Teacher login will be connected in Stage 2
        elif role == "teacher":
            conn = get_db_connection()

            try:
                account = conn.execute("""
                    SELECT
                        ta.id,
                        ta.teacher_id,
                        ta.username,
                        ta.password_hash
                    FROM teacher_accounts ta
                    JOIN teachers t ON t.id = ta.teacher_id
                    WHERE ta.username = ?
                """, (username,)).fetchone()
            finally:
                conn.close()

            password_matches = bool(
                account
                and check_password_hash(account["password_hash"], password)
            )

            app.logger.warning(
                "TEACHER LOGIN DIAGNOSTIC: account_found=%s, password_matches=%s",
                bool(account),
                password_matches
            )

            if account and password_matches:
                session.clear()
                session["teacher_account_id"] = account["id"]
                session["teacher_id"] = account["teacher_id"]
                session["teacher_username"] = account["username"]

                return redirect(url_for("teacher_dashboard"))

            flash("Invalid teacher username or password.", "error")

        return render_template("login.html", selected_role=role)

    selected_role = request.args.get("role", "admin")

    if selected_role not in ("admin", "teacher", "student"):
        selected_role = "admin"

    return render_template(
        "login.html",
        selected_role=selected_role
    )


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/export_students")
@login_required
def export_students():
    conn = get_db_connection()

    search = request.args.get("search", "").strip()
    class_filter = request.args.get("class_filter", "").strip()
    sort_by = request.args.get("sort_by", "name")

    sort_options = {
        "name": "name COLLATE NOCASE",
        "class": "class_name COLLATE NOCASE",
        "id": "id"
    }

    order_column = sort_options.get(
        sort_by, "name COLLATE NOCASE"
    )

    query = """
        SELECT id, name, class_name, phone, email, address
        FROM students
        WHERE 1=1
    """
    params = []

    if search:
        query += """
            AND (
                name LIKE ?
                OR class_name LIKE ?
                OR phone LIKE ?
            )
        """
        value = f"%{search}%"
        params.extend([value, value, value])

    if class_filter:
        query += " AND class_name = ?"
        params.append(class_filter)

    query += f" ORDER BY {order_column}"

    students = conn.execute(query, params).fetchall()
    conn.close()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Student Records"

    headers = [
        "Student ID",
        "Name",
        "Class",
        "Phone",
        "Email",
        "Address"
    ]
    sheet.append(headers)

    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(
            fill_type="solid",
            fgColor="1F4E78"
        )
        cell.alignment = Alignment(horizontal="center")

    for student in students:
        sheet.append([
            student["id"],
            student["name"],
            student["class_name"],
            student["phone"],
            student["email"],
            student["address"]
        ])

    # Adjust column widths
    for column in sheet.columns:
        max_length = max(
            len(str(cell.value or ""))
            for cell in column
        )
        sheet.column_dimensions[
            column[0].column_letter
        ].width = min(max_length + 3, 40)

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="student_records.xlsx",
        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )

@app.route("/enrollments", methods=["GET", "POST"])
@login_required
def enrollments():
    conn = get_db_connection()

    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        course_id = request.form.get("course_id", type=int)
        enrollment_date = request.form.get("enrollment_date", "").strip()

        if not student_id or not course_id or not enrollment_date:
            flash("Please complete all enrollment fields.", "error")
        else:
            student = conn.execute(
                "SELECT id FROM students WHERE id = ?",
                (student_id,)
            ).fetchone()

            course = conn.execute(
                "SELECT id FROM courses WHERE id = ?",
                (course_id,)
            ).fetchone()

            if not student or not course:
                flash("Please select a valid student and course.", "error")
            else:
                try:
                    conn.execute("""
                        INSERT INTO enrollments
                            (student_id, course_id, enrollment_date)
                        VALUES (?, ?, ?)
                    """, (student_id, course_id, enrollment_date))

                    conn.commit()
                    flash("Student enrolled successfully!", "success")

                except sqlite3.IntegrityError:
                    flash(
                        "This student is already enrolled in that course.",
                        "error"
                    )

        conn.close()
        return redirect(url_for("enrollments"))

    students = conn.execute("""
        SELECT id, name, class_name
        FROM students
        ORDER BY name COLLATE NOCASE
    """).fetchall()

    courses = conn.execute("""
        SELECT id, course_name, class_name, fee
        FROM courses
        ORDER BY course_name COLLATE NOCASE
    """).fetchall()

    enrollment_list = conn.execute("""
        SELECT
            e.id,
            e.enrollment_date,
            e.status,
            s.name AS student_name,
            s.class_name AS student_class,
            c.course_name,
            c.class_name AS course_class
        FROM enrollments e
        JOIN students s ON e.student_id = s.id
        JOIN courses c ON e.course_id = c.id
        ORDER BY e.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "enrollments.html",
        students=students,
        courses=courses,
        enrollments=enrollment_list,
        today=date.today().isoformat()
    )

@app.route("/student_accounts", methods=["GET", "POST"])
@login_required
def manage_student_accounts():
    conn = get_db_connection()

    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not student_id or not username or len(password) < 8:
            flash(
                "Select a student, enter a username, "
                "and use a password of at least 8 characters.",
                "error"
            )
        else:
            student = conn.execute(
                "SELECT id FROM students WHERE id = ?",
                (student_id,)
            ).fetchone()

            if not student:
                flash("Please select a valid student.", "error")
            else:
                try:
                    conn.execute("""
                        INSERT INTO student_accounts
                            (student_id, username, password_hash)
                        VALUES (?, ?, ?)
                    """, (
                        student_id,
                        username,
                        generate_password_hash(password)
                    ))

                    conn.commit()
                    flash("Student account created successfully.", "success")

                except sqlite3.IntegrityError:
                    flash(
                        "This student already has an account, "
                        "or the username is already taken.",
                        "error"
                    )

        conn.close()
        return redirect(url_for("manage_student_accounts"))

    students = conn.execute("""
        SELECT s.id, s.name, s.class_name
        FROM students s
        LEFT JOIN student_accounts sa ON sa.student_id = s.id
        WHERE sa.id IS NULL
        ORDER BY s.name COLLATE NOCASE
    """).fetchall()

    accounts = conn.execute("""
        SELECT sa.id, sa.username, s.name, s.class_name
        FROM student_accounts sa
        JOIN students s ON s.id = sa.student_id
        ORDER BY s.name COLLATE NOCASE
    """).fetchall()

    conn.close()

    return render_template(
        "student_accounts.html",
        students=students,
        accounts=accounts
    )


def student_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "student_account_id" not in session:
            return redirect(url_for("student_login"))
        return route_function(*args, **kwargs)
    return wrapper


@app.route("/student_login", methods=["GET", "POST"])
def student_login():
    return redirect(url_for("login", role="student"))

@app.route("/student_dashboard")
@student_required
def student_dashboard():
    student_id = session["student_id"]
    conn = get_db_connection()

    try:
        # 1. Student profile
        student = conn.execute("""
            SELECT id, name, class_name, phone, email
            FROM students
            WHERE id = ?
        """, (student_id,)).fetchone()

        if student is None:
            session.clear()
            flash("Student record not found.", "error")
            return redirect(url_for("student_login"))

        # 2. Active enrolled courses
        courses = conn.execute("""
            SELECT
                c.course_name,
                c.class_name,
                e.enrollment_date,
                e.status
            FROM enrollments e
            JOIN courses c ON c.id = e.course_id
            WHERE e.student_id = ?
              AND e.status = 'Active'
            ORDER BY c.course_name
        """, (student_id,)).fetchall()

        # 3. Attendance summary
        attendance_summary = conn.execute("""
            SELECT
                COUNT(*) AS total_sessions,
                COALESCE(
                    SUM(CASE WHEN status = 'Present'
                             THEN 1 ELSE 0 END), 0
                ) AS present_count,
                COALESCE(
                    SUM(CASE WHEN status = 'Absent'
                             THEN 1 ELSE 0 END), 0
                ) AS absent_count
            FROM attendance
            WHERE student_id = ?
        """, (student_id,)).fetchone()

        total_sessions = attendance_summary["total_sessions"]
        present_count = attendance_summary["present_count"]
        absent_count = attendance_summary["absent_count"]

        # Avoid division by zero
        attendance_percentage = (
            round(present_count * 100.0 / total_sessions, 2)
            if total_sessions > 0 else 0
        )

        # 4. Individual attendance records
        attendance_records = conn.execute("""
            SELECT
                a.attendance_date,
                a.status,
                c.course_name
            FROM attendance a
            JOIN courses c ON c.id = a.course_id
            WHERE a.student_id = ?
            ORDER BY a.attendance_date DESC, c.course_name
        """, (student_id,)).fetchall()

        # 5. Examination results
        # Percentage remains NULL if maximum marks are zero/missing
        # or marks obtained are missing.
        exam_results = conn.execute("""
            SELECT
                e.exam_name,
                e.exam_date,
                e.max_marks,
                em.marks_obtained,
                c.course_name,
                CASE
                    WHEN e.max_marks IS NOT NULL
                         AND e.max_marks > 0
                         AND em.marks_obtained IS NOT NULL
                    THEN ROUND(
                        em.marks_obtained * 100.0 / e.max_marks, 2
                    )
                    ELSE NULL
                END AS percentage
            FROM exam_marks em
            JOIN exams e ON e.id = em.exam_id
            JOIN courses c ON c.id = e.course_id
            WHERE em.student_id = ?
            ORDER BY e.exam_date DESC, e.exam_name
        """, (student_id,)).fetchall()

        # 6. Fee details
        fee_records = conn.execute("""
            SELECT
                sf.id,
                COALESCE(sf.total_fee, 0) AS total_fee,
                c.course_name,
                COALESCE(SUM(fp.amount), 0) AS paid,
                MAX(
                    COALESCE(sf.total_fee, 0)
                    - COALESCE(SUM(fp.amount), 0),
                    0
                ) AS balance
            FROM student_fees sf
            JOIN courses c ON c.id = sf.course_id
            LEFT JOIN fee_payments fp ON fp.fee_id = sf.id
            WHERE sf.student_id = ?
            GROUP BY sf.id
            ORDER BY c.course_name
        """, (student_id,)).fetchall()

        # 7. Overall fee totals
        total_fees = sum(
            float(fee["total_fee"]) for fee in fee_records
        )
        total_paid = sum(
            float(fee["paid"]) for fee in fee_records
        )
        total_balance = sum(
            float(fee["balance"]) for fee in fee_records
        )

        # 8. Display the dashboard
        return render_template(
            "student_dashboard.html",
            student=student,
            courses=courses,
            attendance_summary=attendance_summary,
            attendance_percentage=attendance_percentage,
            attendance_records=attendance_records,
            exam_results=exam_results,
            fee_records=fee_records,
            total_fees=total_fees,
            total_paid=total_paid,
            total_balance=total_balance
        )

    finally:
        conn.close()

@app.route("/student_logout", methods=["POST"])
def student_logout():
    session.clear()
    return redirect(url_for("student_login"))


@app.route("/check_course/<int:course_id>")
@login_required
def check_course(course_id):
    conn = get_db_connection()

    try:
        course = conn.execute(
            "SELECT * FROM courses WHERE id = ?",
            (course_id,)
        ).fetchone()

        if course is None:
            return "Course not found."

        details = {
            "course": dict(course),
            "enrollments": conn.execute(
                "SELECT * FROM enrollments WHERE course_id = ?",
                (course_id,)
            ).fetchall(),
            "attendance": conn.execute(
                "SELECT * FROM attendance WHERE course_id = ?",
                (course_id,)
            ).fetchall(),
            "fees": conn.execute(
                "SELECT * FROM student_fees WHERE course_id = ?",
                (course_id,)
            ).fetchall(),
            "exams": conn.execute(
                "SELECT * FROM exams WHERE course_id = ?",
                (course_id,)
            ).fetchall()
        }

        output = []

        for section, records in details.items():
            output.append(f"\n{section.upper()}:")

            if section == "course":
                output.append(str(records))
            else:
                for record in records:
                    output.append(str(dict(record)))

        return "<pre>" + "\n".join(output) + "</pre>"

    finally:
        conn.close()

@app.route("/list_course_ids")
@login_required
def list_course_ids():
    conn = get_db_connection()

    try:
        courses = conn.execute("""
            SELECT id, course_name, class_name, subject
            FROM courses
            ORDER BY id
        """).fetchall()

        output = ["COURSE ID | NAME | CLASS | SUBJECT"]

        for course in courses:
            output.append(
                f"{course['id']} | {course['course_name']} | "
                f"{course['class_name']} | {course['subject']}"
            )

        return "<pre>" + "\n".join(output) + "</pre>"

    finally:
        conn.close()


@app.route("/teacher_dashboard")
@teacher_required
def teacher_dashboard():
    teacher_id = session["teacher_id"]
    conn = get_db_connection()

    try:
        teacher = conn.execute("""
            SELECT id, name, subject, phone, email
            FROM teachers
            WHERE id = ?
        """, (teacher_id,)).fetchone()

        if teacher is None:
            session.clear()
            flash("Teacher record not found.", "error")
            return redirect(url_for("login", role="teacher"))

        courses = conn.execute("""
            SELECT id, course_name, class_name, subject, fee
            FROM courses
            WHERE teacher_id = ?
            ORDER BY course_name
        """, (teacher_id,)).fetchall()

        timetable_entries = conn.execute("""
            SELECT
                tt.id,
                tt.day_of_week,
                tt.start_time,
                tt.end_time,
                tt.room,
                c.course_name,
                c.class_name,
                c.subject
            FROM timetable tt
            JOIN courses c ON c.id = tt.course_id
            WHERE c.teacher_id = ?
            ORDER BY
                CASE tt.day_of_week
                    WHEN 'Monday' THEN 1
                    WHEN 'Tuesday' THEN 2
                    WHEN 'Wednesday' THEN 3
                    WHEN 'Thursday' THEN 4
                    WHEN 'Friday' THEN 5
                    WHEN 'Saturday' THEN 6
                    WHEN 'Sunday' THEN 7
                END,
                tt.start_time
        """, (teacher_id,)).fetchall()

        
        attendance_summary = conn.execute("""
            SELECT
                c.id AS course_id,
                c.course_name,
                c.class_name,
                COUNT(a.id) AS total_marked,
                SUM(
                    CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END
                ) AS present_count,
                SUM(
                    CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END
                ) AS absent_count
            FROM courses c
            LEFT JOIN attendance a
                ON a.course_id = c.id
            WHERE c.teacher_id = ?
            GROUP BY c.id, c.course_name, c.class_name
            ORDER BY c.course_name
        """, (teacher_id,)).fetchall()


        return render_template(
            "teacher_dashboard.html",
            teacher=teacher,
            courses=courses,
            timetable_entries=timetable_entries,
            attendance_summary=attendance_summary
        )

    finally:
        conn.close()

@app.route("/teacher_logout", methods=["POST"])
@teacher_required
def teacher_logout():
    session.clear()
    flash("You have logged out successfully.", "success")
    return redirect(url_for("login", role="teacher"))


@app.route("/teacher_accounts", methods=["GET", "POST"])
@login_required
def manage_teacher_accounts():
    conn = get_db_connection()

    try:
        if request.method == "POST":
            teacher_id = request.form.get("teacher_id", "").strip()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if not teacher_id.isdigit() or not username or not password:
                flash("Please complete all fields.", "error")
                return redirect(url_for("manage_teacher_accounts"))

            if len(password) < 8:
                flash("Password must contain at least 8 characters.", "error")
                return redirect(url_for("manage_teacher_accounts"))

            teacher = conn.execute(
                "SELECT id FROM teachers WHERE id = ?",
                (int(teacher_id),)
            ).fetchone()

            if teacher is None:
                flash("Please select a valid teacher.", "error")
                return redirect(url_for("manage_teacher_accounts"))

            existing_account = conn.execute("""
                SELECT id
                FROM teacher_accounts
                WHERE teacher_id = ? OR username = ?
            """, (int(teacher_id), username)).fetchone()

            if existing_account:
                flash(
                    "This teacher already has an account, "
                    "or the username is already in use.",
                    "error"
                )
                return redirect(url_for("manage_teacher_accounts"))

            conn.execute("""
                INSERT INTO teacher_accounts
                    (teacher_id, username, password_hash)
                VALUES (?, ?, ?)
            """, (
                int(teacher_id),
                username,
                generate_password_hash(password)
            ))

            conn.commit()
            flash("Teacher login account created successfully.", "success")
            return redirect(url_for("manage_teacher_accounts"))

        teachers = conn.execute("""
            SELECT t.id, t.name, t.subject
            FROM teachers t
            LEFT JOIN teacher_accounts ta ON ta.teacher_id = t.id
            WHERE ta.id IS NULL
            ORDER BY t.name
        """).fetchall()

        accounts = conn.execute("""
            SELECT
                ta.id,
                ta.username,
                t.name AS teacher_name,
                t.subject
            FROM teacher_accounts ta
            JOIN teachers t ON t.id = ta.teacher_id
            ORDER BY t.name
        """).fetchall()

        return render_template(
            "teacher_accounts.html",
            teachers=teachers,
            accounts=accounts
        )

    except sqlite3.IntegrityError:
        conn.rollback()
        flash(
            "The username or teacher account already exists.",
            "error"
        )
        return redirect(url_for("manage_teacher_accounts"))

    except sqlite3.Error:
        conn.rollback()
        app.logger.exception("Teacher account management failed")
        flash("A database error occurred.", "error")
        return redirect(url_for("manage_teacher_accounts"))

    finally:
        conn.close()


@app.route("/timetable", methods=["GET", "POST"])
@login_required
def manage_timetable():
    conn = get_db_connection()

    try:
        if request.method == "POST":
            course_id = request.form.get("course_id", "").strip()
            day_of_week = request.form.get("day_of_week", "").strip()
            start_time = request.form.get("start_time", "").strip()
            end_time = request.form.get("end_time", "").strip()
            room = request.form.get("room", "").strip()

            valid_days = {
                "Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday"
            }

            if (
                not course_id.isdigit()
                or day_of_week not in valid_days
                or not start_time
                or not end_time
            ):
                flash("Please complete all required fields.", "error")
                return redirect(url_for("manage_timetable"))

            if start_time >= end_time:
                flash("End time must be later than start time.", "error")
                return redirect(url_for("manage_timetable"))

            course = conn.execute(
                "SELECT id FROM courses WHERE id = ?",
                (int(course_id),)
            ).fetchone()

            if course is None:
                flash("Please select a valid course.", "error")
                return redirect(url_for("manage_timetable"))

            try:
                conn.execute("""
                    INSERT INTO timetable
                        (course_id, day_of_week, start_time, end_time, room)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    int(course_id),
                    day_of_week,
                    start_time,
                    end_time,
                    room or None
                ))
                conn.commit()
                flash("Timetable entry added successfully.", "success")

            except sqlite3.IntegrityError:
                conn.rollback()
                flash(
                    "This course already has a timetable entry "
                    "at that start time on the selected day, "
                    "or the time range is invalid.",
                    "error"
                )

            return redirect(url_for("manage_timetable"))

        courses = conn.execute("""
            SELECT
                c.id,
                c.course_name,
                c.class_name,
                c.subject,
                t.name AS teacher_name
            FROM courses c
            LEFT JOIN teachers t ON t.id = c.teacher_id
            ORDER BY c.course_name
        """).fetchall()

        timetable_entries = conn.execute("""
            SELECT
                tt.id,
                tt.day_of_week,
                tt.start_time,
                tt.end_time,
                tt.room,
                c.course_name,
                c.class_name,
                c.subject,
                t.name AS teacher_name
            FROM timetable tt
            JOIN courses c ON c.id = tt.course_id
            LEFT JOIN teachers t ON t.id = c.teacher_id
            ORDER BY
                CASE tt.day_of_week
                    WHEN 'Monday' THEN 1
                    WHEN 'Tuesday' THEN 2
                    WHEN 'Wednesday' THEN 3
                    WHEN 'Thursday' THEN 4
                    WHEN 'Friday' THEN 5
                    WHEN 'Saturday' THEN 6
                    WHEN 'Sunday' THEN 7
                END,
                tt.start_time,
                c.course_name
        """).fetchall()

        return render_template(
            "timetable.html",
            courses=courses,
            timetable_entries=timetable_entries
        )

    except sqlite3.Error:
        conn.rollback()
        app.logger.exception("Timetable management failed")
        flash("A database error occurred while loading the timetable.", "error")
        return redirect(url_for("home"))

    finally:
        conn.close()


@app.route("/timetable/delete/<int:entry_id>", methods=["POST"])
@login_required
def delete_timetable_entry(entry_id):
    conn = get_db_connection()

    try:
        cursor = conn.execute(
            "DELETE FROM timetable WHERE id = ?",
            (entry_id,)
        )
        conn.commit()

        if cursor.rowcount:
            flash("Timetable entry deleted successfully.", "success")
        else:
            flash("Timetable entry was not found.", "error")

    except sqlite3.Error:
        conn.rollback()
        app.logger.exception("Timetable deletion failed")
        flash("Could not delete the timetable entry.", "error")

    finally:
        conn.close()

    return redirect(url_for("manage_timetable"))


@app.route("/teacher_attendance", methods=["GET", "POST"])
@teacher_required
def teacher_attendance():
    app.logger.warning(
        "TEACHER ATTENDANCE ROUTE REACHED: teacher_id=%s",
        session.get("teacher_id")
    )
    teacher_id = session["teacher_id"]
    course_id = request.args.get("course_id", "").strip()
    attendance_date = request.args.get(
        "attendance_date", date.today().isoformat()
    )

    # Validate the date before querying the database.
    try:
        date.fromisoformat(attendance_date)
    except ValueError:
        flash("Please select a valid attendance date.", "error")
        return redirect(url_for("teacher_attendance"))

    conn = get_db_connection()

    try:
        # Only show courses assigned to this teacher.
        courses = conn.execute("""
            SELECT id, course_name, class_name, subject
            FROM courses
            WHERE teacher_id = ?
            ORDER BY course_name
        """, (teacher_id,)).fetchall()

        if request.method == "POST":
            course_id = request.form.get("course_id", "").strip()
            attendance_date = request.form.get(
                "attendance_date", ""
            ).strip()

            try:
                date.fromisoformat(attendance_date)
            except ValueError:
                flash("Please select a valid attendance date.", "error")
                return redirect(url_for("teacher_attendance"))

            if not course_id.isdigit():
                flash("Please select a valid course.", "error")
                return redirect(url_for("teacher_attendance"))

            selected_course = conn.execute("""
                SELECT id
                FROM courses
                WHERE id = ? AND teacher_id = ?
            """, (int(course_id), teacher_id)).fetchone()

            if selected_course is None:
                flash(
                    "You are not authorized to mark attendance for this course.",
                    "error"
                )
                return redirect(url_for("teacher_attendance"))

            active_students = conn.execute("""
                SELECT s.id
                FROM enrollments e
                JOIN students s ON s.id = e.student_id
                WHERE e.course_id = ?
                  AND e.status = 'Active'
            """, (int(course_id),)).fetchall()

            allowed_student_ids = {
                student["id"] for student in active_students
            }

            submitted_ids = request.form.getlist("student_id")
            submitted_statuses = request.form.getlist("status")

            if (
                not allowed_student_ids
                or len(submitted_ids) != len(allowed_student_ids)
                or len(set(submitted_ids)) != len(submitted_ids)
                or set(submitted_ids) != {
                    str(student_id)
                    for student_id in allowed_student_ids
                }
                or len(submitted_statuses) != len(submitted_ids)
                or any(
                    status not in {"Present", "Absent"}
                    for status in submitted_statuses
                )
            ):
                flash(
                    "Attendance submission is incomplete or invalid. "
                    "Reload the student list and try again.",
                    "error"
                )
                return redirect(url_for(
                    "teacher_attendance",
                    course_id=course_id,
                    attendance_date=attendance_date
                ))

            try:
                for student_id, status in zip(
                    submitted_ids, submitted_statuses
                ):
                    conn.execute("""
                        INSERT INTO attendance
                            (student_id, course_id, attendance_date, status)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(
                            student_id, course_id, attendance_date
                        )
                        DO UPDATE SET status = excluded.status
                    """, (
                        int(student_id),
                        int(course_id),
                        attendance_date,
                        status
                    ))

                conn.commit()
                flash("Attendance saved successfully.", "success")

            except sqlite3.Error:
                conn.rollback()
                app.logger.exception("Attendance save failed")
                flash("Could not save attendance. Please try again.", "error")

            return redirect(url_for(
                "teacher_attendance",
                course_id=course_id,
                attendance_date=attendance_date
            ))


        students = []
        selected_course = None

        if course_id:
            if not course_id.isdigit():
                flash("Invalid course selection.", "error")
                return redirect(url_for("teacher_attendance"))

            selected_course = conn.execute("""
                SELECT id, course_name, class_name, subject
                FROM courses
                WHERE id = ? AND teacher_id = ?
            """, (int(course_id), teacher_id)).fetchone()

            if selected_course is None:
                flash(
                    "You are not authorized to access this course.",
                    "error"
                )
                return redirect(url_for("teacher_attendance"))

            # Only actively enrolled students in the selected course.
            students = conn.execute("""
                SELECT
                    s.id,
                    s.name,
                    s.phone,
                    a.status AS attendance_status
                FROM enrollments e
                JOIN students s ON s.id = e.student_id
                LEFT JOIN attendance a
                    ON a.student_id = e.student_id
                    AND a.course_id = e.course_id
                    AND a.attendance_date = ?
                WHERE e.course_id = ?
                    AND e.status = 'Active'
                ORDER BY s.name
            """, (
                attendance_date,
                int(course_id)
            )).fetchall()

        return render_template(
            "teacher_attendance.html",
            courses=courses,
            students=students,
            selected_course=selected_course,
            selected_course_id=course_id,
            attendance_date=attendance_date
        )

    finally:
        conn.close()


@app.route("/teacher_attendance_history", methods=["GET"])
@teacher_required
def teacher_attendance_history():
    teacher_id = session["teacher_id"]
    course_id = request.args.get("course_id", "").strip()
    attendance_date = request.args.get(
        "attendance_date", date.today().isoformat()
    )

    try:
        date.fromisoformat(attendance_date)
    except ValueError:
        flash("Please select a valid attendance date.", "error")
        return redirect(url_for("teacher_attendance_history"))

    conn = get_db_connection()

    try:
        # Only courses assigned to the logged-in teacher.
        courses = conn.execute("""
            SELECT id, course_name, class_name, subject
            FROM courses
            WHERE teacher_id = ?
            ORDER BY course_name
        """, (teacher_id,)).fetchall()

        students = []
        selected_course = None

        if course_id:
            if not course_id.isdigit():
                flash("Invalid course selection.", "error")
                return redirect(url_for("teacher_attendance_history"))

            selected_course = conn.execute("""
                SELECT id, course_name, class_name, subject
                FROM courses
                WHERE id = ? AND teacher_id = ?
            """, (int(course_id), teacher_id)).fetchone()

            if selected_course is None:
                flash(
                    "You are not authorized to view this course.",
                    "error"
                )
                return redirect(url_for("teacher_attendance_history"))

            
            students = conn.execute("""
                SELECT
                    s.id AS student_id,
                    s.name AS student_name,
                    s.phone,
                    a.status AS attendance_status,

                    (
                        SELECT COUNT(*)
                        FROM attendance ah
                        WHERE ah.student_id = e.student_id
                          AND ah.course_id = e.course_id
                    ) AS total_recorded,

                    (
                        SELECT COUNT(*)
                        FROM attendance ah
                        WHERE ah.student_id = e.student_id
                          AND ah.course_id = e.course_id
                          AND ah.status = 'Present'
                    ) AS present_count,

                    (
                        SELECT COUNT(*)
                        FROM attendance ah
                        WHERE ah.student_id = e.student_id
                          AND ah.course_id = e.course_id
                          AND ah.status = 'Absent'
                    ) AS absent_count,

                    CASE
                        WHEN (
                            SELECT COUNT(*)
                            FROM attendance ah
                            WHERE ah.student_id = e.student_id
                              AND ah.course_id = e.course_id
                        ) = 0 THEN 0
                        ELSE ROUND(
                            100.0 * (
                                SELECT COUNT(*)
                                FROM attendance ah
                                WHERE ah.student_id = e.student_id
                                  AND ah.course_id = e.course_id
                                  AND ah.status = 'Present'
                            ) / (
                                SELECT COUNT(*)
                                FROM attendance ah
                                WHERE ah.student_id = e.student_id
                                  AND ah.course_id = e.course_id
                            ),
                            1
                        )
                    END AS attendance_percentage

                FROM enrollments e
                JOIN students s ON s.id = e.student_id

                LEFT JOIN attendance a
                    ON a.student_id = e.student_id
                    AND a.course_id = e.course_id
                    AND a.attendance_date = ?

                WHERE e.course_id = ?
                  AND e.status = 'Active'

                ORDER BY s.name
            """, (
                attendance_date,
                int(course_id)
            )).fetchall()

        return render_template(
            "teacher_attendance_history.html",
            courses=courses,
            students=students,
            selected_course=selected_course,
            selected_course_id=course_id,
            attendance_date=attendance_date
        )

    finally:
        conn.close()




if __name__ == "__main__":
    init_db()
    app.run(debug=True)