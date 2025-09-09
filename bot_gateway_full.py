# bot_gateway_full.py
# Bot de Telegram + backend REST (usuarios, grupos, mensajes, registro, login, etc.)

import os
from flask import Flask, request, jsonify, abort
from telegram import Bot
import requests
import sqlite3
from flask_cors import CORS

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '8328266176:AAHwCQTSxbLHCgN2N57fw02p4wKlbHUE_7Q')
DB_PATH = os.path.join(os.path.dirname(__file__), 'gateway.db')
app = Flask(__name__)
CORS(app)
bot = Bot(token=TELEGRAM_TOKEN)

# Endpoint para obtener la IP pública del servidor
@app.route('/get_server_ip', methods=['GET'])
def get_server_ip():
    import socket
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    # Si está detrás de proxy, X-Forwarded-For puede tener la IP pública
    return jsonify({'server_ip': ip})

# Inicializar base de datos

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        email TEXT,
        telegram_id TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS group_members (
        group_id INTEGER,
        user_id INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER,
        recipient_id INTEGER,
        message TEXT,
        is_group INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_db()

# Registro de usuario
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    telegram_id = data.get('telegram_id')
    uuid = data.get('uuid')
    if not username or not password:
        abort(400, 'username y password requeridos')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('ALTER TABLE users ADD COLUMN uuid TEXT')
    except Exception:
        pass
    # Verificar si el nombre ya está ocupado
    c.execute('SELECT id FROM users WHERE username=?', (username,))
    if c.fetchone():
        conn.close()
        return jsonify({'error': 'El nombre ya ha sido ocupado por otra persona'})
    try:
        c.execute('INSERT INTO users (username, password, email, telegram_id, uuid) VALUES (?, ?, ?, ?, ?)',
                  (username, password, email, telegram_id, uuid))
        conn.commit()
        return jsonify({'status': 'usuario registrado'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'usuario ya existe'})
    finally:
        conn.close()
# Endpoint para buscar usuario por nombre
@app.route('/find_user_by_name', methods=['POST'])
def find_user_by_name():
    data = request.json
    nombre = data.get('nombre')
    if not nombre:
        abort(400, 'Nombre requerido')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, username, uuid FROM users WHERE username=?', (nombre,))
    user = c.fetchone()
    conn.close()
    if user:
        return jsonify({'exists': True, 'nombre': user[1], 'uuid': user[2]})
    else:
        return jsonify({'exists': False})

# Login de usuario
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id FROM users WHERE username=? AND password=?', (username, password))
    user = c.fetchone()
    conn.close()
    if user:
        return jsonify({'status': 'login exitoso', 'user_id': user[0]})
    else:
        return jsonify({'error': 'usuario o contraseña incorrectos'})

# Crear grupo
@app.route('/create_group', methods=['POST'])
def create_group():
    data = request.json
    group_name = data.get('group_name')
    if not group_name:
        abort(400, 'group_name requerido')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO groups (name) VALUES (?)', (group_name,))
    group_id = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'group_id': group_id, 'status': 'grupo creado'})

# Agregar usuario a grupo
@app.route('/add_user_to_group', methods=['POST'])
def add_user_to_group():
    data = request.json
    group_id = data.get('group_id')
    user_id = data.get('user_id')
    if not group_id or not user_id:
        abort(400, 'group_id y user_id requeridos')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO group_members (group_id, user_id) VALUES (?, ?)', (group_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'usuario agregado al grupo'})

# Enviar mensaje
@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    sender_id = data.get('sender_id')
    recipient_id = data.get('recipient_id')
    message = data.get('message')
    is_group = data.get('is_group', 0)
    if not sender_id or not recipient_id or not message:
        abort(400, 'sender_id, recipient_id y message requeridos')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (sender_id, recipient_id, message, is_group) VALUES (?, ?, ?, ?)',
              (sender_id, recipient_id, message, is_group))
    conn.commit()
    conn.close()
    # Enviar por Telegram si corresponde
    if is_group:
        # Obtener miembros del grupo
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT user_id FROM group_members WHERE group_id=?', (recipient_id,))
        user_ids = [row[0] for row in c.fetchall()]
        for uid in user_ids:
            c.execute('SELECT telegram_id FROM users WHERE id=?', (uid,))
            tid = c.fetchone()
            if tid and tid[0]:
                bot.send_message(chat_id=tid[0], text=f'[Grupo] {message}')
        conn.close()
    else:
        # Mensaje individual
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT telegram_id FROM users WHERE id=?', (recipient_id,))
        tid = c.fetchone()
        if tid and tid[0]:
            bot.send_message(chat_id=tid[0], text=message)
        conn.close()
    return jsonify({'status': 'mensaje enviado'})

