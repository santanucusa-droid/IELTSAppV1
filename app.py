import os, sqlite3, json, hashlib, secrets, time
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, abort
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DB = os.path.join(os.path.dirname(__file__), 'ielts.db')

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            audio_file TEXT NOT NULL,
            time_limit INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            order_no INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            options TEXT NOT NULL,
            correct_option INTEGER NOT NULL,
            FOREIGN KEY(test_id) REFERENCES tests(id)
        );
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            test_id INTEGER NOT NULL,
            answers TEXT,
            score INTEGER,
            total INTEGER,
            started_at INTEGER,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'submitted',
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(test_id) REFERENCES tests(id)
        );
    ''')
    # default admin
    c.execute("INSERT OR IGNORE INTO users (email, password, is_admin) VALUES (?, ?, 1)",
              ('admin@ielts.com', hash_pw('admin123')))
    conn.commit()
    conn.close()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            abort(403)
        return f(*args, **kwargs)
    return decorated

# ─── AUTH ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('user_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        pw = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE email=? AND password=?', (email, hash_pw(pw))).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['is_admin'] = bool(user['is_admin'])
            return redirect(url_for('index'))
        error = 'Invalid email or password.'
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        pw = request.form['password']
        if len(pw) < 6:
            error = 'Password must be at least 6 characters.'
        else:
            try:
                conn = get_db()
                cursor = conn.execute('INSERT INTO users (email, password) VALUES (?, ?)', (email, hash_pw(pw)))
                user_id = cursor.lastrowid
                conn.commit()
                # Auto-login after registration
                user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
                conn.close()
                session['user_id'] = user['id']
                session['email'] = user['email']
                session['is_admin'] = bool(user['is_admin'])
                return redirect(url_for('user_dashboard'))
            except:
                error = 'Email already registered.'
    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── USER ─────────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def user_dashboard():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    conn = get_db()
    tests = conn.execute('SELECT * FROM tests ORDER BY created_at DESC').fetchall()
    # get attempt info per test for this user
    attempts = conn.execute(
        'SELECT test_id, status, score, total FROM attempts WHERE user_id=?', (session['user_id'],)
    ).fetchall()
    conn.close()
    attempted = {a['test_id']: a for a in attempts}
    return render_template('user_dashboard.html', tests=tests, attempted=attempted)

@app.route('/test/<int:test_id>')
@login_required
def take_test(test_id):
    if session.get('is_admin'):
        abort(403)
    conn = get_db()
    test = conn.execute('SELECT * FROM tests WHERE id=?', (test_id,)).fetchone()
    if not test:
        abort(404)
    # check if already attempted
    existing = conn.execute(
        'SELECT * FROM attempts WHERE user_id=? AND test_id=?', (session['user_id'], test_id)
    ).fetchone()
    if existing:
        conn.close()
        return redirect(url_for('result', attempt_id=existing['id']))
    questions = conn.execute(
        'SELECT * FROM questions WHERE test_id=? ORDER BY order_no', (test_id,)
    ).fetchall()
    conn.close()
    questions_data = [{'id': q['id'], 'text': q['question_text'], 'options': json.loads(q['options'])} for q in questions]
    return render_template('take_test.html', test=test, questions=questions_data)

@app.route('/test/<int:test_id>/submit', methods=['POST'])
@login_required
def submit_test(test_id):
    if session.get('is_admin'):
        abort(403)
    conn = get_db()
    # prevent double submit
    existing = conn.execute(
        'SELECT * FROM attempts WHERE user_id=? AND test_id=?', (session['user_id'], test_id)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'redirect': url_for('result', attempt_id=existing['id'])})

    data = request.json
    answers = data.get('answers', {})
    started_at = data.get('started_at', 0)

    questions = conn.execute('SELECT * FROM questions WHERE test_id=?', (test_id,)).fetchall()
    score = 0
    for q in questions:
        user_ans = answers.get(str(q['id']))
        if user_ans is not None and int(user_ans) == q['correct_option']:
            score += 1

    cursor = conn.execute(
        'INSERT INTO attempts (user_id, test_id, answers, score, total, started_at) VALUES (?, ?, ?, ?, ?, ?)',
        (session['user_id'], test_id, json.dumps(answers), score, len(questions), started_at)
    )
    attempt_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'redirect': url_for('result', attempt_id=attempt_id)})

@app.route('/result/<int:attempt_id>')
@login_required
def result(attempt_id):
    conn = get_db()
    attempt = conn.execute('SELECT * FROM attempts WHERE id=?', (attempt_id,)).fetchone()
    if not attempt or (attempt['user_id'] != session['user_id'] and not session.get('is_admin')):
        abort(403)
    test = conn.execute('SELECT * FROM tests WHERE id=?', (attempt['test_id'],)).fetchone()
    questions = conn.execute('SELECT * FROM questions WHERE test_id=? ORDER BY order_no', (attempt['test_id'],)).fetchall()
    answers = json.loads(attempt['answers'] or '{}')
    conn.close()

    q_results = []
    for q in questions:
        opts = json.loads(q['options'])
        user_ans = answers.get(str(q['id']))
        q_results.append({
            'text': q['question_text'],
            'options': opts,
            'correct': q['correct_option'],
            'user': int(user_ans) if user_ans is not None else None
        })

    return render_template('result.html', attempt=attempt, test=test, q_results=q_results)

# ─── ADMIN ────────────────────────────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    tests = conn.execute('SELECT * FROM tests ORDER BY created_at DESC').fetchall()
    users = conn.execute('SELECT * FROM users WHERE is_admin=0 ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin_dashboard.html', tests=tests, users=users)

@app.route('/admin/test/new', methods=['GET', 'POST'])
@admin_required
def admin_new_test():
    error = None
    if request.method == 'POST':
        title = request.form['title'].strip()
        time_limit = int(request.form['time_limit'])
        audio = request.files.get('audio')
        if not title or not audio:
            error = 'Title and audio file are required.'
        else:
            filename = secure_filename(audio.filename)
            audio.save(os.path.join(UPLOAD_FOLDER, filename))
            conn = get_db()
            cursor = conn.execute('INSERT INTO tests (title, audio_file, time_limit) VALUES (?, ?, ?)',
                                  (title, filename, time_limit))
            test_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return redirect(url_for('admin_edit_test', test_id=test_id))
    return render_template('admin_new_test.html', error=error)

@app.route('/admin/test/<int:test_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_test(test_id):
    conn = get_db()
    test = conn.execute('SELECT * FROM tests WHERE id=?', (test_id,)).fetchone()
    if not test:
        abort(404)

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_question':
            qtext = request.form['question_text'].strip()
            opts = [request.form.get(f'opt{i}', '').strip() for i in range(4)]
            correct = int(request.form['correct'])
            order_no = conn.execute('SELECT COALESCE(MAX(order_no),0)+1 FROM questions WHERE test_id=?', (test_id,)).fetchone()[0]
            conn.execute('INSERT INTO questions (test_id, order_no, question_text, options, correct_option) VALUES (?,?,?,?,?)',
                         (test_id, order_no, qtext, json.dumps(opts), correct))
            conn.commit()
        elif action == 'bulk_import':
            bulk_text = request.form.get('bulk_text', '').strip()
            if bulk_text:
                questions_parsed = parse_bulk_questions(bulk_text)
                order_no = conn.execute('SELECT COALESCE(MAX(order_no),0)+1 FROM questions WHERE test_id=?', (test_id,)).fetchone()[0]
                for q in questions_parsed:
                    conn.execute('INSERT INTO questions (test_id, order_no, question_text, options, correct_option) VALUES (?,?,?,?,?)',
                                 (test_id, order_no, q['text'], json.dumps(q['options']), q['correct']))
                    order_no += 1
                conn.commit()
        elif action == 'delete_question':
            qid = request.form['question_id']
            conn.execute('DELETE FROM questions WHERE id=? AND test_id=?', (qid, test_id))
            conn.commit()

    questions = conn.execute('SELECT * FROM questions WHERE test_id=? ORDER BY order_no', (test_id,)).fetchall()
    conn.close()
    return render_template('admin_edit_test.html', test=test, questions=questions)

def parse_bulk_questions(text):
    """
    Parse bulk questions in format:
    1. Question text?
    A) Option 1
    B) Option 2
    C) Option 3*
    D) Option 4
    
    The * marks the correct answer
    """
    import re
    questions = []
    lines = text.strip().split('\n')
    current_q = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check if it's a question (starts with number and dot)
        q_match = re.match(r'^\d+\.\s*(.+)$', line)
        if q_match:
            if current_q and len(current_q['options']) == 4:
                questions.append(current_q)
            current_q = {
                'text': q_match.group(1).strip(),
                'options': [],
                'correct': -1
            }
        # Check if it's an option (A), B), C), D))
        elif current_q is not None:
            opt_match = re.match(r'^[A-Da-d]\)\s*(.+)$', line)
            if opt_match:
                opt_text = opt_match.group(1).strip()
                # Check if this is the correct answer (marked with *)
                if opt_text.endswith('*'):
                    opt_text = opt_text[:-1].strip()
                    current_q['correct'] = len(current_q['options'])
                current_q['options'].append(opt_text)
    
    # Add the last question
    if current_q and len(current_q['options']) == 4 and current_q['correct'] >= 0:
        questions.append(current_q)
    
    return questions

@app.route('/admin/test/<int:test_id>/delete', methods=['POST'])
@admin_required
def admin_delete_test(test_id):
    conn = get_db()
    conn.execute('DELETE FROM questions WHERE test_id=?', (test_id,))
    conn.execute('DELETE FROM attempts WHERE test_id=?', (test_id,))
    conn.execute('DELETE FROM tests WHERE id=?', (test_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/users')
@admin_required
def admin_users():
    conn = get_db()
    users = conn.execute('SELECT * FROM users WHERE is_admin=0 ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin_users.html', users=users)

@app.route('/admin/user/<int:user_id>')
@admin_required
def admin_user_detail(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    attempts = conn.execute('''
        SELECT a.*, t.title, t.time_limit FROM attempts a
        JOIN tests t ON t.id=a.test_id
        WHERE a.user_id=? ORDER BY a.submitted_at DESC
    ''', (user_id,)).fetchall()
    conn.close()
    return render_template('admin_user_detail.html', user=user, attempts=attempts)

@app.route('/static/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.template_filter('from_json')
def from_json_filter(value):
    return json.loads(value)

init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
