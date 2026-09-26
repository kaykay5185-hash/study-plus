from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib, hmac, json, secrets, sqlite3, time, urllib.parse
import os

ROOT = Path(__file__).parent
DB = ROOT / 'studyplus.db'
ROLES = {'student', 'teacher', 'helper', 'admin', 'owner'}

def load_dotenv():
    env_file = ROOT / '.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                key,value=line.split('=',1); os.environ.setdefault(key.strip(),value.strip().strip('"\''))

load_dotenv()
OWNER_EMAIL=os.environ.get('STUDYPLUS_OWNER_EMAIL','owner@example.com').strip().lower()

def connect():
    db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'student', status TEXT NOT NULL DEFAULT 'active', learning_language TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS account_sessions(id INTEGER PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS classes(id INTEGER PRIMARY KEY, title TEXT NOT NULL, language TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'All levels', starts_at TEXT NOT NULL, duration INTEGER NOT NULL DEFAULT 60, teacher_id INTEGER REFERENCES users(id) ON DELETE SET NULL, description TEXT NOT NULL DEFAULT '', meeting_url TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL, target_id INTEGER REFERENCES users(id) ON DELETE SET NULL, reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS class_joins(class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, PRIMARY KEY(class_id,user_id));
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS quizzes(id INTEGER PRIMARY KEY, title TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'Programming', description TEXT NOT NULL DEFAULT '', author_id INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS quiz_questions(id INTEGER PRIMARY KEY, quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE, prompt TEXT NOT NULL, choices TEXT NOT NULL, answer_index INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS quiz_attempts(id INTEGER PRIMARY KEY, quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, score INTEGER NOT NULL, total INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    ''')
    db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('maintenance','0')")
    db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('owner_email',?)",(OWNER_EMAIL,))
    if 'learning_language' not in [r['name'] for r in db.execute('PRAGMA table_info(users)')]: db.execute("ALTER TABLE users ADD COLUMN learning_language TEXT NOT NULL DEFAULT ''")
    if 'meeting_url' not in [r['name'] for r in db.execute('PRAGMA table_info(classes)')]: db.execute("ALTER TABLE classes ADD COLUMN meeting_url TEXT NOT NULL DEFAULT ''")
    if not db.execute('SELECT COUNT(*) FROM classes').fetchone()[0]:
        db.executemany('INSERT INTO classes(title,language,level,starts_at,duration,description) VALUES(?,?,?,?,?,?)', [
          ('Everyday English Conversation','English','Beginner','2026-10-01T17:00',45,'Practice useful phrases and build confidence speaking.'),
          ('العربية للمبتدئين','Arabic','Beginner','2026-10-02T15:00',60,'Learn Arabic greetings, sounds, and simple conversations.'),
          ('French for Travel','French','Intermediate','2026-10-03T18:30',50,'Travel vocabulary and practical conversation practice.')])
    if not db.execute('SELECT COUNT(*) FROM quizzes').fetchone()[0]:
        cur=db.execute("INSERT INTO quizzes(title,language,description) VALUES(?,?,?)",('Programming fundamentals','Programming','A short starter quiz about code and programming concepts.'))
        qid=cur.lastrowid
        samples=[('Which HTML tag creates a link?',['<a>','<p>','<img>','<div>'],0),('Which value represents true or false in JavaScript?',['String','Boolean','Array','Object'],1),('What does CSS control?',['Page styling','Database storage','Server passwords','File downloads'],0)]
        db.executemany('INSERT INTO quiz_questions(quiz_id,prompt,choices,answer_index) VALUES(?,?,?,?)',[(qid,q,json.dumps(c),a) for q,c,a in samples])
    db.commit(); return db

def pw_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    return salt.hex() + '$' + hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 260000).hex()
def pw_ok(password, stored):
    try:
        salt_hex, digest = stored.split('$',1)
        return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt_hex), 260000).hex(), digest)
    except Exception: return False
def safe_user(row): return {'id':row['id'],'email':row['email'],'role':row['role'],'status':row['status'],'learning_language':row['learning_language'],'created_at':row['created_at']}

class Handler(BaseHTTPRequestHandler):
    def respond(self, data, code=200, headers=None):
        raw=json.dumps(data).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw)))
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(raw)
    def file(self, name, content_type):
        raw=(ROOT/name).read_bytes(); self.send_response(200); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def body(self):
        try: return json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or b'{}')
        except Exception: return {}
    def db_user(self, db):
        token=next((x.strip().split('=',1)[1] for x in self.headers.get('Cookie','').split(';') if x.strip().startswith('sp_session=')),None)
        if not token: return None
        return db.execute('SELECT u.* FROM account_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
    def do_GET(self):
        if self.path in ('/','/index.html'): return self.file('index.html','text/html; charset=utf-8')
        if self.path=='/style.css': return self.file('style.css','text/css; charset=utf-8')
        if self.path=='/app.js': return self.file('app.js','text/javascript; charset=utf-8')
        if self.path.startswith('/api'):
            db=connect(); me=self.db_user(db); path=urllib.parse.urlparse(self.path).path
            if path=='/api/bootstrap':
                owner_exists=db.execute("SELECT 1 FROM users WHERE role='owner' LIMIT 1").fetchone() is not None
                out={'owner_exists':owner_exists,'owner_email':db.execute("SELECT value FROM settings WHERE key='owner_email'").fetchone()[0],'maintenance':db.execute("SELECT value FROM settings WHERE key='maintenance'").fetchone()[0]=='1'}
                if me: out['me']=safe_user(me)
                db.close(); return self.respond(out)
            if not me: db.close(); return self.respond({'error':'Sign in to continue.'},401)
            if me['status']=='banned' and me['role']!='owner': db.close(); return self.respond({'banned':True,'message':'Your account is banned. Contact the StudyPLUS owner for help.'},403)
            maintenance=db.execute("SELECT value FROM settings WHERE key='maintenance'").fetchone()[0]=='1'
            if maintenance and me['role']!='owner': db.close(); return self.respond({'maintenance':True,'message':'We are updating StudyPLUS. Please come back later.'},503)
            if path=='/api/me': out={'me':safe_user(me),'maintenance':maintenance}
            elif path=='/api/classes': out={'classes':[dict(r) for r in db.execute('SELECT c.*,u.email teacher_email,EXISTS(SELECT 1 FROM class_joins j WHERE j.class_id=c.id AND j.user_id=?) joined FROM classes c LEFT JOIN users u ON c.teacher_id=u.id ORDER BY starts_at',(me['id'],)) ]}
            elif path=='/api/quizzes': out={'quizzes':[dict(r) for r in db.execute('SELECT q.id,q.title,q.language,q.description,q.created_at,u.email author_email,(SELECT COUNT(*) FROM quiz_questions x WHERE x.quiz_id=q.id) question_count,(SELECT MAX(CAST(a.score*100.0/NULLIF(a.total,0) AS INTEGER)) FROM quiz_attempts a WHERE a.quiz_id=q.id AND a.user_id=?) best_score FROM quizzes q LEFT JOIN users u ON u.id=q.author_id ORDER BY q.id DESC',(me['id'],))]}
            elif path.startswith('/api/quizzes/'):
                qid=path.split('/')[-1]; quiz=db.execute('SELECT * FROM quizzes WHERE id=?',(qid,)).fetchone()
                if not quiz: db.close(); return self.respond({'error':'Quiz not found.'},404)
                out={'quiz':dict(quiz),'questions':[{'id':r['id'],'prompt':r['prompt'],'choices':json.loads(r['choices'])} for r in db.execute('SELECT * FROM quiz_questions WHERE quiz_id=? ORDER BY id',(qid,))]}
            elif path=='/api/members' and me['role'] in ('owner','admin','helper','teacher'): out={'members':[safe_user(r) for r in db.execute('SELECT * FROM users ORDER BY created_at DESC')]}
            elif path=='/api/reports' and me['role'] in ('owner','admin','helper'): out={'reports':[dict(r) for r in db.execute('SELECT r.*,a.email reporter_email,b.email target_email FROM reports r LEFT JOIN users a ON r.reporter_id=a.id LEFT JOIN users b ON r.target_id=b.id ORDER BY r.id DESC')]}
            else: db.close(); return self.respond({'error':'Not allowed.'},403)
            db.close(); return self.respond(out)
        self.respond({'error':'not found'},404)
    def do_POST(self):
        path=urllib.parse.urlparse(self.path).path; data=self.body(); db=connect(); me=self.db_user(db)
        if path=='/api/register':
            email=str(data.get('email','')).strip().lower(); password=str(data.get('password',''))
            if '@' not in email or len(password)<8: db.close(); return self.respond({'error':'Enter a valid email and a password with at least 8 characters.'},400)
            try: db.execute('INSERT INTO users(email,password_hash,learning_language) VALUES(?,?,?)',(email,pw_hash(password),str(data.get('language','')).strip()))
            except sqlite3.IntegrityError: db.close(); return self.respond({'error':'That email already has an account.'},409)
            db.commit(); db.close(); return self.respond({'ok':True})
        if path=='/api/owner/setup':
            email=str(data.get('email','')).strip().lower(); password=str(data.get('password',''))
            owner=db.execute("SELECT id FROM users WHERE role='owner' LIMIT 1").fetchone()
            expected=db.execute("SELECT value FROM settings WHERE key='owner_email'").fetchone()[0]
            if owner: db.close(); return self.respond({'error':'Owner setup is already complete.'},409)
            if email!=expected or len(password)<10: db.close(); return self.respond({'error':'Use the configured owner email and a password of at least 10 characters.'},400)
            db.execute('INSERT INTO users(email,password_hash,role) VALUES(?,?,?)',(email,pw_hash(password),'owner')); db.commit(); db.close(); return self.respond({'ok':True})
        if path=='/api/login':
            email=str(data.get('email','')).strip().lower(); row=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            if not row or not pw_ok(str(data.get('password','')),row['password_hash']): db.close(); return self.respond({'error':'Email or password is incorrect.'},401)
            if row['status']=='banned' and row['role']!='owner': db.close(); return self.respond({'banned':True,'error':'Your account is banned. Contact the StudyPLUS owner for help.'},403)
            token=secrets.token_urlsafe(32); db.execute('INSERT INTO account_sessions(token_hash,user_id,expires) VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],int(time.time())+86400*14)); db.commit(); db.close()
            return self.respond({'ok':True,'user':safe_user(row)},headers={'Set-Cookie':f'sp_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=1209600'})
        if path=='/api/logout':
            token=next((x.strip().split('=',1)[1] for x in self.headers.get('Cookie','').split(';') if x.strip().startswith('sp_session=')),None)
            if token: db.execute('DELETE FROM account_sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),)); db.commit()
            db.close(); return self.respond({'ok':True},headers={'Set-Cookie':'sp_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'})
        if not me: db.close(); return self.respond({'error':'Sign in to continue.'},401)
        if me['status']=='banned' and me['role']!='owner': db.close(); return self.respond({'error':'Your account is banned.'},403)
        maintenance=db.execute("SELECT value FROM settings WHERE key='maintenance'").fetchone()[0]=='1'
        if maintenance and me['role']!='owner': db.close(); return self.respond({'error':'StudyPLUS is temporarily being updated.'},503)
        if path=='/api/classes':
            if me['role'] not in ('owner','teacher'): db.close(); return self.respond({'error':'Teacher access required.'},403)
            title=str(data.get('title','')).strip(); lang=str(data.get('language','')).strip(); start=str(data.get('starts_at','')).strip()
            if not title or not lang or not start: db.close(); return self.respond({'error':'Complete all required fields.'},400)
            meeting=str(data.get('meeting_url','')).strip()
            if meeting and urllib.parse.urlparse(meeting).scheme!='https': db.close(); return self.respond({'error':'Use a secure https meeting link.'},400)
            db.execute('INSERT INTO classes(title,language,level,starts_at,duration,teacher_id,description,meeting_url) VALUES(?,?,?,?,?,?,?,?)',(title,lang,str(data.get('level','All levels')),start,int(data.get('duration',60)),me['id'],str(data.get('description','')),meeting))
        elif path=='/api/quizzes':
            if me['role'] not in ('teacher','admin','owner'): db.close(); return self.respond({'error':'Only teachers, admins, and the owner can create quizzes.'},403)
            title=str(data.get('title','')).strip(); questions=data.get('questions',[])
            if not title or not isinstance(questions,list) or not questions: db.close(); return self.respond({'error':'Add a quiz title and at least one question.'},400)
            cur=db.execute('INSERT INTO quizzes(title,language,description,author_id) VALUES(?,?,?,?)',(title,str(data.get('language','Programming')),str(data.get('description','')),me['id'])); qid=cur.lastrowid
            for item in questions:
                choices=item.get('choices',[]); answer=item.get('answer_index')
                if not item.get('prompt','').strip() or len(choices)<2 or answer is None or int(answer)<0 or int(answer)>=len(choices): db.rollback(); db.close(); return self.respond({'error':'Each question needs text, at least two choices, and a correct answer.'},400)
                db.execute('INSERT INTO quiz_questions(quiz_id,prompt,choices,answer_index) VALUES(?,?,?,?)',(qid,str(item['prompt']).strip(),json.dumps(choices),int(answer)))
        elif path.startswith('/api/quizzes/') and path.endswith('/submit'):
            qid=path.split('/')[-2]; rows=db.execute('SELECT id,answer_index FROM quiz_questions WHERE quiz_id=? ORDER BY id',(qid,)).fetchall()
            if not rows: db.close(); return self.respond({'error':'Quiz not found or has no questions.'},404)
            answers=data.get('answers',{}); score=sum(1 for row in rows if str(answers.get(str(row['id'])))==str(row['answer_index']))
            db.execute('INSERT INTO quiz_attempts(quiz_id,user_id,score,total) VALUES(?,?,?,?)',(qid,me['id'],score,len(rows)))
            db.commit(); db.close(); return self.respond({'score':score,'total':len(rows),'percent':round(100*score/len(rows))})
        elif path.startswith('/api/classes/') and path.endswith('/join'):
            if me['role'] not in ('owner','admin','helper','teacher','student'): db.close(); return self.respond({'error':'Not allowed.'},403)
            db.execute('INSERT OR IGNORE INTO class_joins(class_id,user_id) VALUES(?,?)',(path.split('/')[-2],me['id'])) if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='class_joins'").fetchone() else None
        elif path=='/api/reports':
            if me['role'] not in ('teacher','admin','helper','owner'): db.close(); return self.respond({'error':'Teacher or staff access required.'},403)
            reason=str(data.get('reason','')).strip(); target=data.get('target_id')
            if not reason or not target: db.close(); return self.respond({'error':'Choose a member and explain the report.'},400)
            db.execute('INSERT INTO reports(reporter_id,target_id,reason) VALUES(?,?,?)',(me['id'],int(target),reason))
        elif path.startswith('/api/members/') and path.endswith('/role'):
            if me['role'] not in ('owner','admin'): db.close(); return self.respond({'error':'Owner or admin access required.'},403)
            target=db.execute('SELECT * FROM users WHERE id=?',(path.split('/')[-2],)).fetchone(); role=str(data.get('role',''))
            if not target or role not in ROLES-{ 'owner' } or target['role']=='owner': db.close(); return self.respond({'error':'That role change is not allowed.'},403)
            db.execute('UPDATE users SET role=? WHERE id=?',(role,target['id']))
        elif path.startswith('/api/members/') and path.endswith('/ban'):
            if me['role']!='owner': db.close(); return self.respond({'error':'Only the owner can ban a member.'},403)
            uid=path.split('/')[-2]; reason=str(data.get('reason','')).strip(); target=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            if not target or target['role']=='owner' or not reason: db.close(); return self.respond({'error':'A member and ban reason are required.'},400)
            db.execute("UPDATE users SET status='banned' WHERE id=?",(uid,)); db.execute('INSERT INTO reports(reporter_id,target_id,reason,status) VALUES(?,?,?,?)',(me['id'],uid,'OWNER BAN: '+reason,'approved'))
        elif path.startswith('/api/members/') and path.endswith('/unban'):
            if me['role']!='owner': db.close(); return self.respond({'error':'Only the owner can unban a member.'},403)
            db.execute("UPDATE users SET status='active' WHERE id=? AND role!='owner'",(path.split('/')[-2],))
        elif path.startswith('/api/members/') and path.endswith('/ban-request'):
            if me['role'] not in ('teacher','admin','helper'): db.close(); return self.respond({'error':'Teacher or staff access required.'},403)
            reason=str(data.get('reason','')).strip(); target=db.execute('SELECT * FROM users WHERE id=?',(path.split('/')[-2],)).fetchone()
            if not target or not reason: db.close(); return self.respond({'error':'Choose a member and enter a reason.'},400)
            db.execute('INSERT INTO reports(reporter_id,target_id,reason) VALUES(?,?,?)',(me['id'],target['id'],'BAN REQUEST: '+reason))
        elif path.startswith('/api/reports/') and path.endswith('/decision'):
            if me['role']!='owner': db.close(); return self.respond({'error':'Only the owner can approve ban requests.'},403)
            rid=int(path.split('/')[-2]); report=db.execute('SELECT * FROM reports WHERE id=?',(rid,)).fetchone(); decision=data.get('decision')
            if not report or decision not in ('approve','decline'): db.close(); return self.respond({'error':'Invalid decision.'},400)
            db.execute('UPDATE reports SET status=? WHERE id=?',(decision+'d',rid))
            if decision=='approve' and report['reason'].startswith('BAN REQUEST:') and report['target_id']:
                db.execute("UPDATE users SET status='banned' WHERE id=? AND role!='owner'",(report['target_id'],))
        elif path=='/api/maintenance':
            if me['role']!='owner': db.close(); return self.respond({'error':'Owner access required.'},403)
            db.execute("UPDATE settings SET value=? WHERE key='maintenance'",('1' if data.get('enabled') else '0',))
        else: db.close(); return self.respond({'error':'Not found.'},404)
        db.commit(); db.close(); self.respond({'ok':True})
    def do_OPTIONS(self): self.respond({})
    def log_message(self,*args): pass

if __name__=='__main__':
    connect().close(); print('StudyPLUS running at http://localhost:8000',flush=True); ThreadingHTTPServer(('127.0.0.1',8000),Handler).serve_forever()
