from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os, uuid, random, string

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'discord-clone-secret-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///discord.db').replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def save_upload(file, subfolder):
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        fname = f"{uuid.uuid4().hex}.{ext}"
        path = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
        os.makedirs(path, exist_ok=True)
        file.save(os.path.join(path, fname))
        return f"{subfolder}/{fname}"
    return None

# ── Models ──────────────────────────────────────────────────────────────────

friends = db.Table('friends',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('friend_id', db.Integer, db.ForeignKey('user.id'))
)

server_members = db.Table('server_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('server_id', db.Integer, db.ForeignKey('server.id'))
)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    discriminator = db.Column(db.String(4), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    avatar = db.Column(db.String(200), default=None)
    status = db.Column(db.String(20), default='online')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    friend_code = db.Column(db.String(20), unique=True)
    friends_list = db.relationship('User', secondary=friends,
        primaryjoin=(friends.c.user_id == id),
        secondaryjoin=(friends.c.friend_id == id),
        backref='friend_of')

    def tag(self):
        return f"{self.username}#{self.discriminator}"

class FriendRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])

class Server(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(200), default=None)
    invite_code = db.Column(db.String(20), unique=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    owner = db.relationship('User', backref='owned_servers')
    members = db.relationship('User', secondary=server_members, backref='servers')
    channels = db.relationship('Channel', backref='server', lazy=True, cascade='all, delete-orphan')

class Channel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), default='text')
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'))
    messages = db.relationship('Message', backref='channel', lazy=True, cascade='all, delete-orphan')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'), nullable=True)
    dm_room = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship('User')

# ── Helpers ──────────────────────────────────────────────────────────────────

def gen_discriminator():
    return ''.join(random.choices(string.digits, k=4))

def gen_invite():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def gen_friend_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

def current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def dm_room_id(a, b):
    return f"dm_{min(a,b)}_{max(a,b)}"

