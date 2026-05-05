from flask import Flask, request, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import sqlite3
import secrets
import logging
import re
import os

app = Flask(__name__, static_folder='sky')
app.secret_key = os.environ.get('SECRET_KEY', 'qf-admin-dev-secret-change-in-prod')

DB_PATH = 'portal.db'

logging.basicConfig(level=logging.INFO)


# ─── database helpers ──────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name    TEXT    NOT NULL,
            email        TEXT    UNIQUE NOT NULL,
            password_hash TEXT   NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS password_resets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id   INTEGER NOT NULL,
            token      TEXT    UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used       INTEGER DEFAULT 0,
            FOREIGN KEY (admin_id) REFERENCES admins(id)
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS opportunities (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id            INTEGER NOT NULL,
            name                TEXT NOT NULL,
            duration            TEXT NOT NULL,
            start_date          TEXT NOT NULL,
            description         TEXT NOT NULL,
            skills              TEXT NOT NULL,
            category            TEXT NOT NULL,
            future_opportunities TEXT NOT NULL,
            max_applicants      INTEGER,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (admin_id) REFERENCES admins(id)
        )
    ''')

    conn.commit()
    conn.close()


def opp_to_dict(row):
    skills = [s.strip() for s in row['skills'].split(',')] if row['skills'] else []
    return {
        'id': row['id'],
        'name': row['name'],
        'duration': row['duration'],
        'start_date': row['start_date'],
        'description': row['description'],
        'skills': skills,
        'category': row['category'],
        'future_opportunities': row['future_opportunities'],
        'max_applicants': row['max_applicants'],
    }


# ─── auth decorator ────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'admin_id' not in session:
            return jsonify({'error': 'Please log in to continue'}), 401
        return f(*args, **kwargs)
    return wrapper


# ─── static file routes ────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('sky', 'admin.html')

@app.route('/admin.css')
def serve_css():
    return send_from_directory('sky', 'admin.css')

@app.route('/admin.js')
def serve_js():
    return send_from_directory('sky', 'admin.js')


# ─── auth routes ───────────────────────────────────────────────────────────────

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json() or {}
    full_name = data.get('full_name', '').strip()
    email     = data.get('email', '').strip().lower()
    password  = data.get('password', '')
    confirm   = data.get('confirm_password', '')

    if not all([full_name, email, password, confirm]):
        return jsonify({'error': 'All fields are required'}), 400

    if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        return jsonify({'error': 'Please enter a valid email address'}), 400

    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    if password != confirm:
        return jsonify({'error': 'Passwords do not match'}), 400

    conn = get_db()
    existing = conn.execute('SELECT id FROM admins WHERE email = ?', (email,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'An account with this email already exists'}), 409

    conn.execute(
        'INSERT INTO admins (full_name, email, password_hash) VALUES (?, ?, ?)',
        (full_name, email, generate_password_hash(password))
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Account created successfully'}), 201


@app.route('/api/login', methods=['POST'])
def login():
    data        = request.get_json() or {}
    email       = data.get('email', '').strip().lower()
    password    = data.get('password', '')
    remember_me = data.get('remember_me', False)

    if not email or not password:
        return jsonify({'error': 'Invalid email or password'}), 401

    conn  = get_db()
    admin = conn.execute('SELECT * FROM admins WHERE email = ?', (email,)).fetchone()
    conn.close()

    if not admin or not check_password_hash(admin['password_hash'], password):
        return jsonify({'error': 'Invalid email or password'}), 401

    session['admin_id']    = admin['id']
    session['admin_email'] = admin['email']
    session['admin_name']  = admin['full_name']

    if remember_me:
        session.permanent = True
        app.permanent_session_lifetime = timedelta(days=30)
    else:
        session.permanent = False

    return jsonify({
        'message': 'Login successful',
        'email': admin['email'],
        'name': admin['full_name'],
    }), 200


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Signed out'}), 200


@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    if 'admin_id' in session:
        return jsonify({
            'authenticated': True,
            'email': session.get('admin_email'),
            'name': session.get('admin_name'),
        }), 200
    return jsonify({'authenticated': False}), 200


@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    data  = request.get_json() or {}
    email = data.get('email', '').strip().lower()

    conn  = get_db()
    admin = conn.execute('SELECT id FROM admins WHERE email = ?', (email,)).fetchone()

    if admin:
        token      = secrets.token_urlsafe(40)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        conn.execute(
            'INSERT INTO password_resets (admin_id, token, expires_at) VALUES (?, ?, ?)',
            (admin['id'], token, expires_at.isoformat())
        )
        conn.commit()
        # in production this would be emailed — log it for now
        app.logger.info('Password reset link: /api/reset-password/%s', token)

    conn.close()
    # always return the same message so we don't leak whether the email exists
    return jsonify({'message': 'If that email is registered you\'ll receive a reset link shortly'}), 200


@app.route('/api/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn  = get_db()
    reset = conn.execute(
        'SELECT * FROM password_resets WHERE token = ? AND used = 0', (token,)
    ).fetchone()

    if not reset:
        conn.close()
        return jsonify({'error': 'This reset link is invalid or has already been used'}), 400

    if datetime.utcnow() > datetime.fromisoformat(reset['expires_at']):
        conn.close()
        return jsonify({'error': 'This reset link has expired — please request a new one'}), 400

    if request.method == 'GET':
        conn.close()
        return jsonify({'valid': True}), 200

    data     = request.get_json() or {}
    new_pass = data.get('password', '')
    if len(new_pass) < 8:
        conn.close()
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    conn.execute('UPDATE admins SET password_hash = ? WHERE id = ?',
                 (generate_password_hash(new_pass), reset['admin_id']))
    conn.execute('UPDATE password_resets SET used = 1 WHERE id = ?', (reset['id'],))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Password updated successfully'}), 200


# ─── opportunities routes ──────────────────────────────────────────────────────

@app.route('/api/opportunities', methods=['GET'])
@login_required
def list_opportunities():
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM opportunities WHERE admin_id = ? ORDER BY created_at DESC',
        (session['admin_id'],)
    ).fetchall()
    conn.close()
    return jsonify([opp_to_dict(r) for r in rows]), 200


@app.route('/api/opportunities', methods=['POST'])
@login_required
def create_opportunity():
    data = request.get_json() or {}

    name      = data.get('name', '').strip()
    duration  = data.get('duration', '').strip()
    start_date = data.get('start_date', '').strip()
    description = data.get('description', '').strip()
    skills    = data.get('skills', '').strip()
    category  = data.get('category', '').strip()
    future    = data.get('future_opportunities', '').strip()
    max_app   = data.get('max_applicants') or None

    if not all([name, duration, start_date, description, skills, category, future]):
        return jsonify({'error': 'Please fill in all required fields'}), 400

    conn   = get_db()
    cursor = conn.execute(
        '''INSERT INTO opportunities
           (admin_id, name, duration, start_date, description, skills, category, future_opportunities, max_applicants)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (session['admin_id'], name, duration, start_date, description,
         skills, category, future, int(max_app) if max_app else None)
    )
    new_id = cursor.lastrowid
    conn.commit()
    row = conn.execute('SELECT * FROM opportunities WHERE id = ?', (new_id,)).fetchone()
    conn.close()
    return jsonify(opp_to_dict(row)), 201


