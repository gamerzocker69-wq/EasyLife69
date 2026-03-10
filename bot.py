import os
import json
import datetime
import base64
from email.mime.text import MIMEText
from flask import Flask, request, redirect
import telebot
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

app = Flask(__name__)

TOKEN = os.getenv('TOKEN')
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI')

bot = telebot.TeleBot(TOKEN)

SCOPES = ['https://www.googleapis.com/auth/gmail.send',
          'https://www.googleapis.com/auth/gmail.compose']

# ─────────────────────────────────────────────
# STOCKAGE
# ─────────────────────────────────────────────
DATA_FILE = "data.json"
TOKENS_FILE = "google_tokens.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_user(user_id):
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"habits": {}, "todos": [], "notes": [], "mood_log": []}
        save_data(data)
    return data[uid], data

def save_user(user_id, user_data):
    data = load_data()
    data[str(user_id)] = user_data
    save_data(data)

def today():
    return datetime.date.today().isoformat()

def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

# ─────────────────────────────────────────────
# GOOGLE OAUTH TOKENS
# ─────────────────────────────────────────────
def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tokens(user_id, token_data):
    tokens = load_tokens()
    tokens[str(user_id)] = token_data
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

def get_gmail_service(user_id):
    tokens = load_tokens()
    uid = str(user_id)
    if uid not in tokens:
        return None
    t = tokens[uid]
    creds = Credentials(
        token=t.get("token"),
        refresh_token=t.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES
    )
    return build("gmail", "v1", credentials=creds)

def make_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI]
            }
        },
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI
    )

pending_oauth = {}

