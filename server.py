import os
import sqlite3
import datetime
import bcrypt
import requests
import base64  # Added for M-Pesa password encoding
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)  # Allows your frontend to safely interact with this server

@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

API_KEY = os.getenv("ODDS_API_KEY")
SPORT = "soccer_epl"

# ==========================================
# M-PESA DARAJA CONFIGURATION (Loaded from .env)
# ==========================================
CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
PASSKEY = os.getenv("MPESA_PASSKEY")
BUSINESS_SHORT_CODE = "174379"  # Default Daraja sandbox shortcode

# ==========================================
# 1. INITIALIZE SECURE SQLITE3 DATABASE
# ==========================================
# Switches to Render's persistent disk folder path if running in the cloud
if os.environ.get('RENDER'):
    DATABASE = '/data/prlm_database.db'
else:
    DATABASE = "prlm_database.db"

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Enables accessing columns by name
    conn.execute("PRAGMA foreign_keys = ON;")  # Ensures table references align perfectly
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                phone TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                balance REAL DEFAULT 0.00
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                match_summary TEXT,
                predicted_choice TEXT,
                odds REAL,
                stake REAL,
                potential_win REAL,
                status TEXT DEFAULT 'OPEN',
                FOREIGN KEY(phone) REFERENCES users(phone)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                type TEXT,
                amount REAL,
                date TEXT,
                FOREIGN KEY(phone) REFERENCES users(phone)
            )
        """)
        conn.commit()

init_db()

# ==========================================
# M-PESA DARAJA UTILITIES & ENDPOINTS
# ==========================================
def get_mpesa_access_token():
    """Generates authentication access token from Safaricom credentials"""
    url = "https://sandbox.safaricom.co.uk/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=(CONSUMER_KEY, CONSUMER_SECRET))
    return response.json().get("access_token")

@app.route('/api/mpesa/stkpush', methods=['POST'])
def trigger_stk_push():
    """Triggers an STK Push menu to pop up on user's device screen"""
    data = request.get_json()
    phone = data.get('phone')    # Expects format: 2547XXXXXXXX
    amount = data.get('amount')  # Deposit target amount
    
    if not phone or not amount or float(amount) < 10:
        return jsonify({"error": "Invalid phone number or minimum deposit of Kes 10 required"}), 400

    try:
        access_token = get_mpesa_access_token()
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        
        # Security hash generation payload requirement
        password_str = BUSINESS_SHORT_CODE + PASSKEY + timestamp
        password = base64.b64encode(password_str.encode()).decode('utf-8')
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Render dynamic deployment tracking path
        app_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:3000')
        callback_url = f"{app_url}/api/mpesa/callback"

        payload = {
            "BusinessShortCode": BUSINESS_SHORT_CODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(float(amount)),
            "PartyA": phone,
            "PartyB": BUSINESS_SHORT_CODE,
            "PhoneNumber": phone,
            "CallBackURL": callback_url,
            "AccountReference": "BettingWallet",
            "TransactionDesc": "Wallet Deposit"
        }
        
        url = "https://sandbox.safaricom.co.uk/mpesa/stkpush/v1/processrequest"
        response = requests.post(url, json=payload, headers=headers)
        return jsonify(response.json())
        
    except Exception as e:
        return jsonify({"error": f"Failed executing payment setup initialization pipeline: {str(e)}"}), 500

@app.route('/api/mpesa/callback', methods=['POST'])
def mpesa_callback():
    """Processes Safaricom callback payload securely to credit user wallets"""
    data = request.get_json()
    
    stk_callback = data['Body']['stkCallback']
    result_code = stk_callback['ResultCode']
    result_desc = stk_callback['ResultDesc']

    # ResultCode 0 means user entered PIN successfully!
    if result_code == 0:
        metadata = stk_callback['CallbackMetadata']['Item']
        
        amount = next((item['Value'] for item in metadata if item['Name'] == 'Amount'), 0)
        phone_raw = next((item['Value'] for item in metadata if item['Name'] == 'PhoneNumber'), None)
        
        if phone_raw:
            phone = str(phone_raw)
            date_str = datetime.date.today().strftime("%m/%d/%Y")
            
            with get_db() as conn:
                # 1. Update wallet balance
                conn.execute("UPDATE users SET balance = balance + ? WHERE phone = ?", (amount, phone))
                # 2. Record statement receipt ledger line
                conn.execute("INSERT INTO transactions (phone, type, amount, date) VALUES (?, 'Deposit (M-Pesa)', ?, ?)", (phone, amount, date_str))
                conn.commit()
                
            print(f"✅ Secure wallet deposit processed. Credited Kes {amount} to user account: {phone}", flush=True)
    else:
        print(f"❌ Payment Callback Alert failed or rejected: {result_desc} (Code: {result_code})", flush=True)

    return jsonify({"ResultCode": 0, "ResultDescription": "Success"}), 200

# ==========================================
# 2. AUTHENTICATION ENDPOINTS
# ==========================================
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    phone = data.get('phone')
    password = data.get('password')

    if not phone or not password or len(password) != 5:
        return jsonify({"error": "Invalid data. Password must be 5 characters."}), 400

    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    try:
        with get_db() as conn:
            conn.execute("INSERT INTO users (phone, password_hash) VALUES (?, ?)", (phone, hashed))
            conn.commit()
        return jsonify({"success": True, "message": "Account created safely."})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Phone number already registered."}), 400

@app.route('/api/signin', methods=['POST'])
def signin():
    data = request.get_json()
    phone = data.get('phone')
    password = data.get('password')

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()

    if not user:
        return jsonify({"error": "User not found."}), 400

    if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return jsonify({"success": True, "user": {"phone": user['phone'], "balance": user['balance']}})
    
    return jsonify({"error": "Invalid password credentials."}), 401

