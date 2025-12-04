from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, date, timedelta
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Database path helper - works in both dev and production
def get_db_path():
    """Get database path that works in both dev and production"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'study_sync.db')

# Database setup
def init_db():
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Daily entries table
    c.execute('''CREATE TABLE IF NOT EXISTS daily_entries
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  entry_date DATE UNIQUE,
                  notes TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Exercise logs table
    c.execute('''CREATE TABLE IF NOT EXISTS exercise_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  daily_entry_id INTEGER,
                  exercise_number TEXT,
                  methods_used TEXT,
                  tips TEXT,
                  problems_encountered TEXT,
                  insights TEXT,
                  difficulty_rating INTEGER,
                  time_spent_minutes INTEGER,
                  is_completed BOOLEAN DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (daily_entry_id) REFERENCES daily_entries(id))''')
    
    # Add new columns if they don't exist (for existing databases)
    try:
        c.execute("ALTER TABLE exercise_logs ADD COLUMN difficulty_rating INTEGER")
    except:
        pass
    try:
        c.execute("ALTER TABLE exercise_logs ADD COLUMN time_spent_minutes INTEGER")
    except:
        pass
    try:
        c.execute("ALTER TABLE exercise_logs ADD COLUMN is_completed BOOLEAN DEFAULT 0")
    except:
        pass
    
    # Exercise templates table
    c.execute('''CREATE TABLE IF NOT EXISTS exercise_templates
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT,
                  methods_used TEXT,
                  tips TEXT,
                  problems_encountered TEXT,
                  insights TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Migrate existing INTEGER exercise_number to TEXT if needed
    try:
        # Check if exercise_number column exists and is INTEGER type
        c.execute("PRAGMA table_info(exercise_logs)")
        columns = c.fetchall()
        exercise_number_col = next((col for col in columns if col[1] == 'exercise_number'), None)
        
        if exercise_number_col and 'INTEGER' in str(exercise_number_col[2]).upper():
            # Migrate: create new table with TEXT column
            c.execute('''CREATE TABLE exercise_logs_new
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          daily_entry_id INTEGER,
                          exercise_number TEXT,
                          methods_used TEXT,
                          tips TEXT,
                          problems_encountered TEXT,
                          insights TEXT,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY (daily_entry_id) REFERENCES daily_entries(id))''')
            
            c.execute('''INSERT INTO exercise_logs_new 
                         SELECT id, daily_entry_id, CAST(exercise_number AS TEXT), 
                         methods_used, tips, problems_encountered, insights, created_at
                         FROM exercise_logs''')
            
            c.execute('DROP TABLE exercise_logs')
            c.execute('ALTER TABLE exercise_logs_new RENAME TO exercise_logs')
    except Exception as e:
        print(f"Migration note: {e}")  # Table might already be migrated or doesn't exist
    
    # Subjects table
    c.execute('''CREATE TABLE IF NOT EXISTS subjects
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE)''')
    
    # Exercise subjects junction table (many-to-many)
    c.execute('''CREATE TABLE IF NOT EXISTS exercise_subjects
                 (exercise_log_id INTEGER,
                  subject_id INTEGER,
                  PRIMARY KEY (exercise_log_id, subject_id),
                  FOREIGN KEY (exercise_log_id) REFERENCES exercise_logs(id),
                  FOREIGN KEY (subject_id) REFERENCES subjects(id))''')
    
    # Badges table
    c.execute('''CREATE TABLE IF NOT EXISTS badges
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE,
                  description TEXT,
                  icon TEXT,
                  milestone_type TEXT,
                  milestone_value INTEGER)''')
    
    # User badges table (tracks unlocked badges)
    c.execute('''CREATE TABLE IF NOT EXISTS user_badges
                 (badge_id INTEGER,
                  unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (badge_id),
                  FOREIGN KEY (badge_id) REFERENCES badges(id))''')
    
    # User stats table (for streak tracking)
    c.execute('''CREATE TABLE IF NOT EXISTS user_stats
                 (id INTEGER PRIMARY KEY,
                  current_streak INTEGER DEFAULT 0,
                  longest_streak INTEGER DEFAULT 0,
                  last_entry_date DATE)''')
    
    conn.commit()
    conn.close()

def detect_subjects(text):
    """Detect subject keywords in text and return suggested subject names"""
    if not text:
        return []
    
    text_lower = text.lower()
    suggestions = []
    
    # Keyword mappings
    keyword_map = {
        'bolzano-weierstrass': ['bolzano-weierstrass', 'bolzano weierstrass', 'bw', 'bolzano', 'weierstrass'],
        'limits': ['limit', 'limits', 'lim'],
        'sequences': ['sequence', 'sequences', 'seq'],
        'series': ['series', 'serie'],
        'continuity': ['continuity', 'continuous', 'cont'],
        'differentiability': ['differentiability', 'differentiable', 'derivative', 'derivatives'],
        'integration': ['integration', 'integral', 'integrals', 'integrate'],
        'convergence': ['convergence', 'converge', 'convergent', 'divergence', 'divergent'],
        'compactness': ['compactness', 'compact'],
        'connectedness': ['connectedness', 'connected', 'disconnected']
    }
    
    # Check for matches
    for subject_name, keywords in keyword_map.items():
        for keyword in keywords:
            if keyword in text_lower:
                suggestions.append(subject_name)
                break
    
    return list(set(suggestions))  # Remove duplicates

def get_or_create_subject(subject_name):
    """Get subject ID, creating it if it doesn't exist"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Try to get existing subject
    c.execute('SELECT id FROM subjects WHERE name = ?', (subject_name,))
    result = c.fetchone()
    
    if result:
        subject_id = result[0]
    else:
        # Create new subject
        c.execute('INSERT INTO subjects (name) VALUES (?)', (subject_name,))
        subject_id = c.lastrowid
    
    conn.commit()
    conn.close()
    return subject_id