# Obtener mensajes
@app.route('/get_messages', methods=['GET'])
def get_messages():
    user_id = request.args.get('user_id')
    group_id = request.args.get('group_id')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if group_id:
        c.execute('SELECT sender_id, message, timestamp FROM messages WHERE recipient_id=? AND is_group=1 ORDER BY timestamp ASC', (group_id,))
    else:
        c.execute('SELECT sender_id, message, timestamp FROM messages WHERE recipient_id=? AND is_group=0 ORDER BY timestamp ASC', (user_id,))
    messages = []
    for row in c.fetchall():
        sender_id = row[0]
        c.execute('SELECT username FROM users WHERE id=?', (sender_id,))
        sender_name = c.fetchone()
        sender_name = sender_name[0] if sender_name else ''
        messages.append({'sender_id': sender_id, 'sender_name': sender_name, 'message': row[1], 'timestamp': row[2]})
    conn.close()
    return jsonify({'messages': messages})

# Obtener lista de usuarios
@app.route('/users', methods=['GET'])
def get_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, username FROM users')
    users = [{'id': row[0], 'username': row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify({'users': users})

# Obtener lista de grupos
@app.route('/groups', methods=['GET'])
def get_groups():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, name FROM groups')
    groups = [{'id': row[0], 'name': row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify({'groups': groups})

# Notificar usuario
@app.route('/notify', methods=['POST'])
def notify():
    data = request.json
    chat_id = data.get('chat_id')
    text = data.get('text', 'Notificación enviada')
    if chat_id:
        bot.send_message(chat_id=chat_id, text=text)
        return jsonify({'status': 'ok', 'detail': 'Notificación enviada'}), 200
    else:
        return jsonify({'status': 'error', 'detail': 'chat_id requerido'}), 400

# Reenviar información (relay)
@app.route('/relay', methods=['POST'])
def relay():
    data = request.json
    chat_id = data.get('chat_id')
    info = data.get('info', 'Información reenviada')
    if chat_id:
        bot.send_message(chat_id=chat_id, text=info)
        return jsonify({'status': 'ok', 'detail': 'Información reenviada'}), 200
    else:
        return jsonify({'status': 'error', 'detail': 'chat_id requerido'}), 400

# Endpoint para iniciar llamada
@app.route('/start_call', methods=['POST'])
def start_call():
    data = request.json
    caller_id = data.get('caller_id')
    recipient_id = data.get('recipient_id')
    if not caller_id or not recipient_id:
        abort(400, 'caller_id y recipient_id requeridos')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT telegram_id FROM users WHERE id=?', (recipient_id,))
    tid = c.fetchone()
    conn.close()
    if tid and tid[0]:
        bot.send_message(chat_id=tid[0], text=f'Tienes una llamada entrante de usuario {caller_id}')
        return jsonify({'status': 'llamada iniciada'})
    else:
        return jsonify({'error': 'El usuario receptor no tiene Telegram vinculado'})

# Endpoint para contestar llamada
@app.route('/answer_call', methods=['POST'])
def answer_call():
    data = request.json
    recipient_id = data.get('recipient_id')
    caller_id = data.get('caller_id')
    if not recipient_id or not caller_id:
        abort(400, 'recipient_id y caller_id requeridos')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT telegram_id FROM users WHERE id=?', (caller_id,))
    tid = c.fetchone()
    conn.close()
    if tid and tid[0]:
        bot.send_message(chat_id=tid[0], text=f'El usuario {recipient_id} ha contestado tu llamada')
        return jsonify({'status': 'llamada contestada'})
    else:
        return jsonify({'error': 'El usuario llamante no tiene Telegram vinculado'})

# Endpoint para borrar mensaje, audio o ubicación para ambos usuarios
@app.route('/delete_message', methods=['POST'])
def delete_message():
    data = request.json
    mensaje_id = data.get('mensaje_id')
    emisor_id = data.get('emisor_id')
    receptor_id = data.get('receptor_id')
    is_audio = data.get('is_audio', False)
    is_ubicacion = data.get('is_ubicacion', False)
    if not mensaje_id or not emisor_id or not receptor_id:
        abort(400, 'Faltan datos para borrar mensaje')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM messages WHERE id=? AND (sender_id=? OR recipient_id=?)', (mensaje_id, emisor_id, receptor_id))
    # Si es audio o ubicación, elimina de la tabla correspondiente si existe
    # (Agrega lógica si tienes tablas separadas para audios/ubicaciones)
    conn.commit()
    conn.close()
    return jsonify({'status': 'mensaje eliminado para ambos'})

# Endpoint para buscar usuario por UUID
@app.route('/find_user_by_uuid', methods=['POST'])
def find_user_by_uuid():
    data = request.json
    uuid = data.get('uuid')
    if not uuid:
        abort(400, 'UUID requerido')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, username FROM users WHERE uuid=?', (uuid,))
    user = c.fetchone()
    conn.close()
    if user:
        return jsonify({'exists': True, 'nombre': user[1]})
    else:
        return jsonify({'exists': False})