# ==========================================
# 3. WALLET & BETTING MANAGEMENT
# ==========================================
@app.route('/api/deposit', methods=['POST'])
def deposit():
    """Manual fallback deposit route"""
    data = request.get_json()
    phone = data.get('phone')
    amount = float(data.get('amount', 0))

    if amount < 10:
        return jsonify({"error": "Min deposit is Kes 10"}), 400

    date_str = datetime.date.today().strftime("%m/%d/%Y")
    
    with get_db() as conn:
        conn.execute("UPDATE users SET balance = balance + ? WHERE phone = ?", (amount, phone))
        conn.execute("INSERT INTO transactions (phone, type, amount, date) VALUES (?, 'Deposit', ?, ?)", (phone, amount, date_str))
        conn.commit()
        updated_user = conn.execute("SELECT balance FROM users WHERE phone = ?", (phone,)).fetchone()
        
    return jsonify({"success": True, "balance": updated_user['balance']})

@app.route('/api/bet', methods=['POST'])
def place_bet():
    data = request.get_json()
    phone = data.get('phone')
    match_summary = data.get('matchSummary')
    predicted_choice = data.get('predictedChoice')
    odds = float(data.get('odds', 1))
    stake = float(data.get('stake', 0))

    with get_db() as conn:
        user = conn.execute("SELECT balance FROM users WHERE phone = ?", (phone,)).fetchone()
        if not user or user['balance'] < stake:
            return jsonify({"error": "Insufficient balance to place bet."}), 400

        potential_win = stake * odds
        conn.execute("UPDATE users SET balance = balance - ? WHERE phone = ?", (stake, phone))
        conn.execute("""
            INSERT INTO bets (phone, match_summary, predicted_choice, odds, stake, potential_win) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (phone, match_summary, predicted_choice, odds, stake, potential_win))
        conn.commit()
        updated_user = conn.execute("SELECT balance FROM users WHERE phone = ?", (phone,)).fetchone()

    return jsonify({"success": True, "balance": updated_user['balance']})

@app.route('/api/history/<phone>', methods=['GET'])
def history(phone):
    with get_db() as conn:
        bets = conn.execute("SELECT * FROM bets WHERE phone = ? ORDER BY id DESC", (phone,)).fetchall()
        txs = conn.execute("SELECT * FROM transactions WHERE phone = ? ORDER BY id DESC", (phone,)).fetchall()
    
    return jsonify({
        "bets": [dict(b) for b in bets],
        "transactions": [dict(t) for t in txs]
    })

# ==========================================
# 4. SECURE API PROXY (Hides your secret API Key)
# ==========================================
@app.route('/api/matches', methods=['GET'])
def get_matches():
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds/?apiKey={API_KEY}&regions=uk&markets=h2h"
    try:
        response = requests.get(url)
        return jsonify(response.json())
    except:
        return jsonify({"error": "Failed fetching odds from source provider."}), 500

# ==========================================
# 5. AUTOMATED BACKGROUND BET SETTLEMENT
# ==========================================
@app.route('/api/settle', methods=['POST'])
def settle_bets():
    scores_url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/scores/?apiKey={API_KEY}&daysFrom=3"
    try:
        completed_games = requests.get(scores_url).json()
        date_str = datetime.date.today().strftime("%m/%d/%Y")
        
        with get_db() as conn:
            open_bets = conn.execute("SELECT * FROM bets WHERE status = 'OPEN'").fetchall()
            
            for bet in open_bets:
                finished_game = next((g for g in completed_games if g.get('completed') and f"{g['home_team']} vs {g['away_team']}" == bet['match_summary']), None)
                
                if finished_game:
                    actual_result = 'X'
                    home_score = next(int(s['score']) for s in finished_game['scores'] if s['name'] == finished_game['home_team'])
                    away_score = next(int(s['score']) for s in finished_game['scores'] if s['name'] == finished_game['away_team'])
                    
                    if home_score > away_score: actual_result = '1'
                    elif away_score > home_score: actual_result = '2'
                    
                    if bet['predicted_choice'] == actual_result:
                        conn.execute("UPDATE users SET balance = balance + ? WHERE phone = ?", (bet['potential_win'], bet['phone']))
                        conn.execute("UPDATE bets SET status = 'WON' WHERE id = ?", (bet['id'],))
                        conn.execute("INSERT INTO transactions (phone, type, amount, date) VALUES (?, 'Bet Win 🏆', ?, ?)", (bet['phone'], bet['potential_win'], date_str))
                    else:
                        conn.execute("UPDATE bets SET status = 'LOST' WHERE id = ?", (bet['id'],))
            conn.commit()
        return jsonify({"success": True, "message": "Settlement processing complete."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.get_json()
    phone = data.get('phone')
    amount = float(data.get('amount', 0))

    if amount < 20:
        return jsonify({"error": "Minimum withdrawal is Kes 20"}), 400

    with get_db() as conn:
        user = conn.execute(
            "SELECT balance FROM users WHERE phone = ?",
            (phone,)
        ).fetchone()

        if not user or user['balance'] < amount:
            return jsonify({"error": "Insufficient balance"}), 400

        conn.execute(
            "UPDATE users SET balance = balance - ? WHERE phone = ?",
            (amount, phone)
        )

        conn.commit()

        updated_user = conn.execute(
            "SELECT balance FROM users WHERE phone = ?",
            (phone,)
        ).fetchone()

    return jsonify({
        "success": True,
        "balance": updated_user['balance']
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port)