def cleanup_duplicate_badges():
    """Remove duplicate badges, keeping only Hebrew ones"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Find badges with same milestone_type and milestone_value
    c.execute('''SELECT milestone_type, milestone_value, GROUP_CONCAT(id) as ids
                 FROM badges
                 GROUP BY milestone_type, milestone_value
                 HAVING COUNT(*) > 1''')
    
    duplicates = c.fetchall()
    
    for milestone_type, milestone_value, ids_str in duplicates:
        badge_ids = [int(id) for id in ids_str.split(',')]
        
        # Get all badges with this milestone
        c.execute('''SELECT id, name FROM badges 
                     WHERE milestone_type = ? AND milestone_value = ?''', 
                  (milestone_type, milestone_value))
        badges = c.fetchall()
        
        # Find Hebrew badge (contains Hebrew characters)
        hebrew_badge_id = None
        for badge_id, name in badges:
            # Check if name contains Hebrew characters
            if any('\u0590' <= char <= '\u05FF' for char in name):
                hebrew_badge_id = badge_id
                break
        
        # If no Hebrew badge found, keep the first one
        if not hebrew_badge_id:
            hebrew_badge_id = badges[0][0]
        
        # Delete other badges and update user_badges references
        for badge_id, name in badges:
            if badge_id != hebrew_badge_id:
                # Update user_badges to point to Hebrew badge
                c.execute('''UPDATE OR IGNORE user_badges 
                           SET badge_id = ? 
                           WHERE badge_id = ?''', (hebrew_badge_id, badge_id))
                # Delete duplicate badge
                c.execute('DELETE FROM badges WHERE id = ?', (badge_id,))
    
    conn.commit()
    conn.close()

def init_badges():
    """Initialize badge definitions"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    badges = [
        ('תרגיל ראשון', 'השלם את התרגיל הראשון שלך', '🎯', 'exercise_count', 1),
        ('מתחיל', 'השלם 5 תרגילים', '🚀', 'exercise_count', 5),
        ('בדרך', 'השלם 10 תרגילים', '🔥', 'exercise_count', 10),
        ('חצי מאה', 'השלם 50 תרגילים', '💯', 'exercise_count', 50),
        ('מאה', 'השלם 100 תרגילים', '👑', 'exercise_count', 100),
        ('לוחם שבוע', 'שמור על רצף של 7 ימים', '⚡', 'streak_days', 7),
        ('אמן חודש', 'שמור על רצף של 30 ימים', '🌟', 'streak_days', 30),
        ('מומחה נושא', 'השלם 10 תרגילים בנושא אחד', '📚', 'subject_exercise_count', 10),
        ('מאסטר נושא', 'השלם 25 תרגילים בנושא אחד', '🎓', 'subject_exercise_count', 25),
        ('יומן יומי', 'תעד רשומות במשך 7 ימים רצופים', '📝', 'daily_log_streak', 7),
    ]
    
    for badge in badges:
        c.execute('''INSERT OR IGNORE INTO badges (name, description, icon, milestone_type, milestone_value)
                     VALUES (?, ?, ?, ?, ?)''', badge)
    
    conn.commit()
    conn.close()
    
    # Clean up any duplicate badges
    cleanup_duplicate_badges()