@app.route('/api/opportunities/<int:opp_id>', methods=['PUT'])
@login_required
def update_opportunity(opp_id):
    conn = get_db()
    opp  = conn.execute(
        'SELECT * FROM opportunities WHERE id = ? AND admin_id = ?',
        (opp_id, session['admin_id'])
    ).fetchone()

    if not opp:
        conn.close()
        return jsonify({'error': 'Opportunity not found'}), 404

    data = request.get_json() or {}

    name       = data.get('name', '').strip()
    duration   = data.get('duration', '').strip()
    start_date = data.get('start_date', '').strip()
    description = data.get('description', '').strip()
    skills     = data.get('skills', '').strip()
    category   = data.get('category', '').strip()
    future     = data.get('future_opportunities', '').strip()
    max_app    = data.get('max_applicants') or None

    if not all([name, duration, start_date, description, skills, category, future]):
        conn.close()
        return jsonify({'error': 'Please fill in all required fields'}), 400

    conn.execute(
        '''UPDATE opportunities
           SET name=?, duration=?, start_date=?, description=?, skills=?,
               category=?, future_opportunities=?, max_applicants=?
           WHERE id=?''',
        (name, duration, start_date, description, skills, category,
         future, int(max_app) if max_app else None, opp_id)
    )
    conn.commit()
    row = conn.execute('SELECT * FROM opportunities WHERE id = ?', (opp_id,)).fetchone()
    conn.close()
    return jsonify(opp_to_dict(row)), 200


@app.route('/api/opportunities/<int:opp_id>', methods=['DELETE'])
@login_required
def delete_opportunity(opp_id):
    conn = get_db()
    opp  = conn.execute(
        'SELECT id FROM opportunities WHERE id = ? AND admin_id = ?',
        (opp_id, session['admin_id'])
    ).fetchone()

    if not opp:
        conn.close()
        return jsonify({'error': 'Opportunity not found'}), 404

    conn.execute('DELETE FROM opportunities WHERE id = ?', (opp_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Opportunity deleted'}), 200


# ─── run ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=8080)