# ─────────────────────────────────────────────
# /start /help
# ─────────────────────────────────────────────
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    text = (
        "👋 *Bot Productivité* — voilà ce que tu peux faire :\n\n"
        "━━━ ✅ HABITUDES ━━━\n"
        "`/addhabit [nom]` — créer une habitude\n"
        "`/done [nom]` — cocher une habitude aujourd'hui\n"
        "`/habits` — voir tes habitudes & streaks\n"
        "`/delhabit [nom]` — supprimer une habitude\n\n"
        "━━━ 📋 TODO ━━━\n"
        "`/addtodo [tâche]` — ajouter une tâche\n"
        "`/listtodo` — voir les tâches\n"
        "`/donetodo [numéro]` — cocher une tâche\n"
        "`/cleartodo` — vider les tâches terminées\n\n"
        "━━━ 📝 NOTES ━━━\n"
        "`/note [texte]` — sauvegarder une note rapide\n"
        "`/notes` — voir tes notes récentes\n\n"
        "━━━ 😊 HUMEUR ━━━\n"
        "`/mood [1-5]` — logger ton humeur\n\n"
        "━━━ 📊 RÉCAPS ━━━\n"
        "`/recap` — récap du jour\n"
        "`/week` — bilan de la semaine\n\n"
        "━━━ 📧 GMAIL ━━━\n"
        "`/connectgmail` — connecter ton Gmail\n"
        "`/send email | sujet | message` — envoyer un mail\n"
        "`/draft email | sujet | message` — créer un brouillon\n"
        "`/gmailstatus` — vérifier la connexion\n"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# ─────────────────────────────────────────────
# HABITUDES
# ─────────────────────────────────────────────
@bot.message_handler(commands=['addhabit'])
def add_habit(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage : `/addhabit Sport`", parse_mode="Markdown")
        return
    name = parts[1].strip().lower()
    user, data = get_user(message.from_user.id)
    if name in user["habits"]:
        bot.reply_to(message, f"⚠️ L'habitude *{name}* existe déjà.", parse_mode="Markdown")
        return
    user["habits"][name] = {"streak": 0, "last_done": None, "history": []}
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"✅ Habitude *{name}* ajoutée ! 💪", parse_mode="Markdown")

@bot.message_handler(commands=['done'])
def done_habit(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage : `/done sport`", parse_mode="Markdown")
        return
    name = parts[1].strip().lower()
    user, data = get_user(message.from_user.id)
    if name not in user["habits"]:
        bot.reply_to(message, f"❌ Habitude *{name}* introuvable.", parse_mode="Markdown")
        return
    habit = user["habits"][name]
    t = today()
    if habit["last_done"] == t:
        bot.reply_to(message, f"✅ *{name}* déjà cochée aujourd'hui !", parse_mode="Markdown")
        return
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    habit["streak"] = (habit["streak"] + 1) if habit["last_done"] == yesterday else 1
    habit["last_done"] = t
    habit["history"].append(t)
    save_user(message.from_user.id, user)
    streak = habit["streak"]
    emoji = "🔥" if streak >= 7 else "⚡" if streak >= 3 else "✅"
    bot.reply_to(message, f"{emoji} *{name}* cochée ! Streak : *{streak} jour{'s' if streak > 1 else ''}*", parse_mode="Markdown")

@bot.message_handler(commands=['habits'])
def list_habits(message):
    user, _ = get_user(message.from_user.id)
    if not user["habits"]:
        bot.reply_to(message, "Pas encore d'habitudes. Utilise `/addhabit [nom]`.", parse_mode="Markdown")
        return
    t = today()
    lines = ["📋 *Tes habitudes :*\n"]
    for name, h in user["habits"].items():
        done_today = "✅" if h["last_done"] == t else "⬜"
        streak = h["streak"]
        fire = " 🔥" if streak >= 7 else " ⚡" if streak >= 3 else ""
        lines.append(f"{done_today} *{name}* — {streak}j de streak{fire}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['delhabit'])
def del_habit(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage : `/delhabit sport`", parse_mode="Markdown")
        return
    name = parts[1].strip().lower()
    user, _ = get_user(message.from_user.id)
    if name not in user["habits"]:
        bot.reply_to(message, f"❌ Habitude *{name}* introuvable.", parse_mode="Markdown")
        return
    del user["habits"][name]
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"🗑️ Habitude *{name}* supprimée.", parse_mode="Markdown")

# ─────────────────────────────────────────────
# TODO
# ─────────────────────────────────────────────
@bot.message_handler(commands=['addtodo'])
def add_todo(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage : `/addtodo Appeler le médecin`", parse_mode="Markdown")
        return
    user, _ = get_user(message.from_user.id)
    user["todos"].append({"task": parts[1].strip(), "done": False, "created": now()})
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"📌 Tâche ajoutée : *{parts[1].strip()}*", parse_mode="Markdown")

@bot.message_handler(commands=['listtodo'])
def list_todo(message):
    user, _ = get_user(message.from_user.id)
    pending = [t for t in user["todos"] if not t["done"]]
    if not pending:
        bot.reply_to(message, "✅ Aucune tâche en cours !")
        return
    lines = ["📋 *Tes tâches :*\n"]
    i = 1
    for t in user["todos"]:
        if not t["done"]:
            lines.append(f"{i}. ⬜ {t['task']}")
            i += 1
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['donetodo'])
def done_todo(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        bot.reply_to(message, "❌ Usage : `/donetodo 2`", parse_mode="Markdown")
        return
    idx = int(parts[1].strip()) - 1
    user, _ = get_user(message.from_user.id)
    pending = [t for t in user["todos"] if not t["done"]]
    if idx < 0 or idx >= len(pending):
        bot.reply_to(message, "❌ Numéro invalide.", parse_mode="Markdown")
        return
    task_name = pending[idx]["task"]
    for t in user["todos"]:
        if t["task"] == task_name and not t["done"]:
            t["done"] = True
            break
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"✅ *{task_name}* — terminée !", parse_mode="Markdown")

@bot.message_handler(commands=['cleartodo'])
def clear_todo(message):
    user, _ = get_user(message.from_user.id)
    before = len(user["todos"])
    user["todos"] = [t for t in user["todos"] if not t["done"]]
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"🧹 {before - len(user['todos'])} tâche(s) supprimée(s).")

# ─────────────────────────────────────────────
# NOTES
# ─────────────────────────────────────────────
@bot.message_handler(commands=['note'])
def add_note(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage : `/note mon idée`", parse_mode="Markdown")
        return
    user, _ = get_user(message.from_user.id)
    user["notes"].append({"text": parts[1].strip(), "date": now()})
    save_user(message.from_user.id, user)
    bot.reply_to(message, "📝 Note sauvegardée ✅")

@bot.message_handler(commands=['notes'])
def list_notes(message):
    user, _ = get_user(message.from_user.id)
    recent = user["notes"][-10:][::-1]
    if not recent:
        bot.reply_to(message, "Aucune note. Utilise `/note [texte]`.", parse_mode="Markdown")
        return
    lines = ["📝 *Tes 10 dernières notes :*\n"]
    for n in recent:
        lines.append(f"• `{n['date']}` — {n['text']}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────────
# HUMEUR
# ─────────────────────────────────────────────
MOOD_EMOJIS = {1: "😞", 2: "😕", 3: "😐", 4: "😊", 5: "🤩"}

@bot.message_handler(commands=['mood'])
def log_mood(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        bot.reply_to(message, "❌ Usage : `/mood 4` (entre 1 et 5)", parse_mode="Markdown")
        return
    score = int(parts[1].strip())
    if score < 1 or score > 5:
        bot.reply_to(message, "❌ Score entre 1 et 5.", parse_mode="Markdown")
        return
    user, _ = get_user(message.from_user.id)
    user["mood_log"].append({"score": score, "date": today()})
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"{MOOD_EMOJIS[score]} Humeur *{score}/5* enregistrée.", parse_mode="Markdown")

# ─────────────────────────────────────────────
# RÉCAPS
# ─────────────────────────────────────────────
@bot.message_handler(commands=['recap'])
def daily_recap(message):
    user, _ = get_user(message.from_user.id)
    t = today()
    lines = [f"📊 *Récap du {t}*\n"]
    lines.append("━━━ ✅ HABITUDES ━━━")
    if user["habits"]:
        for name, h in user["habits"].items():
            status = "✅" if h["last_done"] == t else "❌"
            lines.append(f"{status} {name} (streak {h['streak']}j)")
    else:
        lines.append("_Aucune habitude configurée_")
    lines.append("\n━━━ 📋 TODOS ━━━")
    lines.append(f"✅ Terminées : {len([x for x in user['todos'] if x['done']])}  |  ⬜ Restantes : {len([x for x in user['todos'] if not x['done']])}")
    lines.append("\n━━━ 😊 HUMEUR ━━━")
    today_mood = [m for m in user["mood_log"] if m["date"] == t]
    if today_mood:
        score = today_mood[-1]["score"]
        lines.append(f"{MOOD_EMOJIS[score]} {score}/5")
    else:
        lines.append("_Pas encore loggée — `/mood [1-5]`_")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['week'])
def weekly_recap(message):
    user, _ = get_user(message.from_user.id)
    today_dt = datetime.date.today()
    week_days = [(today_dt - datetime.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    lines = [f"📅 *Bilan semaine ({week_days[0]} → {week_days[-1]})*\n"]
    lines.append("━━━ ✅ HABITUDES ━━━")
    if user["habits"]:
        for name, h in user["habits"].items():
            days_done = sum(1 for d in week_days if d in h["history"])
            bar = "".join(["🟩" if d in h["history"] else "⬜" for d in week_days])
            lines.append(f"*{name}* : {days_done}/7  {bar}")
    else:
        lines.append("_Aucune habitude configurée_")
    lines.append("\n━━━ 📋 TODOS ━━━")
    lines.append(f"✅ {len([x for x in user['todos'] if x['done']])} terminée(s) | ⬜ {len([x for x in user['todos'] if not x['done']])} en cours")
    lines.append("\n━━━ 😊 HUMEUR MOYENNE ━━━")
    week_moods = [m["score"] for m in user["mood_log"] if m["date"] in week_days]
    if week_moods:
        avg = sum(week_moods) / len(week_moods)
        lines.append(f"Moyenne : *{avg:.1f}/5* sur {len(week_moods)} jour(s) {MOOD_EMOJIS[round(avg)]}")
    else:
        lines.append("_Aucune humeur loggée cette semaine_")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────────
# GMAIL — CONNEXION OAUTH
# ─────────────────────────────────────────────
@bot.message_handler(commands=['connectgmail'])
def connect_gmail(message):
    uid = message.from_user.id
    flow = make_flow()
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    pending_oauth[state] = uid
    bot.reply_to(
        message,
        f"🔗 Clique sur ce lien pour connecter ton Gmail :\n\n{auth_url}\n\n"
        f"_Une fois autorisé, reviens ici et t'es bon !_",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['gmailstatus'])
def gmail_status(message):
    tokens = load_tokens()
    uid = str(message.from_user.id)
    if uid in tokens:
        bot.reply_to(message, "✅ Gmail connecté et opérationnel !")
    else:
        bot.reply_to(message, "❌ Gmail pas connecté. Utilise `/connectgmail`.", parse_mode="Markdown")

# ─────────────────────────────────────────────
# GMAIL — ENVOYER UN MAIL
# ─────────────────────────────────────────────
@bot.message_handler(commands=['send'])
def send_email(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or parts[1].count('|') < 2:
        bot.reply_to(message, "❌ Usage : `/send email@exemple.com | Sujet | Corps du message`", parse_mode="Markdown")
        return
    service = get_gmail_service(message.from_user.id)
    if not service:
        bot.reply_to(message, "❌ Gmail pas connecté. Utilise `/connectgmail` d'abord.", parse_mode="Markdown")
        return
    to, subject, body = [x.strip() for x in parts[1].split('|', 2)]
    try:
        mime = MIMEText(body)
        mime['to'] = to
        mime['subject'] = subject
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        bot.reply_to(message, f"📧 Mail envoyé à *{to}* ✅", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erreur lors de l'envoi : `{str(e)}`", parse_mode="Markdown")

# ─────────────────────────────────────────────
# GMAIL — CRÉER UN BROUILLON
# ─────────────────────────────────────────────
@bot.message_handler(commands=['draft'])
def create_draft(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or parts[1].count('|') < 2:
        bot.reply_to(message, "❌ Usage : `/draft email@exemple.com | Sujet | Corps du message`", parse_mode="Markdown")
        return
    service = get_gmail_service(message.from_user.id)
    if not service:
        bot.reply_to(message, "❌ Gmail pas connecté. Utilise `/connectgmail` d'abord.", parse_mode="Markdown")
        return
    to, subject, body = [x.strip() for x in parts[1].split('|', 2)]
    try:
        mime = MIMEText(body)
        mime['to'] = to
        mime['subject'] = subject
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        service.users().drafts().create(userId='me', body={'message': {'raw': raw}}).execute()
        bot.reply_to(message, f"📝 Brouillon créé pour *{to}* — sujet : *{subject}* ✅", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erreur : `{str(e)}`", parse_mode="Markdown")

# ─────────────────────────────────────────────
# FLASK ROUTES
# ─────────────────────────────────────────────
@app.route('/', methods=['GET'])
def index():
    return "Bot webhook ready — envoie /start dans Telegram !"

@app.route('/oauth/callback', methods=['GET'])
def oauth_callback():
    state = request.args.get('state')
    code = request.args.get('code')
    if not state or state not in pending_oauth:
        return "❌ Session OAuth invalide ou expirée.", 400
    uid = pending_oauth.pop(state)
    try:
        flow = make_flow()
        flow.fetch_token(code=code)
        creds = flow.credentials
        save_tokens(uid, {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "scopes": list(creds.scopes) if creds.scopes else []
        })
        bot.send_message(uid, "✅ Gmail connecté ! Tu peux utiliser `/send` et `/draft`.", parse_mode="Markdown")
        return "<h2>✅ Gmail connecté ! Retourne sur Telegram.</h2>"
    except Exception as e:
        return f"❌ Erreur OAuth : {str(e)}", 500

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK'
    return 'Bad request', 403

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