def calculate_streak():
    """Calculate current streak and longest streak"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Get all entry dates ordered by date
    c.execute('SELECT DISTINCT entry_date FROM daily_entries ORDER BY entry_date DESC')
    dates = [datetime.strptime(row[0], '%Y-%m-%d').date() for row in c.fetchall()]
    
    if not dates:
        conn.close()
        return 0, 0
    
    # Calculate current streak
    current_streak = 0
    today = date.today()
    check_date = today
    
    for entry_date in dates:
        if entry_date == check_date or entry_date == check_date - timedelta(days=1):
            if entry_date == check_date:
                current_streak += 1
            else:
                current_streak += 1
                check_date = entry_date
        elif entry_date < check_date - timedelta(days=1):
            break
    
    # Calculate longest streak
    longest_streak = 0
    if dates:
        current_longest = 1
        for i in range(len(dates) - 1):
            if (dates[i] - dates[i+1]).days == 1:
                current_longest += 1
            else:
                longest_streak = max(longest_streak, current_longest)
                current_longest = 1
        longest_streak = max(longest_streak, current_longest)
    
    # Update user_stats
    c.execute('SELECT id FROM user_stats LIMIT 1')
    if c.fetchone():
        c.execute('''UPDATE user_stats 
                     SET current_streak = ?, longest_streak = ?, last_entry_date = ?''',
                  (current_streak, longest_streak, dates[0] if dates else None))
    else:
        c.execute('''INSERT INTO user_stats (id, current_streak, longest_streak, last_entry_date)
                     VALUES (1, ?, ?, ?)''',
                  (current_streak, longest_streak, dates[0] if dates else None))
    
    conn.commit()
    conn.close()
    
    return current_streak, longest_streak

def check_badges():
    """Check and unlock badges based on current stats"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Get total exercise count
    c.execute('SELECT COUNT(*) FROM exercise_logs')
    total_exercises = c.fetchone()[0]
    
    # Get current streak
    current_streak, longest_streak = calculate_streak()
    
    # Get exercise count per subject
    c.execute('''SELECT subject_id, COUNT(*) as count
                 FROM exercise_subjects
                 GROUP BY subject_id''')
    subject_counts = {row[0]: row[1] for row in c.fetchall()}
    
    # Get daily log streak (consecutive days with entries)
    c.execute('SELECT DISTINCT entry_date FROM daily_entries ORDER BY entry_date DESC')
    entry_dates = [datetime.strptime(row[0], '%Y-%m-%d').date() for row in c.fetchall()]
    daily_log_streak = 0
    if entry_dates:
        check_date = date.today()
        for entry_date in entry_dates:
            if entry_date == check_date or entry_date == check_date - timedelta(days=1):
                daily_log_streak += 1
                if entry_date < check_date:
                    check_date = entry_date
            elif entry_date < check_date - timedelta(days=1):
                break
    
    # Get all badges
    c.execute('SELECT id, milestone_type, milestone_value FROM badges')
    badges = c.fetchall()
    
    # Get already unlocked badges
    c.execute('SELECT badge_id FROM user_badges')
    unlocked = set(row[0] for row in c.fetchall())
    
    newly_unlocked = []
    
    for badge_id, milestone_type, milestone_value in badges:
        if badge_id in unlocked:
            continue
        
        unlocked_badge = False
        
        if milestone_type == 'exercise_count' and total_exercises >= milestone_value:
            unlocked_badge = True
        elif milestone_type == 'streak_days' and current_streak >= milestone_value:
            unlocked_badge = True
        elif milestone_type == 'subject_exercise_count':
            if any(count >= milestone_value for count in subject_counts.values()):
                unlocked_badge = True
        elif milestone_type == 'daily_log_streak' and daily_log_streak >= milestone_value:
            unlocked_badge = True
        
        if unlocked_badge:
            c.execute('INSERT INTO user_badges (badge_id) VALUES (?)', (badge_id,))
            c.execute('SELECT name, icon FROM badges WHERE id = ?', (badge_id,))
            badge_info = c.fetchone()
            newly_unlocked.append({'name': badge_info[0], 'icon': badge_info[1]})
    
    conn.commit()
    conn.close()
    
    return newly_unlocked

