import os
import sqlite3
import psycopg2
import threading
from urllib.parse import urlparse

# Database URL (Render par ye automatic Postgres URL uthayega)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///bot.db")
db_lock = threading.Lock()

def get_connection():
    if DATABASE_URL.startswith("postgres"):
        try:
            return psycopg2.connect(DATABASE_URL, sslmode='require')
        except:
            result = urlparse(DATABASE_URL)
            return psycopg2.connect(
                database=result.path[1:],
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port
            )
    else:
        return sqlite3.connect("bot.db", check_same_thread=False)

def init_db():
    """Bot shuru hote hi tables create karta hai"""
    with db_lock:
        conn = get_connection()
        cur = conn.cursor()
        
        # 1. Users Table (Global Score & Wins)
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT, global_score INTEGER DEFAULT 0, wins INTEGER DEFAULT 0)")
        
        # 2. Game Stats Table (Game wise record)
        cur.execute("CREATE TABLE IF NOT EXISTS game_stats (user_id TEXT, game_name TEXT, wins INTEGER DEFAULT 0, earnings INTEGER DEFAULT 0, PRIMARY KEY (user_id, game_name))")
        
        # 3. Admins Table
        cur.execute("CREATE TABLE IF NOT EXISTS bot_admins (user_id TEXT PRIMARY KEY)")
        
        conn.commit()
        conn.close()
        print("[DB] Tables Initialized (Howdies Style).")

def add_game_result(user_id, username, game_name, amount, is_win=False):
    """Coins aur Wins update karne ka Master Function"""
    if not user_id or user_id == "BOT": return

    with db_lock:
        try:
            conn = get_connection()
            cur = conn.cursor()
            
            is_postgres = DATABASE_URL.startswith("postgres")
            ph = "%s" if is_postgres else "?"
            win_count = 1 if is_win else 0
            uid = str(user_id)

            # --- 1. Global Update ---
            if is_postgres:
                cur.execute(f"INSERT INTO users (user_id, username, global_score, wins) VALUES ({ph}, {ph}, 0, 0) ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username", (uid, username))
            else:
                cur.execute(f"INSERT OR IGNORE INTO users (user_id, username, global_score, wins) VALUES ({ph}, {ph}, 0, 0)", (uid, username))
            
            cur.execute(f"UPDATE users SET global_score = global_score + {ph}, wins = wins + {ph} WHERE user_id = {ph}", (amount, win_count, uid))

            # --- 2. Game Specific Update ---
            if is_postgres:
                cur.execute(f"INSERT INTO game_stats (user_id, game_name, wins, earnings) VALUES ({ph}, {ph}, 0, 0) ON CONFLICT (user_id, game_name) DO NOTHING", (uid, game_name))
            else:
                cur.execute(f"INSERT OR IGNORE INTO game_stats (user_id, game_name, wins, earnings) VALUES ({ph}, {ph}, 0, 0)", (uid, game_name))
            
            cur.execute(f"UPDATE game_stats SET wins = wins + {ph}, earnings = earnings + {ph} WHERE user_id = {ph} AND game_name = {ph}", (win_count, amount, uid, game_name))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB ERROR] add_game_result: {e}")

# --- ADMIN MANAGEMENT ---

def add_admin(user_id):
    if not user_id: return False
    with db_lock:
        try:
            conn = get_connection(); cur = conn.cursor()
            is_postgres = DATABASE_URL.startswith("postgres")
            ph = "%s" if is_postgres else "?"
            if is_postgres:
                cur.execute(f"INSERT INTO bot_admins (user_id) VALUES ({ph}) ON CONFLICT DO NOTHING", (str(user_id),))
            else:
                cur.execute(f"INSERT OR IGNORE INTO bot_admins (user_id) VALUES ({ph})", (str(user_id),))
            conn.commit(); conn.close()
            return True
        except: return False

def is_admin(user_id):
    """Check karta hai kya user admin hai"""
    with db_lock:
        try:
            conn = get_connection(); cur = conn.cursor()
            ph = "%s" if DATABASE_URL.startswith("postgres") else "?"
            cur.execute(f"SELECT 1 FROM bot_admins WHERE user_id = {ph}", (str(user_id),))
            row = cur.fetchone()
            conn.close()
            return row is not None
        except: return False

def get_all_admins():
    with db_lock:
        try:
            conn = get_connection(); cur = conn.cursor()
            cur.execute("SELECT user_id FROM bot_admins")
            rows = [item[0] for item in cur.fetchall()]
            conn.close()
            return rows
        except: return []
