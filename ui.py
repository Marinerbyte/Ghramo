from flask import Blueprint, render_template_string, request, jsonify
import os
import time
import psutil 
import db 

ui_bp = Blueprint('ui', __name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>TalkinChat Bot Panel</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {
            --bg-dark: #111827; --bg-card: #1F2937; --bg-input: #374151; --border: #4B5563;
            --primary: #8B5CF6; /* Purple for TalkinChat */ 
            --secondary: #EC4899; --green: #10B981; --red: #EF4444; --yellow: #F59E0B;
            --text-light: #F9FAFB; --text-muted: #9CA3AF;
        }
        body { font-family: 'Inter', sans-serif; background: var(--bg-dark); color: var(--text-light); margin: 0; padding: 2rem; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem; }
        .card { background: var(--bg-card); padding: 1.5rem; border-radius: 12px; border: 1px solid var(--border); margin-bottom: 1rem;}
        input, select { padding: 12px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px; color: var(--text-light); width: 100%; margin-bottom: 10px; }
        button { padding: 12px; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; color: white; width: 100%; }
        .btn-primary { background: var(--primary); }
        .btn-danger { background: var(--red); }
        .status-dot { height: 12px; width: 12px; border-radius: 50%; display:inline-block; margin-right:5px;}
        .online { background-color: var(--green); } .offline { background-color: var(--red); }
        .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 1rem; }
        .col-4 { grid-column: span 4; } .col-8 { grid-column: span 8; }
        #log-window, #chat-window { height: 300px; background: #000; overflow-y: scroll; font-family: monospace; padding: 10px; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="header">
        <div><span id="status" class="status-dot offline"></span> <h1>TalkinChat Bot</h1></div>
        <div id="uptime"></div>
    </div>
    <div class="grid">
        <div class="card col-4">
            <h3>Bot Login</h3>
            <input type="text" id="username" placeholder="Username">
            <input type="password" id="password" placeholder="Password">
            <button class="btn-primary" onclick="startBot()">Login & Start</button>
            <button class="btn-danger" style="margin-top:10px" onclick="stopBot()">Stop</button>
        </div>
        <div class="card col-8">
            <h3>Room Manager</h3>
            <div style="display:flex; gap:10px">
                <input type="text" id="room" placeholder="Room Name">
                <button class="btn-primary" style="width:150px" onclick="joinRoom()">Join</button>
            </div>
            <div id="log-window"></div>
        </div>
    </div>
    <div class="card">
        <h3>Live Data</h3>
        <p>Active Rooms: <span id="room-list"></span></p>
        <p>Plugins: <span id="plugin-list"></span></p>
    </div>

<script>
    async function api(path, data={}) {
        return fetch('/api'+path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)}).then(r=>r.json());
    }
    function startBot() {
        api('/start', {username: document.getElementById('username').value, password: document.getElementById('password').value});
    }
    function stopBot() { api('/stop'); }
    function joinRoom() { api('/join', {room: document.getElementById('room').value}); }
    
    setInterval(async () => {
        const res = await fetch('/api/status').then(r=>r.json());
        document.getElementById('status').className = 'status-dot ' + (res.running ? 'online' : 'offline');
        document.getElementById('log-window').innerHTML = res.logs.map(l => `<div>${l}</div>`).join('');
        document.getElementById('room-list').innerText = res.rooms.join(', ');
        document.getElementById('plugin-list').innerText = res.plugins.join(', ');
    }, 2000);
</script>
</body>
</html>
"""

def register_routes(app, bot_instance):
    @app.route('/')
    def index(): return render_template_string(DASHBOARD_HTML)
    
    @app.route('/api/start', methods=['POST'])
    def start_bot():
        data = request.json
        success, msg = bot_instance.login_api(data['username'], data['password'])
        if success:
            bot_instance.connect_ws()
            bot_instance.plugins.load_plugins()
        return jsonify({"success": success, "msg": msg})

    @app.route('/api/status')
    def status():
        return jsonify({
            "running": bot_instance.running,
            "logs": bot_instance.logs[-20:],
            "rooms": bot_instance.active_rooms,
            "plugins": list(bot_instance.plugins.plugins.keys())
        })

    @app.route('/api/stop', methods=['POST'])
    def stop_bot(): 
        bot_instance.disconnect()
        return jsonify({"success": True})

    @app.route('/api/join', methods=['POST'])
    def join_room():
        bot_instance.join_room(request.json['room'])
        return jsonify({"success": True})
        
    return ui_bp