def get_stats():
    """Get all statistics for the dashboard"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Total exercises
    c.execute('SELECT COUNT(*) FROM exercise_logs')
    total_exercises = c.fetchone()[0]
    
    # Total days logged
    c.execute('SELECT COUNT(DISTINCT entry_date) FROM daily_entries')
    total_days = c.fetchone()[0]
    
    # Streaks
    current_streak, longest_streak = calculate_streak()
    
    # Badges
    c.execute('SELECT COUNT(*) FROM user_badges')
    badges_count = c.fetchone()[0]
    
    # Exercises by subject
    c.execute('''SELECT s.name, COUNT(es.exercise_log_id) as count
                 FROM subjects s
                 LEFT JOIN exercise_subjects es ON s.id = es.subject_id
                 GROUP BY s.id
                 ORDER BY count DESC
                 LIMIT 10''')
    exercises_by_subject = [{'name': row[0], 'count': row[1]} for row in c.fetchall()]
    
    # Recent badges
    c.execute('''SELECT b.name, b.icon, b.description, ub.unlocked_at
                 FROM user_badges ub
                 JOIN badges b ON ub.badge_id = b.id
                 ORDER BY ub.unlocked_at DESC
                 LIMIT 5''')
    recent_badges = [{'name': row[0], 'icon': row[1], 'description': row[2], 'unlocked_at': row[3]} 
                     for row in c.fetchall()]
    
    # All badges with unlock status
    c.execute('''SELECT b.id, b.name, b.description, b.icon, 
                 CASE WHEN ub.badge_id IS NOT NULL THEN 1 ELSE 0 END as unlocked
                 FROM badges b
                 LEFT JOIN user_badges ub ON b.id = ub.badge_id
                 ORDER BY unlocked DESC, b.milestone_value''')
    all_badges = [{'id': row[0], 'name': row[1], 'description': row[2], 'icon': row[3], 'unlocked': row[4]}
                  for row in c.fetchall()]
    
    conn.close()
    
    return {
        'total_exercises': total_exercises,
        'total_days': total_days,
        'current_streak': current_streak,
        'longest_streak': longest_streak,
        'badges_count': badges_count,
        'exercises_by_subject': exercises_by_subject,
        'recent_badges': recent_badges,
        'all_badges': all_badges
    }

# Initialize database when app starts (works with both dev server and gunicorn)
init_db()
init_badges()

@app.route('/')
def index():
    """Main page showing daily entries"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Get all daily entries ordered by date (most recent first)
    c.execute('''SELECT de.id, de.entry_date, de.notes,
                 COUNT(el.id) as exercise_count
                 FROM daily_entries de
                 LEFT JOIN exercise_logs el ON de.id = el.daily_entry_id
                 GROUP BY de.id
                 ORDER BY de.entry_date DESC''')
    
    entries = []
    for row in c.fetchall():
        entries.append({
            'id': row[0],
            'date': row[1],
            'notes': row[2],
            'exercise_count': row[3] or 0
        })
    
    # Get all subjects for filtering
    c.execute('SELECT id, name FROM subjects ORDER BY name')
    subjects = [{'id': row[0], 'name': row[1]} for row in c.fetchall()]
    
    conn.close()
    
    # Get stats for gamification
    stats = get_stats()
    
    return render_template('index.html', entries=entries, subjects=subjects, 
                         today_date=date.today().isoformat(), stats=stats)

