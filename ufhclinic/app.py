from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import sqlite3, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'healthtriage.db')
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'ufh-healthcare-demo-secret-key')

SERVICES = [
    ('Primary Health Care', 'General assessment, minor ailments and routine follow-up.'),
    ('HIV Counselling & Testing', 'Confidential HIV counselling and testing workflow.'),
    ('Diabetes Screening', 'Blood glucose screening recorded by clinic staff.'),
    ('Blood Pressure Check', 'BP screening and monitoring.'),
    ('Temperature Check', 'Temperature measurement during screening.'),
    ('STI / Sexual Health', 'Confidential sexual and reproductive health support.'),
    ('Chronic Treatment Follow-up', 'Continuation and refill tracking for treatment transferred from another clinic.'),
    ('Wound / Minor Ailment Care', 'Basic primary-care treatment and follow-up.'),
    ('Referral', 'Referral to an appropriate external health facility when needed.'),
]
NURSES = [
    ('Sr. L Simandla', 'Professional Nurse', 'Primary Health Care'),
    ('Sr. O Hombana', 'Professional Nurse', 'Primary Health Care'),
    ('Sr. N Tom', 'Professional Nurse', 'HIV / Primary Health Care'),
    ('Sr. S Maqhosha', 'Professional Nurse', 'Primary Health Care'),
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def require_role(role, endpoint):
    if session.get('role') != role:
        flash('Please login to continue.', 'error')
        return redirect(url_for(endpoint))
    return None


def log_action(action):
    try:
        conn = get_db()
        conn.execute('INSERT INTO activity_logs(user_id,user_name,user_role,action,created_at) VALUES(?,?,?,?,?)',
                     (session.get('user_id'), session.get('name'), session.get('role'), action, now()))
        conn.commit(); conn.close()
    except Exception:
        pass


def init_db():
    conn = get_db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('patient','nurse','admin')),
        student_number TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        campus TEXT DEFAULT 'Alice',
        created_at TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        patient_name TEXT NOT NULL,
        service TEXT NOT NULL DEFAULT 'Consultation',
        nurse_name TEXT DEFAULT '',
        appointment_date TEXT NOT NULL,
        appointment_time TEXT NOT NULL,
        reason TEXT NOT NULL,
        notes TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Pending',
        nurse_notes TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS triage_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        patient_name TEXT NOT NULL,
        age INTEGER NOT NULL,
        symptom TEXT NOT NULL,
        duration TEXT NOT NULL,
        severity TEXT NOT NULL,
        description TEXT DEFAULT '',
        priority TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pending',
        nurse_notes TEXT DEFAULT '',
        treatment TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        triage_id INTEGER,
        appointment_id INTEGER,
        nurse_name TEXT DEFAULT '',
        bp_systolic INTEGER,
        bp_diastolic INTEGER,
        glucose REAL,
        glucose_unit TEXT DEFAULT 'mmol/L',
        temperature REAL,
        hiv_test TEXT DEFAULT 'Not done',
        hiv_notes TEXT DEFAULT '',
        consultation_notes TEXT DEFAULT '',
        diagnosis TEXT DEFAULT '',
        treatment_recommendation TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Screening',
        created_at TEXT NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS treatment_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        medication TEXT NOT NULL,
        dosage TEXT DEFAULT '',
        frequency TEXT DEFAULT '',
        indication TEXT DEFAULT '',
        source_clinic TEXT DEFAULT 'UFH Clinic',
        transferred_from_local_clinic INTEGER NOT NULL DEFAULT 0,
        start_date TEXT NOT NULL,
        next_review_date TEXT DEFAULT '',
        next_refill_date TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Active',
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS checkups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        checkup_type TEXT NOT NULL,
        scheduled_date TEXT NOT NULL,
        completed_date TEXT DEFAULT '',
        nurse_name TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Scheduled',
        created_at TEXT NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        referred_to TEXT NOT NULL,
        reason TEXT NOT NULL,
        referral_date TEXT NOT NULL,
        followup_date TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Pending',
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        user_name TEXT,
        user_role TEXT,
        action TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    ''')
    # Safe migrations for an existing working database.
    for col, typ in [('service','TEXT NOT NULL DEFAULT "Consultation"'),('nurse_name','TEXT DEFAULT ""')]:
        try: conn.execute(f'ALTER TABLE appointments ADD COLUMN {col} {typ}')
        except sqlite3.OperationalError: pass
    for col, typ in [('student_number','TEXT DEFAULT ""'),('phone','TEXT DEFAULT ""'),('campus','TEXT DEFAULT "Alice"'),('created_at','TEXT DEFAULT ""')]:
        try: conn.execute(f'ALTER TABLE users ADD COLUMN {col} {typ}')
        except sqlite3.OperationalError: pass
    conn.commit(); conn.close()


def priority_for(symptom, severity):
    s = (symptom or '').lower()
    sev = (severity or '').lower()
    high = ['chest pain','difficulty breathing','shortness of breath','severe bleeding','unconscious','stroke','seizure']
    medium = ['fever','vomiting','stomach pain','abdominal pain','headache','diarrhea','persistent cough']
    if any(x in s for x in high) or sev == 'severe': return 'HIGH PRIORITY'
    if any(x in s for x in medium) or sev == 'moderate': return 'MEDIUM PRIORITY'
    return 'LOW PRIORITY'


def priority_message(p):
    return {'HIGH PRIORITY':'Urgent professional assessment is required. This screening result is not a diagnosis.',
            'MEDIUM PRIORITY':'Please attend the clinic for professional assessment soon.',
            'LOW PRIORITY':'Routine professional assessment is recommended, especially if symptoms worsen.'}.get(p, '')

@app.context_processor
def globals_for_templates():
    return {'services': SERVICES, 'today': date.today().isoformat()}

@app.route('/')
def home(): return render_template('index.html')

@app.route('/services')
def services(): return render_template('services.html')

@app.route('/patient/register', methods=['GET','POST'])
def patient_register():
    if request.method == 'POST':
        name=request.form.get('full_name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        student=request.form.get('student_number','').strip(); phone=request.form.get('phone','').strip(); campus=request.form.get('campus','Alice').strip()
        if not name or not email or not password: flash('Please complete all required fields.','error'); return render_template('patientRegister.html')
        try:
            c=get_db(); c.execute('INSERT INTO users(full_name,email,password,role,student_number,phone,campus,created_at) VALUES(?,?,?,?,?,?,?,?)',
                (name,email,generate_password_hash(password),'patient',student,phone,campus,now())); c.commit(); c.close()
            flash('Patient account created successfully.','success'); return redirect(url_for('patient_login'))
        except sqlite3.IntegrityError: flash('An account with that email already exists.','error')
    return render_template('patientRegister.html')

@app.route('/patient/login', methods=['GET','POST'])
def patient_login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        c=get_db(); u=c.execute("SELECT * FROM users WHERE email=? AND role='patient'",(email,)).fetchone(); c.close()
        if u and check_password_hash(u['password'],password):
            session.clear(); session.update(user_id=u['id'],name=u['full_name'],email=u['email'],role='patient'); log_action('Patient logged in'); return redirect(url_for('patient_dashboard'))
        flash('Invalid patient email or password.','error')
    return render_template('patientLogin.html')

@app.route('/nurse/register', methods=['GET','POST'])
def nurse_register():
    if request.method=='POST':
        name=request.form.get('full_name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        if not name or not email or not password: flash('Please complete all required fields.','error'); return render_template('nurseRegister.html')
        try:
            c=get_db(); c.execute('INSERT INTO users(full_name,email,password,role,created_at) VALUES(?,?,?,?,?)',(name,email,generate_password_hash(password),'nurse',now())); c.commit(); c.close(); flash('Nurse account created successfully.','success'); return redirect(url_for('nurse_login'))
        except sqlite3.IntegrityError: flash('An account with that email already exists.','error')
    return render_template('nurseRegister.html')

@app.route('/nurse/login', methods=['GET','POST'])
def nurse_login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        c=get_db(); u=c.execute("SELECT * FROM users WHERE email=? AND role='nurse'",(email,)).fetchone(); c.close()
        if u and check_password_hash(u['password'],password):
            session.clear(); session.update(user_id=u['id'],name=u['full_name'],email=u['email'],role='nurse'); log_action('Nurse logged in'); return redirect(url_for('nurse_dashboard'))
        flash('Invalid nurse email or password.','error')
    return render_template('nurseLogin.html')

@app.route('/admin/register', methods=['GET','POST'])
def admin_register():
    if request.method=='POST':
        name=request.form.get('full_name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        if not name or not email or not password: flash('Please complete all required fields.','error'); return render_template('adminRegister.html')
        try:
            c=get_db(); c.execute('INSERT INTO users(full_name,email,password,role,created_at) VALUES(?,?,?,?,?)',(name,email,generate_password_hash(password),'admin',now())); c.commit(); c.close(); flash('Admin account created successfully.','success'); return redirect(url_for('admin_login'))
        except sqlite3.IntegrityError: flash('An account with that email already exists.','error')
    return render_template('adminRegister.html')

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        c=get_db(); u=c.execute("SELECT * FROM users WHERE email=? AND role='admin'",(email,)).fetchone(); c.close()
        if u and check_password_hash(u['password'],password):
            session.clear(); session.update(user_id=u['id'],name=u['full_name'],email=u['email'],role='admin'); log_action('Admin logged in'); return redirect(url_for('admin_dashboard'))
        flash('Invalid admin email or password.','error')
    return render_template('adminLogin.html')

@app.route('/patient/dashboard')
def patient_dashboard():
    d=require_role('patient','patient_login');
    if d:return d
    c=get_db(); uid=session['user_id']
    a=c.execute('SELECT * FROM appointments WHERE patient_id=? ORDER BY appointment_date,appointment_time',(uid,)).fetchall()
    t=c.execute('SELECT * FROM triage_records WHERE patient_id=? ORDER BY created_at DESC',(uid,)).fetchall()
    v=c.execute('SELECT * FROM visits WHERE patient_id=? ORDER BY created_at DESC LIMIT 10',(uid,)).fetchall()
    meds=c.execute('SELECT * FROM treatment_records WHERE patient_id=? ORDER BY next_refill_date',(uid,)).fetchall()
    checks=c.execute('SELECT * FROM checkups WHERE patient_id=? ORDER BY scheduled_date',(uid,)).fetchall(); c.close()
    return render_template('patientDashboard.html',name=session['name'],appointments=a,records=t,visits=v,medications=meds,checkups=checks)

@app.route('/triage', methods=['GET','POST'])
def triage():
    d=require_role('patient','patient_login');
    if d:return d
    if request.method=='POST':
        age=request.form.get('age','').strip(); symptom=request.form.get('symptom','').strip(); duration=request.form.get('duration','').strip(); severity=request.form.get('severity','').strip(); desc=request.form.get('description','').strip()
        try: age=int(age); assert 0<=age<=120
        except Exception: flash('Enter a valid age.','error'); return render_template('triage.html')
        if not symptom or not duration or not severity: flash('Complete all required triage fields.','error'); return render_template('triage.html')
        p=priority_for(symptom,severity); c=get_db(); cur=c.execute('INSERT INTO triage_records(patient_id,patient_name,age,symptom,duration,severity,description,priority,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (session['user_id'],session['name'],age,symptom,duration,severity,desc,p,'Pending',now())); tid=cur.lastrowid; c.commit(); c.close(); log_action('Completed triage assessment')
        return render_template('result.html',priority=p,message=priority_message(p),symptom=symptom,description=desc,triage_id=tid)
    return render_template('triage.html')

@app.route('/patient/records')
def patient_records():
    d=require_role('patient','patient_login');
    if d:return d
    c=get_db(); uid=session['user_id']; records=c.execute('SELECT * FROM triage_records WHERE patient_id=? ORDER BY created_at DESC',(uid,)).fetchall(); visits=c.execute('SELECT * FROM visits WHERE patient_id=? ORDER BY created_at DESC',(uid,)).fetchall(); meds=c.execute('SELECT * FROM treatment_records WHERE patient_id=? ORDER BY created_at DESC',(uid,)).fetchall(); referrals=c.execute('SELECT * FROM referrals WHERE patient_id=? ORDER BY created_at DESC',(uid,)).fetchall(); checks=c.execute('SELECT * FROM checkups WHERE patient_id=? ORDER BY scheduled_date DESC',(uid,)).fetchall(); c.close()
    return render_template('patientRecords.html',records=records,visits=visits,medications=meds,referrals=referrals,checkups=checks)

@app.route('/patient/appointments/book', methods=['GET','POST'])
def book_appointment():
    d=require_role('patient','patient_login');
    if d:return d
    if request.method=='POST':
        service=request.form.get('service','Consultation').strip(); nurse=request.form.get('nurse_name','').strip(); appt_date=request.form.get('appointment_date','').strip(); appt_time=request.form.get('appointment_time','').strip(); reason=request.form.get('reason','').strip(); notes=request.form.get('notes','').strip()
        try:
            chosen=datetime.strptime(f'{appt_date} {appt_time}','%Y-%m-%d %H:%M')
            if chosen<=datetime.now(): raise ValueError
        except ValueError: flash('Choose a valid future date and time.','error'); return render_template('bookAppointment.html',nurses=NURSES)
        c=get_db(); exists=c.execute("SELECT id FROM appointments WHERE appointment_date=? AND appointment_time=? AND status!='Cancelled'",(appt_date,appt_time)).fetchone()
        if exists: c.close(); flash('That consultation time is already booked. Choose another time.','error'); return render_template('bookAppointment.html',nurses=NURSES)
        c.execute('INSERT INTO appointments(patient_id,patient_name,service,nurse_name,appointment_date,appointment_time,reason,notes,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(session['user_id'],session['name'],service,nurse,appt_date,appt_time,reason,notes,'Pending',now())); c.commit(); c.close(); log_action('Booked clinic appointment'); flash('Appointment request submitted.','success'); return redirect(url_for('patient_appointments'))
    return render_template('bookAppointment.html',nurses=NURSES)

@app.route('/patient/appointments')
def patient_appointments():
    d=require_role('patient','patient_login');
    if d:return d
    c=get_db(); rows=c.execute('SELECT * FROM appointments WHERE patient_id=? ORDER BY appointment_date DESC,appointment_time DESC',(session['user_id'],)).fetchall(); c.close(); return render_template('patientAppointments.html',appointments=rows)

@app.route('/patient/appointments/cancel/<int:appointment_id>',methods=['POST','GET'])
def cancel_appointment(appointment_id):
    d=require_role('patient','patient_login');
    if d:return d
    c=get_db(); c.execute("UPDATE appointments SET status='Cancelled' WHERE id=? AND patient_id=?",(appointment_id,session['user_id'])); c.commit(); c.close(); flash('Appointment cancelled.','success'); return redirect(url_for('patient_appointments'))

@app.route('/patient/screening',methods=['GET','POST'])
def patient_screening():
    d=require_role('patient','patient_login');
    if d:return d
    if request.method=='POST':
        def integer(name):
            x=request.form.get(name,'').strip(); return int(x) if x else None
        def real(name):
            x=request.form.get(name,'').strip(); return float(x) if x else None
        try: sbp=integer('bp_systolic'); dbp=integer('bp_diastolic'); glucose=real('glucose'); temp=real('temperature')
        except ValueError: flash('Enter valid numeric screening values.','error'); return render_template('screening.html')
        hiv=request.form.get('hiv_test','Not done'); hiv_notes=request.form.get('hiv_notes','').strip()
        c=get_db(); c.execute('INSERT INTO visits(patient_id,bp_systolic,bp_diastolic,glucose,temperature,hiv_test,hiv_notes,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(session['user_id'],sbp,dbp,glucose,temp,hiv,hiv_notes,'Screened',now())); c.commit(); c.close(); log_action('Submitted health screening'); flash('Screening recorded. A nurse must review clinical results.','success'); return redirect(url_for('patient_records'))
    return render_template('screening.html')

@app.route('/nurse/dashboard')
def nurse_dashboard():
    d=require_role('nurse','nurse_login');
    if d:return d
    c=get_db(); records=c.execute("SELECT * FROM triage_records ORDER BY CASE priority WHEN 'HIGH PRIORITY' THEN 1 WHEN 'MEDIUM PRIORITY' THEN 2 ELSE 3 END, created_at DESC").fetchall(); appointments=c.execute('SELECT * FROM appointments ORDER BY appointment_date,appointment_time').fetchall(); visits=c.execute('SELECT v.*,u.full_name AS patient_name FROM visits v JOIN users u ON u.id=v.patient_id ORDER BY v.created_at DESC').fetchall(); meds=c.execute('SELECT t.*,u.full_name AS patient_name FROM treatment_records t JOIN users u ON u.id=t.patient_id ORDER BY t.next_refill_date').fetchall(); checks=c.execute('SELECT ch.*,u.full_name AS patient_name FROM checkups ch JOIN users u ON u.id=ch.patient_id ORDER BY ch.scheduled_date').fetchall(); c.close()
    return render_template('nurseDashboard.html',name=session['name'],records=records,appointments=appointments,visits=visits,medications=meds,checkups=checks,nurses=NURSES)

@app.route('/nurse/appointments/update/<int:appointment_id>',methods=['POST'])
def update_appointment(appointment_id):
    d=require_role('nurse','nurse_login');
    if d:return d
    status=request.form.get('status','Pending'); nurse=request.form.get('nurse_name','').strip(); notes=request.form.get('nurse_notes','').strip()
    if status not in {'Pending','Confirmed','Checked In','Completed','Cancelled'}: status='Pending'
    c=get_db(); c.execute('UPDATE appointments SET status=?,nurse_name=?,nurse_notes=? WHERE id=?',(status,nurse,notes,appointment_id)); c.commit(); c.close(); log_action(f'Updated appointment #{appointment_id}'); flash('Appointment updated.','success'); return redirect(url_for('nurse_dashboard'))

@app.route('/nurse/triage/update/<int:record_id>',methods=['POST'])
def update_triage(record_id):
    d=require_role('nurse','nurse_login');
    if d:return d
    notes=request.form.get('nurse_notes','').strip(); treatment=request.form.get('treatment','').strip(); status=request.form.get('status','Pending')
    if status not in {'Pending','Reviewed','Completed'}: status='Pending'
    c=get_db(); c.execute('UPDATE triage_records SET nurse_notes=?,treatment=?,status=? WHERE id=?',(notes,treatment,status,record_id)); c.commit(); c.close(); flash('Triage record updated.','success'); return redirect(url_for('nurse_dashboard'))

@app.route('/nurse/visit/<int:visit_id>/update',methods=['POST'])
def update_visit(visit_id):
    d=require_role('nurse','nurse_login');
    if d:return d
    fields=['bp_systolic','bp_diastolic','glucose','temperature']
    vals=[]
    try:
        for f in fields:
            x=request.form.get(f,'').strip(); vals.append(int(x) if x and f.startswith('bp_') else (float(x) if x else None))
    except ValueError: flash('Invalid vital sign value.','error'); return redirect(url_for('nurse_dashboard'))
    vals += [request.form.get('hiv_test','Not done'),request.form.get('hiv_notes','').strip(),request.form.get('consultation_notes','').strip(),request.form.get('diagnosis','').strip(),request.form.get('treatment_recommendation','').strip(),request.form.get('status','Consultation'),visit_id]
    c=get_db(); c.execute('UPDATE visits SET bp_systolic=?,bp_diastolic=?,glucose=?,temperature=?,hiv_test=?,hiv_notes=?,consultation_notes=?,diagnosis=?,treatment_recommendation=?,status=? WHERE id=?',vals); c.commit(); c.close(); flash('Patient clinical record updated.','success'); return redirect(url_for('nurse_dashboard'))

@app.route('/nurse/treatment/add',methods=['POST'])
def add_treatment():
    d=require_role('nurse','nurse_login');
    if d:return d
    pid=request.form.get('patient_id'); medication=request.form.get('medication','').strip(); dosage=request.form.get('dosage','').strip(); frequency=request.form.get('frequency','').strip(); indication=request.form.get('indication','').strip(); source=request.form.get('source_clinic','UFH Clinic').strip(); transferred=1 if request.form.get('transferred') else 0; start=request.form.get('start_date','').strip() or date.today().isoformat(); review=request.form.get('next_review_date','').strip(); refill=request.form.get('next_refill_date','').strip(); notes=request.form.get('notes','').strip()
    if not pid or not medication: flash('Patient and medication are required.','error'); return redirect(url_for('nurse_dashboard'))
    c=get_db(); c.execute('INSERT INTO treatment_records(patient_id,medication,dosage,frequency,indication,source_clinic,transferred_from_local_clinic,start_date,next_review_date,next_refill_date,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(pid,medication,dosage,frequency,indication,source,transferred,start,review,refill,'Active',notes,now())); c.commit(); c.close(); flash('Treatment record added to the digital patient record.','success'); return redirect(url_for('nurse_dashboard'))

@app.route('/nurse/checkup/add',methods=['POST'])
def add_checkup():
    d=require_role('nurse','nurse_login');
    if d:return d
    pid=request.form.get('patient_id'); typ=request.form.get('checkup_type','Routine check-up').strip(); sched=request.form.get('scheduled_date','').strip(); nurse=request.form.get('nurse_name','').strip(); notes=request.form.get('notes','').strip()
    if not pid or not sched: flash('Patient and check-up date are required.','error'); return redirect(url_for('nurse_dashboard'))
    c=get_db(); c.execute('INSERT INTO checkups(patient_id,checkup_type,scheduled_date,nurse_name,notes,status,created_at) VALUES(?,?,?,?,?,?,?)',(pid,typ,sched,nurse,notes,'Scheduled',now())); c.commit(); c.close(); flash('Check-up scheduled.','success'); return redirect(url_for('nurse_dashboard'))

@app.route('/nurse/referral/add',methods=['POST'])
def add_referral():
    d=require_role('nurse','nurse_login');
    if d:return d
    pid=request.form.get('patient_id'); dest=request.form.get('referred_to','').strip(); reason=request.form.get('reason','').strip(); follow=request.form.get('followup_date','').strip(); notes=request.form.get('notes','').strip()
    if not pid or not dest or not reason: flash('Patient, destination and reason are required.','error'); return redirect(url_for('nurse_dashboard'))
    c=get_db(); c.execute('INSERT INTO referrals(patient_id,referred_to,reason,referral_date,followup_date,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?)',(pid,dest,reason,date.today().isoformat(),follow,'Pending',notes,now())); c.commit(); c.close(); flash('Referral recorded.','success'); return redirect(url_for('nurse_dashboard'))

@app.route('/admin/dashboard')
def admin_dashboard():
    d=require_role('admin','admin_login');
    if d:return d
    c=get_db(); stats={k:c.execute(q).fetchone()[0] for k,q in {'patients':"SELECT COUNT(*) FROM users WHERE role='patient'",'nurses':"SELECT COUNT(*) FROM users WHERE role='nurse'",'appointments':'SELECT COUNT(*) FROM appointments','triage':'SELECT COUNT(*) FROM triage_records','visits':'SELECT COUNT(*) FROM visits','active_treatment':"SELECT COUNT(*) FROM treatment_records WHERE status='Active'",'referrals':'SELECT COUNT(*) FROM referrals'}.items()}; ap=c.execute('SELECT * FROM appointments ORDER BY created_at DESC LIMIT 8').fetchall(); logs=c.execute('SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT 10').fetchall(); c.close(); return render_template('adminDashboard.html',name=session['name'],stats=stats,appointments=ap,logs=logs)

@app.route('/admin/patients')
def admin_patients():
    d=require_role('admin','admin_login');
    if d:return d
    c=get_db(); rows=c.execute("SELECT id,full_name,email,student_number,phone,campus,created_at FROM users WHERE role='patient' ORDER BY id DESC").fetchall(); c.close(); return render_template('adminPatients.html',patients=rows)

@app.route('/admin/nurses')
def admin_nurses():
    d=require_role('admin','admin_login');
    if d:return d
    c=get_db(); rows=c.execute("SELECT id,full_name,email,created_at FROM users WHERE role='nurse' ORDER BY id DESC").fetchall(); c.close(); return render_template('adminNurses.html',nurses=rows)

@app.route('/admin/appointments')
def admin_appointments():
    d=require_role('admin','admin_login');
    if d:return d
    c=get_db(); rows=c.execute('SELECT * FROM appointments ORDER BY appointment_date,appointment_time').fetchall(); c.close(); return render_template('adminAppointments.html',appointments=rows)

@app.route('/admin/triage')
def admin_triage():
    d=require_role('admin','admin_login');
    if d:return d
    c=get_db(); rows=c.execute('SELECT * FROM triage_records ORDER BY created_at DESC').fetchall(); c.close(); return render_template('adminTriage.html',records=rows)

@app.route('/admin/logs')
def admin_logs():
    d=require_role('admin','admin_login');
    if d:return d
    c=get_db(); rows=c.execute('SELECT * FROM activity_logs ORDER BY created_at DESC').fetchall(); c.close(); return render_template('adminLogs.html',records=rows)

@app.route('/logout')
def logout():
    if session.get('user_id'): log_action('Logged out')
    session.clear(); return redirect(url_for('home'))

init_db()
if __name__ == '__main__':
    print('UFH Clinic & Healthcare Triage System: http://127.0.0.1:5000')
    app.run(host='127.0.0.1',port=5000,debug=True)
