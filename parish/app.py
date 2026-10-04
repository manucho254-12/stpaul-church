import os, io, csv, time, base64, re, secrets, string, smtplib, json, math
import urllib.request, urllib.error, urllib.parse, logging
from logging.handlers import RotatingFileHandler
from werkzeug.exceptions import HTTPException
from datetime import date, timedelta, datetime
from functools import wraps
from collections import defaultdict
from email.message import EmailMessage
from markupsafe import Markup
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, Response, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash as gh, check_password_hash as ch
from werkzeug.utils import secure_filename

_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env):
    for _l in open(_env, encoding='utf-8'):
        _l = _l.strip()
        if _l and not _l.startswith('#') and '=' in _l: _k, _v = _l.split('=', 1); os.environ.setdefault(_k.strip(), _v.strip().strip('"\''))
app = Flask(__name__)
os.makedirs(os.path.join(app.root_path, 'logs'), exist_ok=True)
_h = RotatingFileHandler(os.path.join(app.root_path, 'logs', 'app.log'), maxBytes=1_000_000, backupCount=3, encoding='utf-8')
_h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s')); app.logger.addHandler(_h); app.logger.setLevel(logging.INFO); lg = app.logger
app.config.update(SECRET_KEY=os.getenv('SECRET_KEY', 'change-this-secret'),
    SQLALCHEMY_DATABASE_URI=os.getenv('DB_URI', 'mysql+pymysql://root:@localhost/matuu_parish'), MAX_CONTENT_LENGTH=32 * 1024 * 1024)
UP = os.path.join(app.root_path, 'uploads'); os.makedirs(UP, exist_ok=True)
db = SQLAlchemy(app); C = db.Column; Str = db.String; Int = db.Integer; PK = dict(primary_key=True)
LANGS = ['English', 'Kiswahili', 'Kikamba']
MINISTRIES = ['Choir', 'Youth', 'CMA', 'CWA', 'Finance', 'Parish Council', 'Altar Servers', 'Other']
CATS = ['Priest', 'Parish Administrator', 'Chairperson', 'Finance', 'Youth', 'CMA', 'CWA', 'Choir', 'Other']

class Church(db.Model):
    id = C(Int, **PK); name = C(Str(120), nullable=False); location = C(Str(160)); gmap = C(db.Text)
    pobox = C(Str(60)); chairperson = C(Str(120)); phone = C(Str(30)); email = C(Str(120))
class User(db.Model):
    id = C(Int, **PK); first = C(Str(60)); second = C(Str(60)); username = C(Str(40), unique=True); email = C(Str(120))
    phone = C(Str(30), index=True); church_id = C(Int, db.ForeignKey('church.id'), index=True); ministry = C(Str(80)); pw = C(Str(255))
    role = C(Str(10), default='user'); perms = C(Str(255), default=''); must_change = C(db.Boolean, default=False)
    seen_ann = C(Int, default=0); seen_srv = C(Int, default=0); seen_ser = C(Int, default=0)
    photo = C(Str(255)); added_by = C(Int)
class Staff(db.Model):
    id = C(Int, **PK); name = C(Str(120)); phone = C(Str(30)); email = C(Str(120)); role = C(Str(60)); about = C(db.Text)
    photo = C(Str(255)); perms = C(Str(255), default='sermons'); temp_pw = C(Str(30)); user_id = C(Int, index=True)
class Announcement(db.Model):
    id = C(Int, **PK); kind = C(Str(20), default='Announcement'); title = C(Str(200)); body = C(db.Text); file = C(Str(255)); created = C(db.Date, default=date.today, index=True); church_id = C(Int, db.ForeignKey('church.id'), index=True)
class Service(db.Model):
    id = C(Int, **PK); date = C(db.Date, index=True); time = C(Str(20)); priest = C(Str(120)); language = C(Str(20)); venue = C(Str(160)); topic = C(Str(200)); file = C(Str(255))
class Sermon(db.Model):
    id = C(Int, **PK); title = C(Str(200)); date = C(db.Date, index=True); language = C(Str(20), index=True); file = C(Str(255)); price = C(db.Float, default=0)
class Ministry(db.Model):
    id = C(Int, **PK); church_id = C(Int, db.ForeignKey('church.id'), index=True); category = C(Str(60), index=True); role = C(Str(80)); name = C(Str(120))
    description = C(db.Text); image = C(Str(255)); ord = C(Int, default=0)
class Donation(db.Model):
    id = C(Int, **PK); title = C(Str(120)); paybill = C(Str(40)); account = C(Str(80)); till = C(Str(40)); bank = C(Str(120)); acc_name = C(Str(120)); note = C(db.Text)
class Prayer(db.Model):
    id = C(Int, **PK); user_id = C(Int, index=True); name = C(Str(120)); phone = C(Str(30)); email = C(Str(120)); service = C(Str(60)); location = C(Str(160))
    message = C(db.Text); created = C(db.Date, default=date.today); reply = C(db.Text); replied_on = C(db.Date); reply_seen = C(db.Boolean, default=False)
class Contribution(db.Model):
    id = C(Int, **PK); church_id = C(Int, db.ForeignKey('church.id'), index=True); kind = C(Str(20)); amount = C(db.Float); date = C(db.Date, index=True)
class AttSession(db.Model):
    id = C(Int, **PK); date = C(db.Date, index=True); is_open = C(db.Boolean, default=False)
class Attendance(db.Model):
    id = C(Int, **PK); user_id = C(Int, db.ForeignKey('user.id'), index=True); session_id = C(Int, db.ForeignKey('att_session.id'), index=True); status = C(Str(10)); church_id = C(Int, db.ForeignKey('church.id'), index=True)
    __table_args__ = (db.Index('ix_att_user_session', 'user_id', 'session_id'),)
class Payment(db.Model):
    id = C(Int, **PK); user_id = C(Int, index=True); sermon_id = C(Int, index=True); code = C(Str(20), unique=True); phone = C(Str(30))
    amount = C(db.Float); ext_ref = C(Str(60), index=True); reference = C(Str(60)); status = C(Str(12), default='pending', index=True); created = C(db.Date, default=date.today)
class ResetRequest(db.Model):
    id = C(Int, **PK); user_id = C(Int, index=True); created = C(db.Date, default=date.today); status = C(Str(10), default='pending', index=True); temp_pw = C(Str(30))
class Remittance(db.Model):
    id = C(Int, **PK); church_id = C(Int, db.ForeignKey('church.id'), index=True); user_id = C(Int); date = C(db.Date, index=True)
    tithe = C(db.Float, default=0); offering = C(db.Float, default=0); note = C(Str(255)); status = C(Str(10), default='pending', index=True)
    created = C(db.DateTime, default=datetime.now); confirmed_on = C(db.Date); confirmed_by = C(Str(120))
class Notice(db.Model):
    id = C(Int, **PK); church_id = C(Int, db.ForeignKey('church.id'), index=True); sender_id = C(Int); from_parish = C(db.Boolean, default=False)
    subject = C(Str(200)); body = C(db.Text); file = C(Str(255), index=True); created = C(db.DateTime, default=datetime.now); is_read = C(db.Boolean, default=False, index=True)
class Note(db.Model):
    id = C(Int, **PK); title = C(Str(200)); body = C(db.Text); created = C(db.DateTime, default=datetime.now); updated = C(db.DateTime, default=datetime.now, onupdate=datetime.now)
class Setting(db.Model):
    k = C(Str(60), primary_key=True); v = C(db.Text)

DEFAULTS = dict(church_name='Matuu Parish Church', hero_image='', verse_ref='John 13:34',
    verse='A new command I give you: Love one another. As I have loved you, so you must love one another.',
    welcome="Welcome to our parish family in Matuu. Whoever you are, wherever you are on life's journey, you belong here. Join us in worship, fellowship and service.",
    mission='To proclaim the Gospel of Jesus Christ, nurture the faith of every parishioner through the Word and Sacraments, and serve our community with love, unity and compassion.',
    vision='A united, Christ-centred parish where every member lives their faith joyfully and transforms the community of Matuu and beyond.',
    goals='Strengthen worship and the sacramental life\nGrow small Christian communities and ministries\nNurture youth and children in faith\nSupport the needy through charity and outreach\nPractise transparent stewardship of parish resources',
    county='Machakos', town='Matuu', subcounty='Yatta', phone='', email='', whatsapp='', youtube='', map_query='Matuu Parish Church, Matuu, Kenya', logo='', pay_paybill='', pay_account='', pay_till='', pay_name='')
SET_FIELDS = [('church_name','Church name','text'),('hero_image','Home hero image','file'),('verse','Bible verse','area'),('verse_ref','Verse reference','text'),
    ('welcome','Welcome message','area'),('mission','Mission','area'),('vision','Vision','area'),('goals','Goals (one per line)','area'),('county','County','text'),
    ('town','Town','text'),('subcounty','Sub-county','text'),('phone','Phone','text'),('email','Email','text'),('whatsapp','WhatsApp link','text'),('youtube','YouTube link','text'),('map_query','Parish map search text','text')]