@app.route('/entry/<date_str>')
def entry_detail(date_str):
    """View/edit entry for a specific date"""
    try:
        entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return "Invalid date format", 400
    
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Get or create daily entry
    c.execute('SELECT id, notes FROM daily_entries WHERE entry_date = ?', (entry_date,))
    entry = c.fetchone()
    
    if entry:
        entry_id, notes = entry
    else:
        # Create new entry
        c.execute('INSERT INTO daily_entries (entry_date) VALUES (?)', (entry_date,))
        entry_id = c.lastrowid
        notes = None
        conn.commit()
    
    # Get all exercises for this entry
    c.execute('''SELECT el.id, el.exercise_number, el.methods_used, el.tips,
                 el.problems_encountered, el.insights, el.difficulty_rating, el.time_spent_minutes, el.is_completed
                 FROM exercise_logs el
                 WHERE el.daily_entry_id = ?
                 ORDER BY el.exercise_number''', (entry_id,))
    
    exercises = []
    for row in c.fetchall():
        ex_id = row[0]
        # Get subjects for this exercise
        c.execute('''SELECT s.id, s.name
                     FROM subjects s
                     JOIN exercise_subjects es ON s.id = es.subject_id
                     WHERE es.exercise_log_id = ?''', (ex_id,))
        exercise_subjects = [{'id': r[0], 'name': r[1]} for r in c.fetchall()]
        
        exercises.append({
            'id': ex_id,
            'exercise_number': row[1],
            'methods_used': row[2],
            'tips': row[3],
            'problems_encountered': row[4],
            'insights': row[5],
            'difficulty_rating': row[6],
            'time_spent_minutes': row[7],
            'is_completed': bool(row[8]) if len(row) > 8 else False,
            'subjects': exercise_subjects
        })
    
    # Get all subjects for tagging
    c.execute('SELECT id, name FROM subjects ORDER BY name')
    all_subjects = [{'id': row[0], 'name': row[1]} for row in c.fetchall()]
    
    # Get templates
    c.execute('SELECT id, name FROM exercise_templates ORDER BY name')
    templates = [{'id': row[0], 'name': row[1]} for row in c.fetchall()]
    
    conn.close()
    
    return render_template('entry.html', 
                         entry_date=entry_date.isoformat(),
                         templates=templates,
                         entry_id=entry_id,
                         notes=notes or '',
                         exercises=exercises,
                         all_subjects=all_subjects)