# ── Auth ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    u = current_user()
    if u:
        return redirect(url_for('app_home'))
    return render_template('landing.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        d = request.form
        if User.query.filter_by(email=d['email']).first():
            return render_template('auth.html', error="Email déjà utilisé", mode='register')
        if User.query.filter_by(username=d['username']).first():
            return render_template('auth.html', error="Nom d'utilisateur pris", mode='register')
        u = User(
            username=d['username'],
            discriminator=gen_discriminator(),
            email=d['email'],
            password=generate_password_hash(d['password']),
            friend_code=gen_friend_code()
        )
        db.session.add(u)
        db.session.commit()
        session['user_id'] = u.id
        return redirect(url_for('app_home'))
    return render_template('auth.html', mode='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        d = request.form
        u = User.query.filter_by(email=d['email']).first()
        if not u or not check_password_hash(u.password, d['password']):
            return render_template('auth.html', error="Identifiants incorrects", mode='login')
        session['user_id'] = u.id
        return redirect(url_for('app_home'))
    return render_template('auth.html', mode='login')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

# ── App ───────────────────────────────────────────────────────────────────────

@app.route('/app')
def app_home():
    u = current_user()
    if not u: return redirect(url_for('login'))
    pending = FriendRequest.query.filter_by(receiver_id=u.id, status='pending').all()
    return render_template('app.html', user=u, view='friends', pending=pending)

@app.route('/app/server/<int:sid>')
def view_server(sid):
    u = current_user()
    if not u: return redirect(url_for('login'))
    server = Server.query.get_or_404(sid)
    if u not in server.members and server.owner_id != u.id:
        return redirect(url_for('app_home'))
    channel = server.channels[0] if server.channels else None
    return render_template('app.html', user=u, view='server', server=server, channel=channel)

@app.route('/app/server/<int:sid>/channel/<int:cid>')
def view_channel(sid, cid):
    u = current_user()
    if not u: return redirect(url_for('login'))
    server = Server.query.get_or_404(sid)
    channel = Channel.query.get_or_404(cid)
    messages = Message.query.filter_by(channel_id=cid).order_by(Message.created_at).all()
    pending = FriendRequest.query.filter_by(receiver_id=u.id, status='pending').all()
    return render_template('app.html', user=u, view='channel', server=server,
                           channel=channel, messages=messages, pending=pending)

@app.route('/app/dm/<int:uid>')
def view_dm(uid):
    u = current_user()
    if not u: return redirect(url_for('login'))
    friend = User.query.get_or_404(uid)
    room = dm_room_id(u.id, uid)
    messages = Message.query.filter_by(dm_room=room).order_by(Message.created_at).all()
    pending = FriendRequest.query.filter_by(receiver_id=u.id, status='pending').all()
    return render_template('app.html', user=u, view='dm', friend=friend,
                           messages=messages, room=room, pending=pending)

# ── Server CRUD ───────────────────────────────────────────────────────────────

@app.route('/api/server/create', methods=['POST'])
def create_server():
    u = current_user()
    if not u: return jsonify({'error': 'auth'}), 401
    name = request.form.get('name', '').strip()
    if not name: return jsonify({'error': 'Nom requis'}), 400
    icon_path = save_upload(request.files.get('icon'), 'servers')
    s = Server(name=name, icon=icon_path, owner_id=u.id, invite_code=gen_invite(), is_public=bool(request.form.get('public')))
    s.members.append(u)
    db.session.add(s)
    db.session.flush()
    for ch_name in ['général', 'annonces', 'off-topic']:
        db.session.add(Channel(name=ch_name, server_id=s.id))
    db.session.add(Channel(name='Voix générale', type='voice', server_id=s.id))
    db.session.commit()
    return jsonify({'id': s.id, 'redirect': url_for('view_server', sid=s.id)})

@app.route('/api/server/join', methods=['POST'])
def join_server():
    u = current_user()
    if not u: return jsonify({'error': 'auth'}), 401
    code = request.json.get('code', '').strip()
    s = Server.query.filter_by(invite_code=code).first()
    if not s: return jsonify({'error': 'Code invalide'}), 404
    if u not in s.members: s.members.append(u)
    db.session.commit()
    return jsonify({'redirect': url_for('view_server', sid=s.id)})

@app.route('/api/server/search')
def search_servers():
    q = request.args.get('q', '').strip()
    servers = Server.query.filter(Server.is_public == True, Server.name.ilike(f'%{q}%')).limit(20).all()
    return jsonify([{'id': s.id, 'name': s.name, 'icon': s.icon,
                     'members': len(s.members), 'invite': s.invite_code} for s in servers])

# ── Friends ───────────────────────────────────────────────────────────────────

@app.route('/api/friend/add', methods=['POST'])
def add_friend():
    u = current_user()
    if not u: return jsonify({'error': 'auth'}), 401
    code = request.json.get('code', '').strip()
    target = User.query.filter_by(friend_code=code).first()
    if not target: return jsonify({'error': 'Code ami introuvable'}), 404
    if target.id == u.id: return jsonify({'error': 'Vous ne pouvez pas vous ajouter vous-même'}), 400
    if target in u.friends_list: return jsonify({'error': 'Déjà ami'}), 400
    existing = FriendRequest.query.filter_by(sender_id=u.id, receiver_id=target.id).first()
    if existing: return jsonify({'error': 'Demande déjà envoyée'}), 400
    req = FriendRequest(sender_id=u.id, receiver_id=target.id)
    db.session.add(req)
    db.session.commit()
    socketio.emit('friend_request', {'from': u.tag(), 'req_id': req.id}, room=f"user_{target.id}")
    return jsonify({'ok': True, 'message': f'Demande envoyée à {target.tag()}'})

@app.route('/api/friend/accept/<int:req_id>', methods=['POST'])
def accept_friend(req_id):
    u = current_user()
    req = FriendRequest.query.get_or_404(req_id)
    if req.receiver_id != u.id: return jsonify({'error': 'Non autorisé'}), 403
    req.status = 'accepted'
    sender = User.query.get(req.sender_id)
    u.friends_list.append(sender)
    sender.friends_list.append(u)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/friend/decline/<int:req_id>', methods=['POST'])
def decline_friend(req_id):
    u = current_user()
    req = FriendRequest.query.get_or_404(req_id)
    if req.receiver_id != u.id: return jsonify({'error': 'Non autorisé'}), 403
    req.status = 'declined'
    db.session.commit()
    return jsonify({'ok': True})

# ── Profile ───────────────────────────────────────────────────────────────────

@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    u = current_user()
    if not u: return jsonify({'error': 'auth'}), 401
    avatar_path = save_upload(request.files.get('avatar'), 'avatars')
    if avatar_path: u.avatar = avatar_path
    if request.form.get('username'):
        u.username = request.form['username']
    db.session.commit()
    return jsonify({'ok': True, 'avatar': u.avatar})

# ── Messages (REST fallback) ──────────────────────────────────────────────────

@app.route('/api/message/send', methods=['POST'])
def send_message_rest():
    u = current_user()
    if not u: return jsonify({'error': 'auth'}), 401
    d = request.json
    msg = Message(content=d['content'], author_id=u.id,
                  channel_id=d.get('channel_id'), dm_room=d.get('dm_room'))
    db.session.add(msg)
    db.session.commit()
    return jsonify({'ok': True})

# ── SocketIO ──────────────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    u = current_user()
    if u:
        join_room(f"user_{u.id}")

@socketio.on('join_channel')
def on_join_channel(data):
    join_room(f"channel_{data['channel_id']}")

@socketio.on('join_dm')
def on_join_dm(data):
    join_room(data['room'])

@socketio.on('send_message')
def on_send_message(data):
    u = current_user()
    if not u: return
    msg = Message(content=data['content'], author_id=u.id,
                  channel_id=data.get('channel_id'), dm_room=data.get('dm_room'))
    db.session.add(msg)
    db.session.commit()
    room = f"channel_{data['channel_id']}" if data.get('channel_id') else data.get('dm_room')
    emit('new_message', {
        'id': msg.id,
        'content': msg.content,
        'author': u.username,
        'author_id': u.id,
        'avatar': u.avatar,
        'discriminator': u.discriminator,
        'time': msg.created_at.strftime('%H:%M')
    }, room=room)

@socketio.on('typing')
def on_typing(data):
    u = current_user()
    if not u: return
    room = f"channel_{data['channel_id']}" if data.get('channel_id') else data.get('dm_room')
    emit('user_typing', {'user': u.username}, room=room, include_self=False)

@socketio.on('call_user')
def on_call(data):
    u = current_user()
    emit('incoming_call', {'from': u.username, 'from_id': u.id, 'offer': data.get('offer')},
         room=f"user_{data['to']}")

@socketio.on('call_answer')
def on_answer(data):
    emit('call_answered', {'answer': data['answer']}, room=f"user_{data['to']}")

@socketio.on('ice_candidate')
def on_ice(data):
    emit('ice_candidate', {'candidate': data['candidate']}, room=f"user_{data['to']}")

# ── Uploads ───────────────────────────────────────────────────────────────────

@app.route('/static/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ── Init ──────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