CRUD = {
 'announcements': (Announcement, 'Announcements & Events', [('kind','Type','select',['Announcement','Event']),('title','Title','text'),('body','Message','area'),('file','PDF / Word file (optional)','file'),('church_id','Church (blank = whole parish)','church')], {}),
 'services': (Service, 'Mass & Services', [('date','Date','date'),('time','Time','time'),('priest','Priest','text'),('language','Language','select',LANGS),('venue','Venue','text'),('topic','Topic','text'),('file','PDF schedule (optional)','file')], {}),
 'sermons': (Sermon, 'Sermons', [('title','Topic','text'),('date','Sunday date','date'),('language','Language','select',LANGS),('price','Price in KES (0 = free)','num'),('file','Sermon PDF','file')], {}),
 'ministries': (Ministry, 'Church Ministries', [('church_id','Church','church'),('category','Category','select',CATS),('role','Title / Role','text'),('name','Name','text'),('description','Description','area'),('image','Photo','file'),('ord','Order','num')], {}),
 'churches': (Church, 'Churches in the Parish', [('name','Church name','text'),('location','Location','text'),('gmap','Google Map (place name, "lat,lng" or embed code)','area'),('pobox','P.O. Box (optional)','text'),('chairperson','Chairperson (optional)','text'),('phone','Phone (optional)','text'),('email','Email (optional)','text')], {}),
 'staff': (Staff, 'Staff', [('name','Full name','text'),('phone','Phone number (their username)','text'),('email','Email','text'),('role','Position','select',['Priest','Parish Administrator','Finance','Youth Leader','Choir Master','Secretary','Other']),('about','Details','area'),('photo','Photo (optional, crop to face)','photo'),('perms','Privileges (comma list)','text')], dict(extra=['name','phone','role','temp_pw'], photo='photo')),
 'donations': (Donation, 'Donation Details', [('title','Title (e.g. Building Fund)','text'),('paybill','Paybill number','text'),('account','Account number','text'),('till','Buy Goods & Services (Till) number','text'),('bank','Bank name','text'),('acc_name','Name that appears when paying','text'),('note','Note','area')], {}),
 'contributions': (Contribution, 'Tithes & Offerings', [('church_id','Church','church'),('kind','Type','select',['Tithe','Offering']),('amount','Amount (KES)','num'),('date','Date','date')], {}),
 'attendance': (AttSession, 'Attendance Sundays', [('date','Sunday date','date'),('is_open','Open for members','bool')], {}),
 'notes': (Note, 'Notes', [('title','Title','text'),('body','Note','area')], {}),
 'users': (User, 'Users & Privileges', [('role','Role','select',['user','cadmin|Church admin (own church only)','admin','staff','super']),('perms','Privileges (comma list)','text'),('church_id','Church','church'),('ministry','Ministry','select',MINISTRIES)], dict(extra=['first','second','username','phone','email'], no_new=True)),
}

def settings():
    try: d = dict(DEFAULTS); d.update({s.k: s.v for s in Setting.query}); return d
    except Exception: return dict(DEFAULTS)
def me(): return db.session.get(User, session['uid']) if 'uid' in session else None
def allowed(u, key):
    if not u: return False
    if key in ('users', 'notes', 'notices'): return u.role == 'super'
    return u.role == 'super' or (u.role in ('admin', 'staff') and key in (u.perms or '').split(','))
def need(level=None):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = me()
            if not u: return redirect(url_for('alogin' if request.path.startswith('/admin') else 'login', next=request.path))
            if level == 'admin' and u.role == 'user': abort(403)
            return f(*a, **k)
        return w
    return deco
def guard(key):
    if key not in CRUD and key not in ('settings', 'prayers', 'payments', 'resets', 'notices'): abort(404)
    if not allowed(me(), key): abort(403)
def send_mail(to, subject, body):
    h = os.getenv('SMTP_HOST')
    if not (h and to): lg.warning('Email not sent (SMTP not configured or no address): to=%s subject=%s', to, subject); return False
    try:
        m = EmailMessage(); m['From'] = os.getenv('SMTP_FROM', os.getenv('SMTP_USER')); m['To'] = to; m['Subject'] = subject; m.set_content(body)
        with smtplib.SMTP(h, int(os.getenv('SMTP_PORT', 587)), timeout=15) as s:
            s.starttls(); s.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASS')); s.send_message(m)
        return True
    except Exception as e: lg.error('Email sending failed to %s: %s', to, e); return False
def find_user(l): l = l.strip(); return User.query.filter((db.func.lower(User.username) == l.lower()) | (User.phone == l)).first()

@app.errorhandler(Exception)
def on_error(e):
    if isinstance(e, HTTPException):
        if (e.code or 500) < 400: return e
        code = e.code
        if code >= 500: lg.error('HTTP %s on %s', code, request.path)
    else: lg.exception('Unhandled error on %s', request.path); code = 500
    msg = {401: 'Please log in to continue.', 403: 'You do not have access to this page.', 404: 'Page not found.'}.get(code, 'Something went wrong. Please try again later.')
    return render_template('error.html', code=code, msg=msg), code
@app.before_request
def force_change():
    u = me()
    if u and u.must_change and request.endpoint not in ('account', 'logout', 'media', 'static'): return redirect(url_for('account'))
    ep = request.endpoint or ''
    if u and u.role == 'cadmin' and request.path.startswith('/admin') and not ep.startswith('c_') and ep not in ('dash', 'a_profile', 'alogin', 'static', 'media'): abort(403)
@app.context_processor
def ctx():
    def up(f): return url_for('media', name=f)
    def val(o, f):
        v = getattr(o, f[0]); t = f[2] if len(f) > 2 else 'text'
        if t == 'file': return Markup(f'<a href="{up(v)}" target="_blank">View</a>') if v else ''
        if t == 'photo': return Markup(f'<img src="{up(v)}" class="thumb">') if v else ''
        if t == 'church': c = db.session.get(Church, v) if v else None; return c.name if c else ''
        if t == 'bool': return 'Open' if v else 'Closed'
        if f[0] == 'role' and v == 'cadmin': return 'Church admin'
        return '' if v is None else v
    u = me()
    try:
        n = len(notif_items(u)) if u else 0
        an = Prayer.query.filter(Prayer.reply.is_(None)).count() if allowed(u, 'prayers') else 0
        nb = Notice.query.filter_by(church_id=u.church_id, from_parish=True, is_read=False).count() if u and u.role == 'cadmin' else (Notice.query.filter_by(from_parish=False, is_read=False).count() if u and u.role == 'super' else 0)
    except Exception: n = an = nb = 0
    alink = '/admin/church/notices' if u and u.role == 'cadmin' else ('/admin/notices' if nb and not an else '/admin/inbox')
    return dict(S=settings(), me=u, up=up, val=val, today=date.today(), allowed=allowed, notif=n, anotif=an + nb, alink=alink, nbadge=nb, wa_link=wa_link,
                church_name=lambda i: (db.session.get(Church, i).name if i and db.session.get(Church, i) else ''))
def ann_query(u):
    q = Announcement.query
    if u.role in ('user', 'cadmin'): q = q.filter(Announcement.church_id.is_(None) | (Announcement.church_id == u.church_id))
    return q
def save_doc(fl):
    if not (fl and fl.filename): return None
    base, ext = os.path.splitext(fl.filename); ext = ext.lower()
    if ext not in ('.pdf', '.doc', '.docx'): return False
    v = f"{int(time.time())}_{secure_filename(base) or 'document'}{ext}"; fl.save(os.path.join(UP, v)); return v
def save_img(fl):
    if not (fl and fl.filename): return None
    base, ext = os.path.splitext(fl.filename); ext = ext.lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.gif') or not (fl.mimetype or '').startswith('image/'): return False
    v = f"{int(time.time())}_{secure_filename(base) or 'photo'}{ext}"; fl.save(os.path.join(UP, v)); return v
def period_range(p, year, month, d1, d2):
    try:
        if p == 'month': a = date(year, month, 1); b = date(year + (month == 12), month % 12 + 1, 1) - timedelta(1); lab = a.strftime('%B %Y')
        elif p == 'h1': a, b = date(year, 1, 1), date(year, 6, 30); lab = f'First half of {year} (Jan-Jun)'
        elif p == 'h2': a, b = date(year, 7, 1), date(year, 12, 31); lab = f'Second half of {year} (Jul-Dec)'
        elif p == 'custom': a, b = date.fromisoformat(d1), date.fromisoformat(d2); lab = f'{a} to {b}'
        else: a, b = date(year, 1, 1), date(year, 12, 31); lab = f'Whole year {year}'
    except Exception: return None
    return (a, b, lab) if a <= b else None
def giving(a, b, cid=None):
    q = db.session.query(Contribution.church_id, Contribution.kind, db.func.sum(Contribution.amount), db.func.count(Contribution.id)).filter(Contribution.date >= a, Contribution.date <= b)
    if cid: q = q.filter(Contribution.church_id == cid)
    agg = defaultdict(lambda: dict(tithe=0.0, offering=0.0, n=0))
    for ch_id, kind, tot, n in q.group_by(Contribution.church_id, Contribution.kind):
        agg[ch_id]['tithe' if kind == 'Tithe' else 'offering'] += float(tot or 0); agg[ch_id]['n'] += n
    rows = []
    for c in Church.query.order_by(Church.name):
        if cid and c.id != cid: continue
        x = agg.get(c.id, dict(tithe=0.0, offering=0.0, n=0)); rows.append(dict(id=c.id, name=c.name, tithe=x['tithe'], offering=x['offering'], total=x['tithe'] + x['offering'], n=x['n']))
    return rows
def mark(u, items):
    pays = {}
    for p in Payment.query.filter_by(user_id=u.id).order_by(Payment.id):
        if not (pays.get(p.sermon_id) and pays[p.sermon_id][0] == 'approved'): pays[p.sermon_id] = (p.status, p.id, p.phone)
    for x in items:
        st = pays.get(x.id); x.pstatus, x.ppid, x.pphone = (st if st else (None, None, ''))
        x.access = (x.price or 0) <= 0 or u.role in ('admin', 'staff', 'super') or x.pstatus == 'approved'
    return items
@app.route('/media/<name>')
def media(name):
    if name.lower().endswith(('.pdf', '.doc', '.docx')):
        u = me()
        if not u: return redirect(url_for('login', next=request.path))
        sm = Sermon.query.filter_by(file=name).first()
        if sm and not mark(u, [sm])[0].access: flash('Please pay for this sermon to read or download it.', 'warning'); return redirect(url_for('home', lang=sm.language, _anchor='sermons'))
        an = Announcement.query.filter_by(file=name).first()
        if an and an.church_id and u.role in ('user', 'cadmin') and u.church_id != an.church_id: abort(403)
        nt = Notice.query.filter_by(file=name).first()
        if nt and not (u.role == 'super' or (u.role == 'cadmin' and u.church_id == nt.church_id)): abort(403)
    return send_from_directory(UP, name, as_attachment=bool(request.args.get('dl')))