@app.route('/entry/<date_str>/exercise', methods=['POST'])
def add_exercise(date_str):
    """Add exercise to a daily entry"""
    try:
        entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    
    data = request.json
    exercise_number = data.get('exercise_number')
    methods_used = data.get('methods_used', '')
    tips = data.get('tips', '')
    problems_encountered = data.get('problems_encountered', '')
    insights = data.get('insights', '')
    difficulty_rating = data.get('difficulty_rating')
    time_spent_minutes = data.get('time_spent_minutes')
    subject_names = data.get('subjects', [])
    
    if not exercise_number:
        return jsonify({'error': 'Exercise number is required'}), 400
    
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Get or create daily entry
    c.execute('SELECT id FROM daily_entries WHERE entry_date = ?', (entry_date,))
    entry = c.fetchone()
    
    if entry:
        entry_id = entry[0]
    else:
        c.execute('INSERT INTO daily_entries (entry_date) VALUES (?)', (entry_date,))
        entry_id = c.lastrowid
        conn.commit()
    
    # Insert exercise log
    c.execute('''INSERT INTO exercise_logs 
                 (daily_entry_id, exercise_number, methods_used, tips, problems_encountered, insights, difficulty_rating, time_spent_minutes)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (entry_id, exercise_number, methods_used, tips, problems_encountered, insights, difficulty_rating, time_spent_minutes))
    
    exercise_id = c.lastrowid
    
    # Add subjects
    combined_text = f"{methods_used} {tips} {problems_encountered} {insights}".lower()
    detected_subjects = detect_subjects(combined_text)
    
    # Combine manual and detected subjects
    all_subject_names = list(set(subject_names + detected_subjects))
    
    for subject_name in all_subject_names:
        subject_id = get_or_create_subject(subject_name)
        try:
            c.execute('''INSERT INTO exercise_subjects (exercise_log_id, subject_id)
                         VALUES (?, ?)''', (exercise_id, subject_id))
        except sqlite3.IntegrityError:
            pass  # Already exists
    
    conn.commit()
    conn.close()
    
    # Check for newly unlocked badges
    newly_unlocked = check_badges()
    
    return jsonify({'success': True, 'exercise_id': exercise_id, 'badges_unlocked': newly_unlocked})

@app.route('/exercise/<int:exercise_id>', methods=['PUT'])
def update_exercise(exercise_id):
    """Update an exercise log"""
    data = request.json
    methods_used = data.get('methods_used', '')
    tips = data.get('tips', '')
    problems_encountered = data.get('problems_encountered', '')
    insights = data.get('insights', '')
    difficulty_rating = data.get('difficulty_rating')
    time_spent_minutes = data.get('time_spent_minutes')
    subject_names = data.get('subjects', [])
    
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Update exercise
    c.execute('''UPDATE exercise_logs
                 SET methods_used = ?, tips = ?, problems_encountered = ?, insights = ?, 
                     difficulty_rating = ?, time_spent_minutes = ?
                 WHERE id = ?''',
              (methods_used, tips, problems_encountered, insights, difficulty_rating, time_spent_minutes, exercise_id))
    
    # Remove existing subject associations
    c.execute('DELETE FROM exercise_subjects WHERE exercise_log_id = ?', (exercise_id,))
    
    # Add new subjects
    combined_text = f"{methods_used} {tips} {problems_encountered} {insights}".lower()
    detected_subjects = detect_subjects(combined_text)
    
    all_subject_names = list(set(subject_names + detected_subjects))
    
    for subject_name in all_subject_names:
        subject_id = get_or_create_subject(subject_name)
        c.execute('''INSERT INTO exercise_subjects (exercise_log_id, subject_id)
                     VALUES (?, ?)''', (exercise_id, subject_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/exercise/<int:exercise_id>', methods=['DELETE'])
def delete_exercise(exercise_id):
    """Delete an exercise log"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Delete subject associations
    c.execute('DELETE FROM exercise_subjects WHERE exercise_log_id = ?', (exercise_id,))
    
    # Delete exercise
    c.execute('DELETE FROM exercise_logs WHERE id = ?', (exercise_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/exercise/<int:exercise_id>/toggle-complete', methods=['POST'])
def toggle_exercise_complete(exercise_id):
    """Toggle exercise completion status"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Get current completion status
    c.execute('SELECT is_completed FROM exercise_logs WHERE id = ?', (exercise_id,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return jsonify({'error': 'Exercise not found'}), 404
    
    # Toggle completion status
    new_status = not bool(result[0])
    c.execute('UPDATE exercise_logs SET is_completed = ? WHERE id = ?', (new_status, exercise_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'is_completed': new_status})

@app.route('/entry/<date_str>/notes', methods=['PUT'])
def update_entry_notes(date_str):
    """Update daily entry notes"""
    try:
        entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    
    data = request.json
    notes = data.get('notes', '')
    
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Get or create entry
    c.execute('SELECT id FROM daily_entries WHERE entry_date = ?', (entry_date,))
    entry = c.fetchone()
    
    if entry:
        c.execute('UPDATE daily_entries SET notes = ? WHERE id = ?', (notes, entry[0]))
    else:
        c.execute('INSERT INTO daily_entries (entry_date, notes) VALUES (?, ?)', (entry_date, notes))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/subjects')
def subjects_list():
    """List all subjects with exercise counts"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    c.execute('''SELECT s.id, s.name, COUNT(DISTINCT es.exercise_log_id) as exercise_count
                 FROM subjects s
                 LEFT JOIN exercise_subjects es ON s.id = es.subject_id
                 GROUP BY s.id
                 ORDER BY s.name''')
    
    subjects = []
    for row in c.fetchall():
        subjects.append({
            'id': row[0],
            'name': row[1],
            'exercise_count': row[2] or 0
        })
    
    conn.close()
    
    return render_template('subjects.html', subjects=subjects)

@app.route('/subject/<int:subject_id>')
def subject_detail(subject_id):
    """View all exercises for a specific subject"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Get subject name
    c.execute('SELECT name FROM subjects WHERE id = ?', (subject_id,))
    subject = c.fetchone()
    
    if not subject:
        return "Subject not found", 404
    
    # Get all exercises with this subject
    c.execute('''SELECT el.id, el.exercise_number, el.methods_used, el.tips,
                 el.problems_encountered, el.insights, de.entry_date, el.difficulty_rating, el.time_spent_minutes, el.is_completed
                 FROM exercise_logs el
                 JOIN exercise_subjects es ON el.id = es.exercise_log_id
                 JOIN daily_entries de ON el.daily_entry_id = de.id
                 WHERE es.subject_id = ?
                 ORDER BY de.entry_date DESC, el.exercise_number''', (subject_id,))
    
    exercises = []
    for row in c.fetchall():
        exercises.append({
            'id': row[0],
            'exercise_number': row[1],
            'methods_used': row[2],
            'tips': row[3],
            'problems_encountered': row[4],
            'insights': row[5],
            'entry_date': row[6],
            'difficulty_rating': row[7],
            'time_spent_minutes': row[8],
            'is_completed': bool(row[9]) if len(row) > 9 else False
        })
    
    conn.close()
    
    return render_template('subject_detail.html', subject_name=subject[0], exercises=exercises)

@app.route('/search')
def search():
    """Search entries by exercise number, subjects, or dates"""
    query = request.args.get('q', '')
    subject_id = request.args.get('subject', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Build query
    conditions = []
    params = []
    
    if query:
        # Advanced search: search in exercise number and all content fields
        conditions.append('''(el.exercise_number LIKE ? OR 
                              el.methods_used LIKE ? OR 
                              el.tips LIKE ? OR 
                              el.problems_encountered LIKE ? OR 
                              el.insights LIKE ?)''')
        search_term = f'%{query}%'
        params.extend([search_term, search_term, search_term, search_term, search_term])
    
    if subject_id:
        conditions.append('es.subject_id = ?')
        params.append(subject_id)
    
    if date_from:
        conditions.append('de.entry_date >= ?')
        params.append(date_from)
    
    if date_to:
        conditions.append('de.entry_date <= ?')
        params.append(date_to)
    
    where_clause = ' AND '.join(conditions) if conditions else '1=1'
    
    c.execute(f'''SELECT DISTINCT de.id, de.entry_date, de.notes,
                 COUNT(DISTINCT el.id) as exercise_count
                 FROM daily_entries de
                 JOIN exercise_logs el ON de.id = el.daily_entry_id
                 LEFT JOIN exercise_subjects es ON el.id = es.exercise_log_id
                 WHERE {where_clause}
                 GROUP BY de.id
                 ORDER BY de.entry_date DESC''', params)
    
    entries = []
    for row in c.fetchall():
        entries.append({
            'id': row[0],
            'date': row[1],
            'notes': row[2],
            'exercise_count': row[3] or 0
        })
    
    # Get all subjects for filter
    c.execute('SELECT id, name FROM subjects ORDER BY name')
    subjects = [{'id': row[0], 'name': row[1]} for row in c.fetchall()]
    
    conn.close()
    
    # Get stats for gamification
    stats = get_stats()
    
    return render_template('index.html', entries=entries, subjects=subjects, 
                         search_query=query, selected_subject=subject_id,
                         date_from=date_from, date_to=date_to,
                         today_date=date.today().isoformat(), stats=stats)

@app.route('/api/subjects/suggest', methods=['POST'])
def suggest_subjects():
    """API endpoint to suggest subjects based on text"""
    data = request.json
    text = data.get('text', '')
    
    suggestions = detect_subjects(text)
    
    # Also get all existing subjects for autocomplete
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute('SELECT name FROM subjects ORDER BY name')
    all_subjects = [row[0] for row in c.fetchall()]
    conn.close()
    
    return jsonify({'suggestions': suggestions, 'all_subjects': all_subjects})

@app.route('/stats')
def stats():
    """Statistics dashboard page"""
    stats_data = get_stats()
    return render_template('stats.html', stats=stats_data)

@app.route('/export')
def export_data():
    """Export all data to JSON"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Get all data
    c.execute('SELECT * FROM daily_entries ORDER BY entry_date DESC')
    entries_data = []
    for row in c.fetchall():
        entry_id = row[0]
        c.execute('''SELECT el.id, el.exercise_number, el.methods_used, el.tips,
                     el.problems_encountered, el.insights, el.difficulty_rating, el.time_spent_minutes, el.is_completed
                     FROM exercise_logs el WHERE el.daily_entry_id = ?''', (entry_id,))
        exercises = []
        for ex_row in c.fetchall():
            ex_id = ex_row[0]
            c.execute('''SELECT s.name FROM subjects s
                         JOIN exercise_subjects es ON s.id = es.subject_id
                         WHERE es.exercise_log_id = ?''', (ex_id,))
            subjects = [r[0] for r in c.fetchall()]
            exercises.append({
                'exercise_number': ex_row[1],
                'methods_used': ex_row[2],
                'tips': ex_row[3],
                'problems_encountered': ex_row[4],
                'insights': ex_row[5],
                'difficulty_rating': ex_row[6],
                'time_spent_minutes': ex_row[7],
                'is_completed': bool(ex_row[8]) if len(ex_row) > 8 else False,
                'subjects': subjects
            })
        entries_data.append({
            'date': row[1],
            'notes': row[2],
            'exercises': exercises
        })
    
    c.execute('SELECT name FROM subjects ORDER BY name')
    subjects_list = [row[0] for row in c.fetchall()]
    
    c.execute('''SELECT b.name, b.description, b.icon FROM badges b
                 JOIN user_badges ub ON b.id = ub.badge_id''')
    badges_list = [{'name': row[0], 'description': row[1], 'icon': row[2]} for row in c.fetchall()]
    
    conn.close()
    
    export_data = {
        'export_date': datetime.now().isoformat(),
        'entries': entries_data,
        'subjects': subjects_list,
        'badges': badges_list
    }
    
    from flask import Response
    return Response(
        json.dumps(export_data, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=study_journal_backup.json'}
    )

@app.route('/import', methods=['POST'])
def import_data():
    """Import data from JSON backup"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        import_data = json.loads(file.read().decode('utf-8'))
        
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        
        imported_count = 0
        
        for entry_data in import_data.get('entries', []):
            entry_date = entry_data['date']
            notes = entry_data.get('notes', '')
            
            # Get or create entry
            c.execute('SELECT id FROM daily_entries WHERE entry_date = ?', (entry_date,))
            entry = c.fetchone()
            
            if entry:
                entry_id = entry[0]
                if notes:
                    c.execute('UPDATE daily_entries SET notes = ? WHERE id = ?', (notes, entry_id))
            else:
                c.execute('INSERT INTO daily_entries (entry_date, notes) VALUES (?, ?)', (entry_date, notes))
                entry_id = c.lastrowid
            
            # Import exercises
            for exercise_data in entry_data.get('exercises', []):
                c.execute('''INSERT INTO exercise_logs 
                           (daily_entry_id, exercise_number, methods_used, tips, problems_encountered, 
                            insights, difficulty_rating, time_spent_minutes)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                         (entry_id, exercise_data.get('exercise_number'),
                          exercise_data.get('methods_used', ''),
                          exercise_data.get('tips', ''),
                          exercise_data.get('problems_encountered', ''),
                          exercise_data.get('insights', ''),
                          exercise_data.get('difficulty_rating'),
                          exercise_data.get('time_spent_minutes')))
                
                exercise_id = c.lastrowid
                imported_count += 1
                
                # Add subjects
                for subject_name in exercise_data.get('subjects', []):
                    subject_id = get_or_create_subject(subject_name)
                    try:
                        c.execute('''INSERT INTO exercise_subjects (exercise_log_id, subject_id)
                                   VALUES (?, ?)''', (exercise_id, subject_id))
                    except:
                        pass
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'imported': imported_count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/templates')
def templates_list():
    """List exercise templates"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    c.execute('SELECT id, name, methods_used, tips, problems_encountered, insights FROM exercise_templates ORDER BY name')
    templates = []
    for row in c.fetchall():
        templates.append({
            'id': row[0],
            'name': row[1],
            'methods_used': row[2],
            'tips': row[3],
            'problems_encountered': row[4],
            'insights': row[5]
        })
    
    conn.close()
    return jsonify({'templates': templates})

@app.route('/templates', methods=['POST'])
def create_template():
    """Create exercise template"""
    data = request.json
    name = data.get('name')
    methods_used = data.get('methods_used', '')
    tips = data.get('tips', '')
    problems_encountered = data.get('problems_encountered', '')
    insights = data.get('insights', '')
    
    if not name:
        return jsonify({'error': 'Template name is required'}), 400
    
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    c.execute('''INSERT INTO exercise_templates (name, methods_used, tips, problems_encountered, insights)
                 VALUES (?, ?, ?, ?, ?)''',
              (name, methods_used, tips, problems_encountered, insights))
    
    template_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'template_id': template_id})

@app.route('/api/templates/<int:template_id>')
def get_template(template_id):
    """Get template by ID"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    c.execute('SELECT id, name, methods_used, tips, problems_encountered, insights FROM exercise_templates WHERE id = ?', (template_id,))
    row = c.fetchone()
    
    conn.close()
    
    if row:
        return jsonify({
            'template': {
                'id': row[0],
                'name': row[1],
                'methods_used': row[2],
                'tips': row[3],
                'problems_encountered': row[4],
                'insights': row[5]
            }
        })
    else:
        return jsonify({'error': 'Template not found'}), 404

if __name__ == '__main__':
    init_db()
    # Only run debug mode locally, not in production
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
