import os
import json
import datetime
from flask import Flask, request
import telebot
from telebot import types

app = Flask(__name__)

TOKEN = os.getenv('TOKEN')
bot = telebot.TeleBot(TOKEN)

# ─────────────────────────────────────────────
# STOCKAGE (JSON local — remplace par DB plus tard)
# ─────────────────────────────────────────────
DATA_FILE = "data.json"

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
        data[uid] = {
            "habits": {},        # { "nom": { "streak": 0, "last_done": null, "history": [] } }
            "todos": [],         # [ { "task": "...", "done": False, "created": "..." } ]
            "notes": [],         # [ { "text": "...", "date": "..." } ]
            "mood_log": []       # [ { "score": 3, "date": "..." } ]
        }
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
# /start  /help
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
        "`/week` — bilan de la semaine\n"
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
    bot.reply_to(message, f"✅ Habitude *{name}* ajoutée ! Reviens la cocher chaque jour 💪", parse_mode="Markdown")

@bot.message_handler(commands=['done'])
def done_habit(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage : `/done sport`", parse_mode="Markdown")
        return
    name = parts[1].strip().lower()
    user, data = get_user(message.from_user.id)
    if name not in user["habits"]:
        bot.reply_to(message, f"❌ Habitude *{name}* introuvable. Utilise `/habits` pour voir la liste.", parse_mode="Markdown")
        return
    habit = user["habits"][name]
    t = today()
    if habit["last_done"] == t:
        bot.reply_to(message, f"✅ *{name}* déjà cochée aujourd'hui. Reviens demain !", parse_mode="Markdown")
        return
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if habit["last_done"] == yesterday:
        habit["streak"] += 1
    else:
        habit["streak"] = 1
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
        bot.reply_to(message, "Tu n'as pas encore d'habitudes. Utilise `/addhabit [nom]`.", parse_mode="Markdown")
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
    task = parts[1].strip()
    user, _ = get_user(message.from_user.id)
    user["todos"].append({"task": task, "done": False, "created": now()})
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"📌 Tâche ajoutée : *{task}*", parse_mode="Markdown")

@bot.message_handler(commands=['listtodo'])
def list_todo(message):
    user, _ = get_user(message.from_user.id)
    todos = [t for t in user["todos"] if not t["done"]]
    if not todos:
        bot.reply_to(message, "✅ Aucune tâche en cours — t'es à jour !")
        return
    lines = ["📋 *Tes tâches :*\n"]
    for i, t in enumerate(user["todos"]):
        if not t["done"]:
            lines.append(f"{i+1}. ⬜ {t['task']}")
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
        bot.reply_to(message, "❌ Numéro invalide. Utilise `/listtodo` pour voir les numéros.", parse_mode="Markdown")
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
    after = len(user["todos"])
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"🧹 {before - after} tâche(s) terminée(s) supprimée(s).")


# ─────────────────────────────────────────────
# NOTES
# ─────────────────────────────────────────────
@bot.message_handler(commands=['note'])
def add_note(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage : `/note mon idée de génie`", parse_mode="Markdown")
        return
    text = parts[1].strip()
    user, _ = get_user(message.from_user.id)
    user["notes"].append({"text": text, "date": now()})
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"📝 Note sauvegardée ✅")

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
    emoji = MOOD_EMOJIS[score]
    bot.reply_to(message, f"{emoji} Humeur *{score}/5* enregistrée.", parse_mode="Markdown")


# ─────────────────────────────────────────────
# RÉCAP DU JOUR
# ─────────────────────────────────────────────
@bot.message_handler(commands=['recap'])
def daily_recap(message):
    user, _ = get_user(message.from_user.id)
    t = today()
    lines = [f"📊 *Récap du {t}*\n"]

    # Habitudes
    lines.append("━━━ ✅ HABITUDES ━━━")
    if user["habits"]:
        for name, h in user["habits"].items():
            status = "✅" if h["last_done"] == t else "❌"
            lines.append(f"{status} {name} (streak {h['streak']}j)")
    else:
        lines.append("_Aucune habitude configurée_")

    # Todos
    lines.append("\n━━━ 📋 TODOS ━━━")
    pending = [t2 for t2 in user["todos"] if not t2["done"]]
    done_tasks = [t2 for t2 in user["todos"] if t2["done"]]
    lines.append(f"✅ Terminées : {len(done_tasks)}  |  ⬜ Restantes : {len(pending)}")

    # Humeur
    lines.append("\n━━━ 😊 HUMEUR ━━━")
    today_mood = [m for m in user["mood_log"] if m["date"] == t]
    if today_mood:
        score = today_mood[-1]["score"]
        lines.append(f"{MOOD_EMOJIS[score]} {score}/5")
    else:
        lines.append("_Pas encore loggée — `/mood [1-5]`_")

    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")


# ─────────────────────────────────────────────
# BILAN SEMAINE (dimanche ou on demand)
# ─────────────────────────────────────────────
@bot.message_handler(commands=['week'])
def weekly_recap(message):
    user, _ = get_user(message.from_user.id)
    today_dt = datetime.date.today()
    week_days = [(today_dt - datetime.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    lines = [f"📅 *Bilan semaine ({week_days[0]} → {week_days[-1]})*\n"]

    # Habitudes sur la semaine
    lines.append("━━━ ✅ HABITUDES ━━━")
    if user["habits"]:
        for name, h in user["habits"].items():
            days_done = sum(1 for d in week_days if d in h["history"])
            bar = "".join(["🟩" if d in h["history"] else "⬜" for d in week_days])
            lines.append(f"*{name}* : {days_done}/7  {bar}")
    else:
        lines.append("_Aucune habitude configurée_")

    # Todos faites cette semaine
    lines.append("\n━━━ 📋 TODOS COMPLÉTÉES ━━━")
    done_this_week = len([t for t in user["todos"] if t["done"]])
    pending_count = len([t for t in user["todos"] if not t["done"]])
    lines.append(f"✅ {done_this_week} terminée(s) | ⬜ {pending_count} en cours")

    # Humeur moyenne
    lines.append("\n━━━ 😊 HUMEUR MOYENNE ━━━")
    week_moods = [m["score"] for m in user["mood_log"] if m["date"] in week_days]
    if week_moods:
        avg = sum(week_moods) / len(week_moods)
        lines.append(f"Moyenne : *{avg:.1f}/5* sur {len(week_moods)} jour(s) {MOOD_EMOJIS[round(avg)]}")
    else:
        lines.append("_Aucune humeur loggée cette semaine_")

    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")


# ─────────────────────────────────────────────
# FLASK ROUTES
# ─────────────────────────────────────────────
@app.route('/', methods=['GET'])
def index():
    return "Bot webhook ready — envoie /start dans Telegram !"

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