PH = 'https://backend.payhero.co.ke/api/v2'
def ph_ready(): return all(os.getenv(k) for k in ('PAYHERO_API_USERNAME', 'PAYHERO_API_PASSWORD', 'PAYHERO_CHANNEL_ID'))
def ph_call(method, path, payload=None):
    tok = base64.b64encode(f"{os.getenv('PAYHERO_API_USERNAME', '')}:{os.getenv('PAYHERO_API_PASSWORD', '')}".encode()).decode()
    req = urllib.request.Request(PH + path, data=json.dumps(payload).encode() if payload else None, method=method, headers={'Authorization': 'Basic ' + tok, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e: lg.error('PayHero HTTP %s on %s: %s', e.code, path, e.read().decode()[:500])
    except Exception as e: lg.error('PayHero request failed on %s: %s', path, e)
    return {'success': False}
def norm_phone(p):
    d = re.sub(r'\D', '', p or '')
    if d.startswith('254'): d = '0' + d[3:]
    elif len(d) == 9: d = '0' + d
    return d if re.match(r'^0[17]\d{8}$', d) else None
def settle(p, receipt=None):
    r = ph_call('GET', '/transaction-status?reference=' + urllib.parse.quote(p.reference or ''))
    st = str(r.get('status', '')).upper()
    if st == 'SUCCESS':
        p.status = 'approved'
        if receipt and not Payment.query.filter_by(code=receipt).first(): p.code = receipt
        lg.info('Payment %s approved', p.ext_ref)
    elif st == 'FAILED': p.status = 'failed'; lg.info('Payment %s failed', p.ext_ref)
    db.session.commit(); return p.status
@app.route('/sermons/<int:id>/pay', methods=['POST'])
@need()
def sermon_pay(id):
    u = me(); sm = db.get_or_404(Sermon, id); ph = norm_phone(request.form.get('phone'))
    if not ph: flash('Enter a valid Safaricom number, e.g. 0712345678.', 'danger')
    elif not ph_ready(): lg.error('PayHero not configured: set PAYHERO_API_USERNAME, PAYHERO_API_PASSWORD, PAYHERO_CHANNEL_ID in .env'); flash('Online payment is not available right now. Please try again later.', 'warning')
    else:
        p = Payment(user_id=u.id, sermon_id=id, phone=ph, amount=sm.price, status='pending', ext_ref='SER-' + secrets.token_hex(6).upper()); db.session.add(p); db.session.commit()
        body = dict(amount=int(sm.price) if float(sm.price).is_integer() else sm.price, phone_number=ph, channel_id=int(os.getenv('PAYHERO_CHANNEL_ID')), provider=os.getenv('PAYHERO_PROVIDER', 'm-pesa'), external_reference=p.ext_ref, customer_name=f'{u.first} {u.second}')
        if os.getenv('PAYHERO_CALLBACK_URL'): body['callback_url'] = os.getenv('PAYHERO_CALLBACK_URL')
        r = ph_call('POST', '/payments', body)
        if r.get('success'): p.reference = r.get('reference'); db.session.commit(); flash('A payment prompt has been sent to your phone. Enter your M-Pesa PIN to complete it.', 'success')
        else: lg.error('PayHero did not accept payment %s: %s', p.ext_ref, r); p.status = 'failed'; db.session.commit(); flash('We could not start the payment right now. Please try again in a moment.', 'danger')
    return redirect(url_for('home', lang=sm.language, _anchor='sermons'))
@app.route('/payment/<int:pid>/status')
@need()
def pay_status(pid):
    p = db.get_or_404(Payment, pid)
    if p.user_id != me().id: abort(403)
    if p.status == 'pending' and p.reference: settle(p)
    return {'status': p.status}
@app.route('/sermons/<int:id>/check', methods=['POST'])
@need()
def sermon_check(id):
    sm = db.get_or_404(Sermon, id); p = Payment.query.filter_by(user_id=me().id, sermon_id=id, status='pending').order_by(Payment.id.desc()).first()
    if p and p.reference:
        st = settle(p)
        flash({'approved': 'Payment confirmed. You can now read or download this sermon.', 'failed': 'The payment failed or was cancelled. Please try again.'}.get(st, 'Still waiting for confirmation. Complete the M-Pesa prompt on your phone, then check again.'), 'success' if st == 'approved' else 'info')
    return redirect(url_for('home', lang=sm.language, _anchor='sermons'))
@app.route('/payhero/callback', methods=['POST'])
def payhero_cb():
    r = (request.get_json(silent=True) or {}).get('response') or {}
    p = Payment.query.filter_by(ext_ref=r.get('ExternalReference')).first() if r.get('ExternalReference') else None
    if p and p.status == 'pending' and p.reference: settle(p, r.get('MpesaReceiptNumber'))   # status is re-verified with PayHero, never trusted from the callback body
    return {'ok': True}

# ---------- public ----------
def loc_ctx():
    cs = Church.query.all(); cid = request.args.get('church', type=int); c = db.session.get(Church, cid) if cid else (cs[0] if cs else None)
    q = (c.gmap or c.location or c.name) if c else settings()['map_query']
    m = re.search(r'src="([^"]+)"', q or '')
    return dict(churches=cs, c=c, src=m.group(1) if m else 'https://www.google.com/maps?q=' + (q or '').replace(' ', '+') + '&output=embed')
def min_ctx():
    q = Ministry.query; cid = request.args.get('church', type=int); cat = request.args.get('cat')
    if cid: q = q.filter_by(church_id=cid)
    if cat: q = q.filter_by(category=cat)
    return dict(m_items=q.order_by(Ministry.ord, Ministry.id).all(), cats=CATS, cid=cid, cat=cat)
@app.route('/')
def home():
    u = me(); lang = request.args.get('lang', 'English')
    d = dict(services_l=[], ann_l=[], ser_l=[], lang=lang, langs=LANGS, don_l=Donation.query.all(), mine=[])
    if u:
        d.update(services_l=Service.query.order_by(Service.date.desc()).limit(40).all(), ann_l=ann_query(u).order_by(Announcement.id.desc()).all(),
                 ser_l=mark(me(), Sermon.query.filter_by(language=lang).order_by(Sermon.date.desc()).all()), mine=Prayer.query.filter_by(user_id=u.id).order_by(Prayer.id.desc()).all())
    return render_template('home.html', **d, **loc_ctx(), **min_ctx())
@app.route('/about')
def about(): return render_template('about.html')
@app.route('/services')
@need()
def services(): return render_template('services.html', items=Service.query.order_by(Service.date.desc()).limit(40).all())
@app.route('/announcements')
@need()
def announcements(): return render_template('announcements.html', items=ann_query(me()).order_by(Announcement.id.desc()).all())
@app.route('/sermons')
@need()
def sermons():
    lang = request.args.get('lang', 'English')
    return render_template('sermons.html', items=mark(me(), Sermon.query.filter_by(language=lang).order_by(Sermon.date.desc()).all()), lang=lang, langs=LANGS)
@app.route('/ministries')
def ministries(): d = min_ctx(); return render_template('ministries.html', items=d['m_items'], churches=Church.query.all(), cats=CATS, cid=d['cid'], cat=d['cat'])
@app.route('/donate')
def donate(): return render_template('donate.html', items=Donation.query.all())
@app.route('/location')
def location(): return render_template('location.html', **loc_ctx())
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    u = me()
    if request.method == 'POST':
        f = request.form
        db.session.add(Prayer(user_id=u.id if u else None, name=f['name'], phone=f['phone'], email=f.get('email', ''), service=f['service'], location=f['location'], message=f.get('message', '')))
        db.session.commit(); flash('Thank you. Your message has been sent to the parish office.', 'success'); return redirect(url_for('contact'))
    mine = Prayer.query.filter_by(user_id=u.id).order_by(Prayer.id.desc()).all() if u else []
    return render_template('contact.html', mine=mine)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        f = request.form; un = f['username'].strip()
        if not re.match(r'^[A-Za-z0-9_.-]{3,30}$', un): flash('Username must be 3-30 letters, numbers, dot, dash or underscore.', 'danger')
        elif f['password'] != f['confirm']: flash('Passwords do not match.', 'danger')
        elif find_user(un) or find_user(f['phone']): flash('That username or phone number is already registered.', 'danger')
        else:
            u = User(first=f['first'], second=f['second'], username=un, email=f.get('email', '').strip(), phone=f['phone'].strip(), church_id=f.get('church_id') or None, ministry=f['ministry'], pw=gh(f['password']), **seen_now())
            db.session.add(u); db.session.commit()
            return render_template('registered.html', u=u, church=db.session.get(Church, u.church_id) if u.church_id else None, pw=f['password'])
    return render_template('register.html', churches=Church.query.all(), ministries=MINISTRIES)
def do_login(admin):
    if request.method == 'POST':
        u = find_user(request.form['login'])
        if u and ch(u.pw, request.form['password']) and (not admin or u.role != 'user'):
            session['uid'] = u.id; return redirect(request.args.get('next') or url_for('dash' if admin else 'home'))
        flash('Invalid username/phone or password.', 'danger')
    return render_template('login.html', admin=admin)
@app.route('/login', methods=['GET', 'POST'])
def login(): return do_login(False)
@app.route('/admin/login', methods=['GET', 'POST'])
def alogin(): return do_login(True)
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('home'))
def new_temp(): return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
def wa_link(phone, text=''):
    p = norm_phone(phone); return ('https://wa.me/254' + p[1:] + '?text=' + urllib.parse.quote(text)) if p else ''
def reset_user(u):
    t = new_temp(); u.pw = gh(t); u.must_change = True
    rs = ResetRequest.query.filter_by(user_id=u.id, status='pending').all() or [ResetRequest(user_id=u.id)]
    for r in rs: db.session.add(r); r.status = 'done'; r.temp_pw = t
    st = Staff.query.filter_by(user_id=u.id).first()
    if st: st.temp_pw = t
    db.session.commit()
    send_mail(u.email, 'Your temporary password', f'Hello {u.first},\n\nUsername: {u.username}\nTemporary password: {t}\n\nLog in and you will be asked to set a new password.')
    lg.info('Password reset issued for user %s', u.id); return t
@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        l = request.form['login'].strip(); u = find_user(l) or User.query.filter(db.func.lower(User.email) == l.lower()).first()
        if u:
            ok = False
            if u.email:
                t = new_temp(); ok = send_mail(u.email, 'Your temporary password', f'Hello {u.first},\n\nUsername: {u.username}\nTemporary password: {t}\n\nLog in and you will be asked to set a new password.')
                if ok: u.pw = gh(t); u.must_change = True; db.session.commit()
            if not ok and not ResetRequest.query.filter_by(user_id=u.id, status='pending').first(): db.session.add(ResetRequest(user_id=u.id)); db.session.commit()
        flash('If the account exists, a temporary password will be emailed to you, or the parish office will contact you with one.', 'info'); return redirect(url_for('login'))
    return render_template('forgot.html')
@app.route('/account', methods=['GET', 'POST'])
@need()
def account():
    u = me()
    if request.method == 'POST':
        f = request.form; kind = f.get('form'); bk = f.get('back') or ''
        back = bk if bk.startswith('/') and not bk.startswith('//') else url_for('account')
        if kind == 'photo':
            d = f.get('photo_data', '')
            try:
                raw = base64.b64decode(d.split(',', 1)[1]) if d.startswith('data:image/jpeg;base64,') else b''
                if raw[:3] != b'\xff\xd8\xff' or len(raw) > 2_000_000: raise ValueError('bad image')
                fn = f'user{u.id}_{int(time.time())}.jpg'; open(os.path.join(UP, fn), 'wb').write(raw); u.photo = fn; db.session.commit(); flash('Profile picture updated.', 'success')
            except Exception as e: lg.warning('Profile photo rejected for user %s: %s', u.id, e); flash('Please choose a photo and crop it, then save.', 'danger')
        elif kind == 'remove': u.photo = None; db.session.commit(); flash('Profile picture removed.', 'success')
        elif kind == 'username':
            nu = f.get('username', '').strip(); o = find_user(nu) if nu else None
            if u.role == 'user': abort(403)
            elif not re.match(r'^[A-Za-z0-9_.-]{3,30}$', nu): flash('Username must be 3-30 letters, numbers, dot, dash or underscore.', 'danger')
            elif o and o.id != u.id: flash('That username or phone number is already in use.', 'danger')
            else: u.username = nu; db.session.commit(); flash('Username updated. Use it the next time you log in.', 'success')
        elif not ch(u.pw, f.get('old', '')): flash('Current password is wrong.', 'danger')
        elif f.get('new') != f.get('confirm') or len(f.get('new', '')) < 6: flash('New passwords must match and be at least 6 characters.', 'danger')
        else:
            u.pw = gh(f['new']); u.must_change = False; u.email = f.get('email', u.email)
            st = Staff.query.filter_by(user_id=u.id).first()
            if st: st.temp_pw = ''
            ResetRequest.query.filter_by(user_id=u.id).update({'temp_pw': ''})
            db.session.commit(); flash('Password updated. Use it the next time you log in.', 'success'); return redirect(back if bk else url_for('home'))
        return redirect(back)
    return render_template('account.html')
@app.route('/attended', methods=['GET', 'POST'])
@need()
def attended():
    u = me(); s = AttSession.query.filter_by(is_open=True).order_by(AttSession.date.desc()).first()
    cur = Attendance.query.filter_by(user_id=u.id, session_id=s.id).first() if s else None
    if request.method == 'POST' and s and not cur and s.date.weekday() == 6:
        st = 'Present' if request.form['status'] == 'Present' else 'Absent'; cid = request.form.get('church_id', type=int)
        if st == 'Present' and not cid: flash('Please select the church you attended.', 'danger')
        else:
            db.session.add(Attendance(user_id=u.id, session_id=s.id, status=st, church_id=cid if st == 'Present' else None)); db.session.commit()
            flash('Your attendance has been recorded and cannot be changed.', 'success'); return redirect(url_for('attended'))
    mine = db.session.query(AttSession.date, Attendance.status, Attendance.church_id).join(Attendance, Attendance.session_id == AttSession.id).filter(Attendance.user_id == u.id).order_by(AttSession.date.desc()).all()
    cn = {c.id: c.name for c in Church.query}
    return render_template('attended.html', s=s, cur=cur, mine=mine, churches=Church.query.all(), cn=cn)

def seen_now():
    mx = lambda M: db.session.query(db.func.coalesce(db.func.max(M.id), 0)).scalar()
    return dict(seen_ann=mx(Announcement), seen_srv=mx(Service), seen_ser=mx(Sermon))
def notif_items(u):
    out = []
    for a in ann_query(u).filter(Announcement.id > (u.seen_ann or 0)).order_by(Announcement.id.desc()): out.append(('megaphone', 'New ' + (a.kind or 'announcement'), a.title, '#announcements'))
    for x in Service.query.filter(Service.id > (u.seen_srv or 0)).order_by(Service.id.desc()): out.append(('calendar-event', 'New Mass / Service', f'{x.date} {x.time or ""} - {x.topic or ""}', '#services'))
    for x in Sermon.query.filter(Sermon.id > (u.seen_ser or 0)).order_by(Sermon.id.desc()): out.append(('book', 'New sermon', f'{x.title} ({x.language})', '#sermons'))
    for p in Prayer.query.filter(Prayer.user_id == u.id, Prayer.reply.isnot(None), Prayer.reply_seen.isnot(True)): out.append(('reply', 'Reply from the parish office', p.reply, '#contact'))
    return out
@app.route('/notifications')
@need()
def notifications():
    u = me(); items = notif_items(u)
    for p in Prayer.query.filter(Prayer.user_id == u.id, Prayer.reply.isnot(None)): p.reply_seen = True
    for k, v in seen_now().items(): setattr(u, k, v)
    db.session.commit(); return render_template('notifications.html', items=items)

# ---------- admin ----------
def stats():
    ch_ = {c.id: c.name for c in Church.query}; bar = defaultdict(lambda: {'Tithe': 0, 'Offering': 0}); line = defaultdict(lambda: defaultdict(float)); months = set()
    for c in Contribution.query:
        n = ch_.get(c.church_id, 'Unknown'); bar[n][c.kind] += c.amount or 0
        if c.date: m = c.date.strftime('%Y-%m'); months.add(m); line[n][m] += c.amount or 0
    months = sorted(months); att = []
    for s in AttSession.query.order_by(AttSession.date):
        att.append([s.date.isoformat(), Attendance.query.filter_by(session_id=s.id, status='Present').count(), Attendance.query.filter_by(session_id=s.id, status='Absent').count()])
    ac = defaultdict(int)
    for a in Attendance.query.filter_by(status='Present'): ac[ch_.get(a.church_id, 'Unknown')] += 1
    return dict(churches=list(bar), tithe=[bar[n]['Tithe'] for n in bar], offering=[bar[n]['Offering'] for n in bar], months=months,
                line={n: [line[n].get(m, 0) for m in months] for n in line}, att=att, ac_l=list(ac), ac_v=list(ac.values()))
@app.route('/admin')
@need('admin')
def dash():
    if me().role == 'staff': return redirect(url_for('a_list', key='sermons'))
    if me().role == 'cadmin': return redirect(url_for('c_dash'))
    cnt = [('Members', User.query.filter_by(role='user').count(), 'people', '/admin/users'), ('Churches', Church.query.count(), 'building', '/admin/churches'),
           ('Staff', Staff.query.count(), 'person-badge', '/admin/staff'), ('Sermons', Sermon.query.count(), 'book', '/admin/sermons'),
           ('New messages', Prayer.query.filter(Prayer.reply.is_(None)).count(), 'envelope-exclamation', '/admin/inbox'),
           ('Total KES', int(db.session.query(db.func.coalesce(db.func.sum(Contribution.amount), 0)).scalar()), 'cash-coin', '/admin/contributions')]
    return render_template('admin/dash.html', cnt=cnt, tips=tips()[0], resets=ResetRequest.query.filter_by(status='pending').count(), remits=Remittance.query.filter_by(status='pending').count(), nunread=Notice.query.filter_by(from_parish=False, is_read=False).count(), msgs=Prayer.query.order_by(Prayer.id.desc()).limit(5).all(), newu=User.query.order_by(User.id.desc()).limit(5).all())
@app.route('/admin/resets')
@need('admin')
def resets():
    guard('resets'); rows = db.session.query(ResetRequest, User).join(User, ResetRequest.user_id == User.id).order_by(ResetRequest.id.desc()).all()
    return render_template('admin/resets.html', rows=rows, wa=wa_link)
@app.route('/admin/resets/<int:id>/generate', methods=['POST'])
@need('admin')
def reset_gen(id):
    guard('resets'); r = db.get_or_404(ResetRequest, id); u = db.get_or_404(User, r.user_id); t = reset_user(u)
    flash(f'Temporary password for @{u.username}: {t}. Send it to the member (use the WhatsApp button). They must set a new password at login.', 'success'); return redirect(url_for('resets'))
@app.route('/admin/users/<int:id>/reset', methods=['POST'])
@need('admin')
def user_reset(id):
    guard('users'); u = db.get_or_404(User, id); t = reset_user(u)
    flash(f'Temporary password for @{u.username}: {t}. Send it to the member. They must set a new password at login.', 'success'); return redirect(url_for('a_list', key='users'))
def last_sunday(): t = date.today(); return t - timedelta((t.weekday() + 1) % 7)
def tips():
    today = date.today(); T = []; follow = []
    def add(level, icon, text, link=''): T.append(dict(level=level, icon=icon, text=text, link=link))
    sess = AttSession.query.order_by(AttSession.date.desc()).limit(4).all(); k = len(sess); sids = [x.id for x in sess]; members = User.query.filter_by(role='user').all()
    cn = {c.id: c.name for c in Church.query}
    if not k: add('info', 'check2-square', 'No attendance has been recorded yet. Open a Sunday under Attendance so members can mark Present or Absent.', '/admin/attendance')
    else:
        rows = db.session.query(Attendance.user_id, Attendance.status).filter(Attendance.session_id.in_(sids)).all()
        present = defaultdict(int); absent = defaultdict(int)
        for uid, st in rows: (present if st == 'Present' else absent)[uid] += 1
        last = dict(db.session.query(Attendance.user_id, db.func.max(AttSession.date)).join(AttSession, Attendance.session_id == AttSession.id).filter(Attendance.status == 'Present').group_by(Attendance.user_id).all())
        for u in members:
            if not present[u.id]:
                follow.append(dict(name=f'{u.first} {u.second}', phone=u.phone, church=cn.get(u.church_id, ''), state='Marked absent' if absent[u.id] else 'No response', last=last.get(u.id),
                                   wa=wa_link(u.phone, f'Hello {u.first}, we missed you at church and are praying for you. You are always welcome. God bless you.')))
        if follow: add('warning', 'person-x', f'{len(follow)} member(s) have not attended church in the last {k} Sunday(s). Please reach out to them.', '/admin/insights')
        if members and len({r[0] for r in rows}) / len(members) < .5: add('info', 'hand-index', 'Less than half of your members marked attendance recently. Remind them to use the Attended tab every Sunday.')
        rate = {}
        for cid, name in cn.items():
            ms = [u for u in members if u.church_id == cid]
            if ms: rate[name] = sum(present[u.id] for u in ms) / (len(ms) * k)
        if rate:
            n, r = min(rate.items(), key=lambda x: x[1])
            if r < .5: add('warning', 'building-down', f'{n} has the lowest attendance ({round(r * 100)}% of its members). Consider a visit, a mission or a church meeting there.', '/admin/analytics')
    d30, d60 = today - timedelta(30), today - timedelta(60); cur = defaultdict(float); prev = 0.0
    for c in Contribution.query.filter(Contribution.date >= d60):
        if c.date >= d30: cur[c.church_id] += c.amount or 0
        else: prev += c.amount or 0
    quiet = [n for cid, n in cn.items() if not cur.get(cid)]
    if quiet and Contribution.query.count(): add('warning', 'cash-coin', 'No tithes or offerings recorded in the last 30 days for: ' + ', '.join(quiet[:5]) + '. Record them or follow up.', '/admin/contributions')
    if prev and sum(cur.values()) < prev * .8: add('warning', 'graph-down-arrow', 'Total giving in the last 30 days is more than 20% lower than the 30 days before. Consider a stewardship talk.', '/admin/analytics')
    sm = Sermon.query.order_by(Sermon.date.desc()).first()
    if not sm or (sm.date and (today - sm.date).days > 14): add('info', 'book', 'No new sermon uploaded in the last 2 weeks. Upload the latest Sunday sermons.', '/admin/sermons')
    an = Announcement.query.order_by(Announcement.id.desc()).first()
    if not an or (an.created and (today - an.created).days > 14): add('info', 'megaphone', 'No announcement posted in the last 2 weeks. Keep members informed.', '/admin/announcements')
    if not Service.query.filter(Service.date >= today).count(): add('warning', 'calendar-x', 'There is no upcoming Mass or service on the schedule. Add the coming Sundays.', '/admin/services')
    n = Prayer.query.filter(Prayer.reply.is_(None), Prayer.created < today - timedelta(3)).count()
    if n: add('danger', 'envelope-exclamation', f'{n} message(s) have waited more than 3 days for a reply.', '/admin/inbox')
    n = Payment.query.filter_by(status='pending').count()
    if n: add('info', 'wallet2', f'{n} sermon payment(s) are pending. Check them if members complain.', '/admin/payments')
    n = ResetRequest.query.filter_by(status='pending').count()
    if n: add('warning', 'key', f'{n} member(s) asked for a password reset and need a temporary password.', '/admin/resets')
    n = Church.query.filter((Church.location.is_(None)) | (Church.location == '') | (Church.gmap.is_(None)) | (Church.gmap == '')).count()
    if n: add('info', 'geo-alt', f'{n} church(es) are missing a location or Google Map, so members cannot find them.', '/admin/churches')
    n = Ministry.query.filter((Ministry.image.is_(None)) | (Ministry.image == '')).count()
    if n: add('info', 'image', f'{n} ministry leader(s) have no photo yet.', '/admin/ministries')
    if me() and me().role in ('super', 'admin'):
        a30, b30 = today - timedelta(29), today; low = [r['name'] for r in giving(a30, b30) if not r['total']]
        if low and len(low) < len(cn) and Contribution.query.count(): add('info', 'calculator', 'No confirmed giving in the last 30 days from: ' + ', '.join(low[:5]) + '. See Giving Reports.', '/admin/giving')
    n = Notice.query.filter_by(from_parish=False, is_read=False).count()
    if n and me() and me().role == 'super': add('warning', 'chat-square-text', f'{n} unread notice(s) from church admins.', '/admin/notices')
    n = Remittance.query.filter_by(status='pending').count()
    if n: add('warning', 'box-arrow-in-down', f'{n} church tithe/offering report(s) are waiting for you to confirm the money has arrived.', '/admin/remittances')
    if me() and me().role == 'super':
        have = {u.church_id for u in User.query.filter_by(role='cadmin')}; no = [nm for cid, nm in cn.items() if cid not in have]
        if no: add('warning', 'person-gear', f'{len(no)} church(es) have no church admin: ' + ', '.join(no[:5]) + '. Assign one under Users & Privileges (role: Church admin).', '/admin/users')
    if Remittance.query.count():
        ls = last_sunday(); done = {r.church_id for r in Remittance.query.filter(Remittance.date == ls, Remittance.status != 'rejected')}; miss = [nm for cid, nm in cn.items() if cid not in done]
        if miss: add('info', 'cash-stack', f'No tithe/offering report for Sunday {ls} from: ' + ', '.join(miss[:5]) + '.', '/admin/remittances')
    n = User.query.filter(User.role == 'user', (User.email.is_(None)) | (User.email == '')).count()
    if n and members and n / len(members) > .5: add('info', 'envelope-at', f'{n} members have no email address, so they cannot get password reset emails. Encourage them to add one under My Profile.')
    if not T: add('success', 'emoji-smile', 'Everything looks healthy. Keep up the good work.')
    return T, sorted(follow, key=lambda x: x['state'] != 'No response'), k
@app.route('/admin/insights')
@need('admin')
def insights_page():
    if me().role == 'staff': abort(403)
    t, f, k = tips(); return render_template('admin/insights.html', tips=t, follow=f, k=k)
@app.route('/admin/remittances')
@need('admin')
def remits():
    guard('contributions'); cn = {c.id: c.name for c in Church.query}; us = {u.id: f'{u.first} {u.second}' for u in User.query.filter(User.role.in_(['cadmin', 'admin', 'super']))}
    rows = Remittance.query.order_by((Remittance.status != 'pending'), Remittance.date.desc(), Remittance.id.desc()).limit(200).all()
    return render_template('admin/remits.html', rows=rows, cn=cn, us=us)
@app.route('/admin/remittances/<int:id>/<act>', methods=['POST'])
@need('admin')
def remit_act(id, act):
    guard('contributions'); r = db.get_or_404(Remittance, id)
    if r.status != 'pending': flash('That report was already handled.', 'warning'); return redirect(url_for('remits'))
    if act == 'confirm':
        for kind, amt in (('Tithe', r.tithe), ('Offering', r.offering)):
            if (amt or 0) > 0: db.session.add(Contribution(church_id=r.church_id, kind=kind, amount=amt, date=r.date))
        r.status = 'confirmed'; flash('Marked as arrived. The tithe and offering are now recorded in the system.', 'success')
    elif act == 'reject': r.status = 'rejected'; flash('Report rejected. The church admin will see it.', 'success')
    else: abort(404)
    r.confirmed_on = date.today(); r.confirmed_by = f'{me().first} {me().second}'; db.session.commit(); lg.info('Remittance %s %s by user %s', r.id, r.status, me().id); return redirect(url_for('remits'))
@app.route('/admin/giving')
@need('admin')
def giving_report():
    guard('contributions'); t = date.today(); g = request.args
    p = g.get('period', 'month'); p = p if p in ('month', 'h1', 'h2', 'year', 'custom') else 'month'
    yr = g.get('year', type=int) or t.year; mo = g.get('month', type=int) or t.month; mo = mo if 1 <= mo <= 12 else t.month; yr = yr if 2000 <= yr <= 2100 else t.year
    d1 = g.get('from') or t.replace(day=1).isoformat(); d2 = g.get('to') or t.isoformat(); cid = g.get('church', type=int)
    rng = period_range(p, yr, mo, d1, d2)
    if not rng: flash('Please choose a valid period (the start date must not be after the end date).', 'danger'); rng = period_range('month', t.year, t.month, d1, d2)
    a, b, label = rng; rows = giving(a, b, cid); tt = sum(r['tithe'] for r in rows); to = sum(r['offering'] for r in rows)
    if g.get('csv'):
        out = io.StringIO(); w = csv.writer(out); w.writerow(['Church', 'Tithe', 'Offering', 'Total', 'Period', f'{a} to {b}'])
        for r in rows: w.writerow([r['name'], r['tithe'], r['offering'], r['total'], '', ''])
        w.writerow(['TOTAL', tt, to, tt + to]); return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=giving_report.csv'})
    return render_template('admin/giving.html', rows=rows, tt=tt, to=to, label=label, a=a, b=b, p=p, yr=yr, mo=mo, d1=d1, d2=d2, cid=cid, churches=Church.query.order_by(Church.name).all(),
                           months=[(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)], pending=db.session.query(db.func.coalesce(db.func.sum(Remittance.tithe + Remittance.offering), 0)).filter(Remittance.status == 'pending').scalar())
@app.route('/admin/notes')
@need('admin')
def notes_page():
    guard('notes'); q = request.args.get('q', '').strip(); qs = Note.query
    if q: qs = qs.filter(Note.title.contains(q) | Note.body.contains(q))
    return render_template('admin/notes.html', items=qs.order_by(Note.updated.desc()).all(), q=q)
# ----- church admin (own church only) -----
def cu():
    u = me()
    if not u or u.role != 'cadmin' or not u.church_id: abort(403)
    return u
def church_att(cid, limit=12):
    ms = User.query.filter(User.church_id == cid, User.role.in_(['user', 'cadmin'])).order_by(User.first, User.second).all()
    sess = AttSession.query.order_by(AttSession.date.desc()).limit(limit).all(); st = {}
    if ms and sess:
        for a in Attendance.query.filter(Attendance.user_id.in_([m.id for m in ms]), Attendance.session_id.in_([x.id for x in sess])): st[(a.user_id, a.session_id)] = a.status
    per = []
    for x in reversed(sess):
        p = sum(1 for m in ms if st.get((m.id, x.id)) == 'Present'); a = sum(1 for m in ms if st.get((m.id, x.id)) == 'Absent')
        per.append(dict(id=x.id, date=x.date.isoformat(), present=p, absent=a, none=len(ms) - p - a))
    return ms, sess, st, per
def church_tips(u):
    cid = u.church_id; today = date.today(); T = []; follow = []; ms, sess, st, per = church_att(cid, 12); k = min(len(sess), 4)
    def add(level, icon, text, link=''): T.append(dict(level=level, icon=icon, text=text, link=link))
    wa = lambda m: wa_link(m.phone, f'Hello {m.first}, we missed you at church and are praying for you. You are always welcome. God bless you.')
    last = {}
    for (uid, sid), s_ in st.items():
        if s_ == 'Present':
            d = next((x.date for x in sess if x.id == sid), None)
            if d and (uid not in last or d > last[uid]): last[uid] = d
    if not ms: add('info', 'people', 'No members have registered for your church yet. Invite parishioners to create an account and pick your church.')
    elif not sess: add('info', 'check2-square', 'The parish has not opened attendance yet, so there is nothing to compare. Ask the parish office to open a Sunday.')
    else:
        for m in ms:
            if not any(st.get((m.id, x.id)) == 'Present' for x in sess[:k]):
                follow.append(dict(name=f'{m.first} {m.second}', phone=m.phone, state='Marked absent' if any(st.get((m.id, x.id)) == 'Absent' for x in sess[:k]) else 'No response', last=last.get(m.id), wa=wa(m)))
        if follow: add('warning', 'person-x', f'{len(follow)} of your members have not attended church in the last {k} Sunday(s). Visit or call them.', '/admin/church/insights')
        if len(sess) >= 3:
            n = sum(1 for m in ms if not any(st.get((m.id, x.id)) == 'Present' for x in sess[:3]))
            if n: add('danger', 'exclamation-triangle', f'{n} member(s) have missed 3 Sundays in a row. This is the time for a pastoral visit.', '/admin/church/insights')
        cur = per[-1]
        if (cur['present'] + cur['absent']) / max(len(ms), 1) < .5: add('info', 'hand-index', 'Fewer than half of your members marked attendance on the latest Sunday. Remind them to use the Attended tab after Mass.')
        if len(per) >= 2 and per[-2]['present'] and cur['present'] < per[-2]['present'] * .8: add('warning', 'graph-down-arrow', f"Attendance fell from {per[-2]['present']} to {cur['present']} on the latest Sunday. Find out why and encourage members.", '/admin/church/attendance')
        if len(per) >= 2 and cur['present'] > per[-2]['present']: add('success', 'graph-up-arrow', f"Attendance grew from {per[-2]['present']} to {cur['present']} on the latest Sunday. Well done, keep encouraging them.")
    ls = last_sunday()
    if not Remittance.query.filter(Remittance.church_id == cid, Remittance.date == ls, Remittance.status != 'rejected').count(): add('warning', 'cash-coin', f'You have not recorded tithes and offerings for Sunday {ls}. Record them and take them to the parish.', '/admin/church/contributions')
    n = Remittance.query.filter(Remittance.church_id == cid, Remittance.status == 'pending', Remittance.created < datetime.now() - timedelta(3)).count()
    if n: add('warning', 'hourglass-split', f'{n} report(s) have waited over 3 days for the parish to confirm. Make sure the money has been delivered to the parish office.', '/admin/church/contributions')
    n = Remittance.query.filter(Remittance.church_id == cid, Remittance.status == 'rejected', Remittance.date >= today - timedelta(60)).count()
    if n: add('danger', 'x-octagon', f'{n} of your recent reports were rejected by the parish. Check the amounts with the parish office.', '/admin/church/contributions')
    c30, c60 = 0.0, 0.0
    for c in Contribution.query.filter(Contribution.church_id == cid, Contribution.date >= today - timedelta(60)):
        if c.date >= today - timedelta(30): c30 += c.amount or 0
        else: c60 += c.amount or 0
    if c60 and c30 < c60 * .8: add('warning', 'graph-down-arrow', 'Confirmed giving in the last 30 days is more than 20% lower than the 30 days before. Consider a stewardship talk.', '/admin/church/contributions')
    n = sum(1 for m in ms if not m.email)
    if ms and n: add('info', 'envelope-at', f'{n} member(s) have no email address. Ask them to add one under My Profile so they can reset their own password.')
    n = sum(1 for m in ms if (m.ministry or 'Other') == 'Other')
    if ms and n: add('info', 'people', f'{n} member(s) have not joined a ministry. Encourage them to join the Choir, Youth, CMA or CWA.')
    if len(ms) >= 10 and sum(1 for m in ms if m.ministry == 'Youth') / len(ms) < .1: add('info', 'stars', 'Very few members are in the Youth ministry. Plan a youth Sunday or a youth meeting to bring them in.')
    n = Notice.query.filter_by(church_id=cid, from_parish=True, is_read=False).count()
    if n: add('warning', 'chat-square-text', f'You have {n} unread notice(s) from the parish office.', '/admin/church/notices')
    n = db.session.query(ResetRequest).join(User, ResetRequest.user_id == User.id).filter(ResetRequest.status == 'pending', User.church_id == cid, User.role == 'user').count()
    if n: add('warning', 'key', f'{n} member(s) asked for a password reset. Generate a temporary password for them.', '/admin/church/members')
    la = Announcement.query.filter_by(church_id=cid).order_by(Announcement.id.desc()).first()
    if not Ministry.query.filter_by(church_id=cid).count(): add('info', 'people', 'Your church has no ministries listed yet. Add your priest, chairperson, choir and other leaders so everyone can see them.', '/admin/church/ministries')
    if not la or (la.created and (today - la.created).days > 14): add('info', 'megaphone', 'You have not posted an announcement for your church in the last 2 weeks. Keep your members informed.', '/admin/church/announcements')
    if not T: add('success', 'emoji-smile', 'Everything looks healthy in your church. Keep up the good work.')
    return T, sorted(follow, key=lambda x: x['state'] != 'No response'), k
def church_page(**kw):
    u = cu(); ch_ = db.session.get(Church, u.church_id); return render_template(kw.pop('t'), ch=ch_, **kw)
@app.route('/admin/church')
@need('admin')
def c_dash():
    u = cu(); ms, sess, st, per = church_att(u.church_id); t, f, k = church_tips(u); cur = per[-1] if per else None
    giving = db.session.query(db.func.coalesce(db.func.sum(Contribution.amount), 0)).filter(Contribution.church_id == u.church_id, Contribution.date >= date.today() - timedelta(30)).scalar()
    pend = Remittance.query.filter_by(church_id=u.church_id, status='pending').count()
    return church_page(t='admin/c_dash.html', n=len(ms), cur=cur, per=per, tips=t, giving=int(giving), pend=pend, unread=Notice.query.filter_by(church_id=u.church_id, from_parish=True, is_read=False).count())
@app.route('/admin/church/members')
@need('admin')
def c_members():
    u = cu(); ms, sess, st, per = church_att(u.church_id); q = request.args.get('q', '').strip().lower(); k = min(len(sess), 4); rows = []
    for m in ms:
        if q and q not in f'{m.first} {m.second} {m.phone} {m.ministry}'.lower(): continue
        hist = [st.get((m.id, x.id)) for x in sess[:k]]; rows.append(dict(m=m, att=sum(1 for h in hist if h == 'Present'), hist=hist))
    ask = {r.user_id for r in ResetRequest.query.filter_by(status='pending')}
    for r_ in rows: r_['ask'] = r_['m'].id in ask
    return church_page(t='admin/c_members.html', rows=rows, k=k, q=q, wa=wa_link, total=len(ms), nask=sum(1 for r_ in rows if r_['ask']))
@app.route('/admin/church/attendance')
@need('admin')
def c_attendance():
    u = cu(); ms, sess, st, per = church_att(u.church_id); sid = request.args.get('s', type=int); sel = next((x for x in sess if x.id == sid), sess[0] if sess else None)
    cur = next((p for p in per if sel and p['id'] == sel.id), None)
    rows = [(m, st.get((m.id, sel.id)) if sel else None) for m in ms]
    return church_page(t='admin/c_attendance.html', sess=sess, sel=sel, cur=cur, per=per, rows=rows, can_mark=bool(sel and sel.is_open))
@app.route('/admin/church/insights')
@need('admin')
def c_insights():
    u = cu(); t, f, k = church_tips(u); return church_page(t='admin/c_insights.html', tips=t, follow=f, k=k)
@app.route('/admin/church/add-member', methods=['GET', 'POST'])
@need('admin')
def c_add_member():
    u = cu()
    if request.method == 'POST':
        f = request.form; ph = norm_phone(f.get('phone')); first = f.get('first', '').strip(); second = f.get('second', '').strip(); em = f.get('email', '').strip()
        if not first or not second: flash('Please enter the first and second name.', 'danger')
        elif not ph: flash('Enter a valid phone number, e.g. 0712345678.', 'danger')
        elif find_user(ph): flash('That phone number is already registered.', 'danger')
        else:
            tmp = ''.join(secrets.choice(string.digits) for _ in range(6))
            m = User(first=first, second=second, username=ph, phone=ph, email=em, church_id=u.church_id, ministry=f.get('ministry') if f.get('ministry') in MINISTRIES else 'Other', pw=gh(tmp), role='user', must_change=True, added_by=u.id, **seen_now())
            db.session.add(m); db.session.commit(); lg.info('Church admin %s added member %s', u.id, m.id)
            return church_page(t='admin/c_cred.html', m=m, pw=tmp, what='added')
    added = User.query.filter(User.church_id == u.church_id, User.added_by.isnot(None)).order_by(User.id.desc()).all()
    return church_page(t='admin/c_add_member.html', ministries=MINISTRIES, added=added)
@app.route('/admin/church/members/<int:id>/reset', methods=['POST'])
@need('admin')
def c_reset(id):
    u = cu(); m = db.get_or_404(User, id)
    if m.church_id != u.church_id or m.role != 'user': abort(403)
    t = reset_user(m); return church_page(t='admin/c_cred.html', m=m, pw=t, what='reset')
@app.route('/admin/church/attendance/mark', methods=['POST'])
@need('admin')
def c_mark():
    u = cu(); f = request.form; m = db.get_or_404(User, f.get('member', type=int) or 0); s_ = db.get_or_404(AttSession, f.get('session', type=int) or 0)
    if m.church_id != u.church_id or m.added_by is None or not s_.is_open or s_.date.weekday() != 6 or f.get('status') not in ('Present', 'Absent'): abort(403)
    if not Attendance.query.filter_by(user_id=m.id, session_id=s_.id).first():
        db.session.add(Attendance(user_id=m.id, session_id=s_.id, status=f['status'], church_id=u.church_id if f['status'] == 'Present' else None)); db.session.commit(); flash(f'{m.first} marked {f["status"]}. This cannot be changed.', 'success')
    return redirect(url_for('c_attendance', s=s_.id))
@app.route('/admin/church/ministries', methods=['GET', 'POST'])
@need('admin')
def c_min():
    u = cu(); f = request.form; eid = request.args.get('edit', type=int); m = db.session.get(Ministry, eid) if eid else None
    if m and m.church_id != u.church_id: abort(403)
    if request.method == 'POST':
        fn = save_img(request.files.get('image')); name = f.get('name', '').strip()[:120]; cat = f.get('category') if f.get('category') in CATS else 'Other'
        if fn is False: flash('Please upload a photo (JPG, PNG, WEBP or GIF).', 'danger')
        elif not name: flash('Please enter the name.', 'danger')
        else:
            m = m or Ministry(church_id=u.church_id); m.category = cat; m.role = f.get('role', '').strip()[:80] or cat; m.name = name; m.description = f.get('description', '').strip()
            try: m.ord = int(f.get('ord') or 0)
            except ValueError: m.ord = 0
            if fn: m.image = fn
            elif 'remove_image' in f: m.image = None
            db.session.add(m); db.session.commit(); flash('Saved. Everyone using the website can now see it under Church Ministries.', 'success'); return redirect(url_for('c_min'))
    rows = Ministry.query.filter_by(church_id=u.church_id).order_by(Ministry.ord, Ministry.id).all()
    return church_page(t='admin/c_ministries.html', rows=rows, m=m, cats=CATS)
@app.route('/admin/church/ministries/<int:id>/delete', methods=['POST'])
@need('admin')
def c_min_del(id):
    u = cu(); m = db.get_or_404(Ministry, id)
    if m.church_id != u.church_id: abort(403)
    db.session.delete(m); db.session.commit(); flash('Deleted.', 'success'); return redirect(url_for('c_min'))
@app.route('/admin/church/announcements', methods=['GET', 'POST'])
@need('admin')
def c_ann():
    u = cu(); f = request.form; eid = request.args.get('edit', type=int); a = db.session.get(Announcement, eid) if eid else None
    if a and a.church_id != u.church_id: abort(403)
    if request.method == 'POST':
        fn = save_doc(request.files.get('file')); title = f.get('title', '').strip()[:200]; body = f.get('body', '').strip()
        if fn is False: flash('Only PDF or Word (.doc, .docx) files can be attached.', 'danger')
        elif not title or not (body or fn or (a and a.file)): flash('Please write a title and a message, or attach a file.', 'danger')
        else:
            a = a or Announcement(church_id=u.church_id); a.title = title; a.body = body; a.kind = 'Event' if f.get('kind') == 'Event' else 'Announcement'
            if fn: a.file = fn
            if 'remove_file' in f and not fn: a.file = None
            db.session.add(a); db.session.commit(); flash('Posted. Your church members can now see it.', 'success'); return redirect(url_for('c_ann'))
    rows = Announcement.query.filter_by(church_id=u.church_id).order_by(Announcement.id.desc()).limit(50).all()
    return church_page(t='admin/c_announce.html', rows=rows, a=a)
@app.route('/admin/church/announcements/<int:id>/delete', methods=['POST'])
@need('admin')
def c_ann_del(id):
    u = cu(); a = db.get_or_404(Announcement, id)
    if a.church_id != u.church_id: abort(403)
    db.session.delete(a); db.session.commit(); flash('Deleted.', 'success'); return redirect(url_for('c_ann'))
@app.route('/admin/church/notices', methods=['GET', 'POST'])
@need('admin')
def c_notice():
    u = cu(); f = request.form
    if request.method == 'POST':
        fn = save_doc(request.files.get('file')); subj = f.get('subject', '').strip()[:200]; body = f.get('body', '').strip()
        if fn is False: flash('Only PDF or Word (.doc, .docx) files can be attached.', 'danger')
        elif not subj or not (body or fn): flash('Please write a subject and a message, or attach a file.', 'danger')
        else: db.session.add(Notice(church_id=u.church_id, sender_id=u.id, from_parish=False, subject=subj, body=body, file=fn or None, is_read=False)); db.session.commit(); flash('Sent to the parish office.', 'success')
        return redirect(url_for('c_notice'))
    items = Notice.query.filter_by(church_id=u.church_id).order_by(Notice.id.desc()).limit(100).all()
    us = {x.id: f'{x.first} {x.second}' for x in User.query.filter(User.role.in_(['cadmin', 'super']))}
    unread = [x for x in items if x.from_parish and not x.is_read]
    for x in unread: x.is_read = True
    db.session.commit()
    return church_page(t='admin/c_notice.html', items=items, us=us, new_ids={x.id for x in unread})
@app.route('/admin/church/contributions', methods=['GET', 'POST'])
@need('admin')
def c_contrib():
    u = cu()
    if request.method == 'POST':
        f = request.form
        try: d = date.fromisoformat(f['date']); ti = float(f.get('tithe') or 0); of = float(f.get('offering') or 0)
        except Exception: flash('Please fill in a valid date and amounts.', 'danger'); return redirect(url_for('c_contrib'))
        if d.weekday() != 6 or d > date.today(): flash('Choose a Sunday that has already come (today or earlier).', 'danger')
        elif ti < 0 or of < 0 or (ti + of) <= 0 or ti > 1e8 or of > 1e8: flash('Enter a tithe and/or offering amount greater than zero.', 'danger')
        elif Remittance.query.filter(Remittance.church_id == u.church_id, Remittance.date == d, Remittance.status != 'rejected').first(): flash('A report for that Sunday already exists. Delete the pending one first if you need to change it.', 'danger')
        else:
            db.session.add(Remittance(church_id=u.church_id, user_id=u.id, date=d, tithe=ti, offering=of, note=f.get('note', '').strip()[:255])); db.session.commit()
            flash('Recorded. It will count in the system only after the parish confirms the money has arrived.', 'success')
        return redirect(url_for('c_contrib'))
    rows = Remittance.query.filter_by(church_id=u.church_id).order_by(Remittance.date.desc(), Remittance.id.desc()).limit(60).all()
    return church_page(t='admin/c_contrib.html', rows=rows, last=last_sunday(), confirmed=sum((r.tithe or 0) + (r.offering or 0) for r in rows if r.status == 'confirmed'))
@app.route('/admin/church/contributions/<int:id>/delete', methods=['POST'])
@need('admin')
def c_contrib_del(id):
    u = cu(); r = db.get_or_404(Remittance, id)
    if r.church_id != u.church_id or r.status != 'pending': abort(403)
    db.session.delete(r); db.session.commit(); flash('Deleted.', 'success'); return redirect(url_for('c_contrib'))
@app.route('/admin/notices', methods=['GET', 'POST'])
@need('admin')
def notices_page():
    guard('notices'); f = request.form
    if request.method == 'POST':
        fn = save_doc(request.files.get('file')); subj = f.get('subject', '').strip()[:200]; body = f.get('body', '').strip()
        if fn is False: flash('Only PDF or Word (.doc, .docx) files can be attached.', 'danger')
        elif not subj or not (body or fn): flash('Please write a subject and a message, or attach a file.', 'danger')
        else:
            ids = [c.id for c in Church.query] if f.get('church') == 'all' else [int(f['church'])] if (f.get('church') or '').isdigit() and db.session.get(Church, int(f['church'])) else []
            if not ids: flash('Please choose a church.', 'danger')
            else:
                for cid in ids: db.session.add(Notice(church_id=cid, sender_id=me().id, from_parish=True, subject=subj, body=body, file=fn or None, is_read=False))
                db.session.commit(); flash(f'Notice sent to {len(ids)} church(es).', 'success')
        return redirect(url_for('notices_page', church=request.args.get('church')))
    cid = request.args.get('church', type=int); q = Notice.query
    if cid: q = q.filter_by(church_id=cid)
    items = q.order_by(Notice.id.desc()).limit(200).all()
    for x in items:
        if not x.from_parish and not x.is_read: x.is_read = True
    db.session.commit()
    us = {u.id: f'{u.first} {u.second}' for u in User.query.filter(User.role.in_(['cadmin', 'super']))}
    return render_template('admin/notices.html', items=items, churches=Church.query.all(), cid=cid, us=us, cn={c.id: c.name for c in Church.query})
@app.route('/admin/notices/<int:id>/delete', methods=['POST'])
@need('admin')
def notice_del(id): guard('notices'); db.session.delete(db.get_or_404(Notice, id)); db.session.commit(); flash('Deleted.', 'success'); return redirect(url_for('notices_page'))
@app.route('/admin/profile')
@need('admin')
def a_profile(): return render_template('admin/profile.html')
@app.route('/admin/analytics')
@need('admin')
def analytics():
    if me().role == 'staff': abort(403)
    return render_template('admin/analytics.html', d=stats())
@app.route('/admin/inbox')
@need('admin')
def inbox(): guard('prayers'); return render_template('admin/inbox.html', items=Prayer.query.order_by(Prayer.id.desc()).all())
@app.route('/admin/inbox/<int:id>/reply', methods=['POST'])
@need('admin')
def reply(id):
    guard('prayers'); m = db.get_or_404(Prayer, id); m.reply = request.form['reply']; m.replied_on = date.today(); db.session.commit()
    ok = send_mail(m.email, 'Reply from ' + settings()['church_name'], f'Dear {m.name},\n\n{m.reply}\n\n-- {settings()["church_name"]}') if m.email else False
    flash('Reply saved' + (' and emailed.' if ok else '. (Not emailed: no email on file or SMTP not set; the member sees it under Contact.)'), 'success'); return redirect(url_for('inbox'))
@app.route('/admin/inbox/<int:id>/delete', methods=['POST'])
@need('admin')
def inbox_del(id): guard('prayers'); db.session.delete(db.get_or_404(Prayer, id)); db.session.commit(); return redirect(url_for('inbox'))
@app.route('/admin/logo', methods=['GET', 'POST'])
@need('admin')
def a_logo():
    guard('settings')
    if request.method == 'POST':
        fl = request.files.get('logo')
        if 'remove' in request.form: db.session.merge(Setting(k='logo', v='')); flash('Logo removed. The default cross is shown again.', 'success')
        elif fl and fl.filename and fl.mimetype.startswith('image/'):
            v = f"{int(time.time())}_{secure_filename(fl.filename)}"; fl.save(os.path.join(UP, v)); db.session.merge(Setting(k='logo', v=v)); flash('Logo updated.', 'success')
        else: flash('Please choose an image file (PNG, JPG, SVG).', 'danger'); return redirect(url_for('a_logo'))
        db.session.commit(); return redirect(url_for('a_logo'))
    return render_template('admin/logo.html')
@app.route('/admin/payments')
@need('admin')
def payments():
    guard('payments')
    rows = db.session.query(Payment, User, Sermon).join(User, Payment.user_id == User.id).join(Sermon, Payment.sermon_id == Sermon.id).order_by(Payment.id.desc()).all()
    return render_template('admin/payments.html', rows=rows)
@app.route('/admin/payments/<int:id>/<act>', methods=['POST'])
@need('admin')
def pay_act(id, act):
    guard('payments'); p = db.get_or_404(Payment, id); p.status = {'approve': 'approved', 'reject': 'rejected'}.get(act) or abort(404); db.session.commit()
    flash('Payment ' + p.status + '.', 'success'); return redirect(url_for('payments'))
@app.route('/admin/settings', methods=['GET', 'POST'])
@need('admin')
def a_settings():
    guard('settings')
    if request.method == 'POST':
        for f in SET_FIELDS:
            n = f[0]
            if f[2] == 'file':
                fl = request.files.get(n)
                if not (fl and fl.filename): continue
                v = f"{int(time.time())}_{secure_filename(fl.filename)}"; fl.save(os.path.join(UP, v))
            else: v = request.form.get(n, '')
            db.session.merge(Setting(k=n, v=v))
        db.session.commit(); flash('Church information updated.', 'success'); return redirect(url_for('a_settings'))
    return render_template('admin/form.html', title='Church Information', fields=SET_FIELDS, o=type('O', (), settings())(), churches=[], back=None)
def fill(o, fields):
    for f in fields:
        n, t = f[0], f[2]
        if t in ('file', 'photo'):
            d = request.form.get(n + '_data', '')
            if t == 'photo' and d.startswith('data:image'):
                v = f"{int(time.time())}_face.jpg"; open(os.path.join(UP, v), 'wb').write(base64.b64decode(d.split(',', 1)[1])); setattr(o, n, v); continue
            fl = request.files.get(n)
            if fl and fl.filename: v = f"{int(time.time())}_{secure_filename(fl.filename)}"; fl.save(os.path.join(UP, v)); setattr(o, n, v)
        elif t == 'bool': setattr(o, n, n in request.form)
        elif t == 'num': setattr(o, n, float(request.form.get(n) or 0))
        elif t == 'date': setattr(o, n, date.fromisoformat(request.form[n]) if request.form.get(n) else None)
        elif t == 'church': setattr(o, n, int(request.form[n]) if request.form.get(n) else None)
        else: setattr(o, n, request.form.get(n, '').strip())
def after_save(key, o):
    if key != 'staff': return
    u = db.session.get(User, o.user_id) if o.user_id else None
    if not u:
        tmp = ''.join(secrets.choice(string.digits) for _ in range(6)); nm = o.name.split(' ', 1)
        u = User(first=nm[0], second=nm[1] if len(nm) > 1 else '', username=o.phone, phone=o.phone, email=o.email, role='staff', pw=gh(tmp), must_change=True, ministry='Other')
        db.session.add(u); db.session.flush(); o.user_id = u.id; o.temp_pw = tmp
        send_mail(o.email, 'Your staff login', f'Hello {o.name},\n\nUsername: {o.phone}\nTemporary password: {tmp}\n\nYou will be asked to set a new password at first login.')
        flash(f'Staff saved. Login username: {o.phone} | Temporary password: {tmp} (also kept in the Staff list).', 'success')
    u.perms = o.perms; u.phone = o.phone; u.email = o.email; db.session.commit()
@app.route('/admin/<key>')
@need('admin')
def a_list(key):
    guard(key); M, title, fields, opt = CRUD[key]
    return render_template('admin/list.html', key=key, title=title, fields=fields, opt=opt, items=M.query.order_by(M.id.desc()).all())
@app.route('/admin/<key>/new', methods=['GET', 'POST'])
@app.route('/admin/<key>/<int:id>/edit', methods=['GET', 'POST'])
@need('admin')
def a_edit(key, id=None):
    guard(key); M, title, fields, opt = CRUD[key]
    if opt.get('no_new') and not id: abort(404)
    o = db.get_or_404(M, id) if id else M()
    if request.method == 'POST':
        fill(o, fields)
        if key == 'attendance' and (not o.date or o.date.weekday() != 6): db.session.rollback(); flash('Attendance can only be set for a Sunday date.', 'danger')
        elif key == 'users' and o.role == 'cadmin' and not o.church_id: db.session.rollback(); flash('Please select the church this church admin will manage.', 'danger')
        else:
            db.session.add(o); db.session.commit(); after_save(key, o)
            if key != 'staff': flash('Saved.', 'success')
            return redirect(url_for('a_list', key=key))
    return render_template('admin/form.html', title=title, fields=fields, o=o, churches=Church.query.all(), back=url_for('a_list', key=key))
@app.route('/admin/<key>/<int:id>/delete', methods=['POST'])
@need('admin')
def a_del(key, id):
    guard(key); o = db.get_or_404(CRUD[key][0], id)
    if key == 'staff' and o.user_id:
        u = db.session.get(User, o.user_id)
        if u: db.session.delete(u)
    db.session.delete(o); db.session.commit(); flash('Deleted.', 'success'); return redirect(url_for('a_list', key=key))
@app.route('/admin/report/<kind>.csv')
@need('admin')
def report(kind):
    if me().role == 'staff': abort(403)
    cn = {c.id: c.name for c in Church.query}
    if kind == 'contributions': rows = [['Church', 'Type', 'Amount', 'Date']] + [[cn.get(c.church_id, ''), c.kind, c.amount, c.date] for c in Contribution.query]
    elif kind == 'attendance': rows = [['Sunday', 'Member', 'Phone', 'Status', 'Church attended']] + [[s.date, f'{u.first} {u.second}', u.phone, a.status, cn.get(a.church_id, '')] for a, s, u in db.session.query(Attendance, AttSession, User).join(AttSession, Attendance.session_id == AttSession.id).join(User, Attendance.user_id == User.id)]
    elif kind == 'users': rows = [['Name', 'Username', 'Phone', 'Email', 'Ministry']] + [[f'{u.first} {u.second}', u.username, u.phone, u.email, u.ministry] for u in User.query]
    elif kind == 'followup': rows = [['Name', 'Phone', 'Church', 'Status', 'Last present']] + [[x['name'], x['phone'], x['church'], x['state'], x['last'] or ''] for x in tips()[1]]
    else: abort(404)
    out = io.StringIO(); csv.writer(out).writerows(rows)
    return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment;filename={kind}.csv'})

def ensure_columns():
    from sqlalchemy import inspect, text
    insp = inspect(db.engine); tabs = insp.get_table_names()
    for t, c, typ in [('user', 'seen_ann', 'INTEGER DEFAULT 0'), ('user', 'seen_srv', 'INTEGER DEFAULT 0'), ('user', 'seen_ser', 'INTEGER DEFAULT 0'), ('prayer', 'reply_seen', 'BOOLEAN DEFAULT 0'), ('user', 'photo', 'VARCHAR(255)'), ('user', 'added_by', 'INTEGER'), ('announcement', 'church_id', 'INTEGER'), ('sermon', 'price', 'FLOAT DEFAULT 0'), ('payment', 'ext_ref', 'VARCHAR(60)'), ('payment', 'reference', 'VARCHAR(60)')]:
        if t in tabs and c not in [x['name'] for x in insp.get_columns(t)]: db.session.execute(text(f'ALTER TABLE `{t}` ADD COLUMN {c} {typ}'))
    db.session.commit()
def ensure_indexes():
    from sqlalchemy import inspect
    insp = inspect(db.engine)
    for t in db.metadata.tables.values():
        have = {i['name'] for i in insp.get_indexes(t.name)}
        for ix in t.indexes:
            if ix.name not in have:
                try: ix.create(db.engine)
                except Exception as e: lg.warning('Index skipped %s: %s', ix.name, e)
def init():
    db.create_all(); ensure_columns(); ensure_indexes()
    if not Church.query.first(): db.session.add(Church(name='Matuu Parish (Main Church)', location='Matuu Town'))
    if not User.query.filter_by(role='super').first():
        db.session.add(User(first='Parish', second='Admin', username='admin', pw=gh('admin123'), role='super', ministry='Other'))
    db.session.commit()
if __name__ == '__main__':
    with app.app_context(): init()
    app.run(debug=os.getenv('FLASK_DEBUG') == '1')
