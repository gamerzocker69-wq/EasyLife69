import os
import json
import datetime
import base64
from email.mime.text import MIMEText
from flask import Flask, request
import telebot
from telebot import types
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
        data[uid] = {"habitudes": {}, "taches": [], "notes": [], "humeur": []}
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
# GOOGLE OAUTH
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
    flow = Flow.from_client_config(
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
    flow.code_verifier = None
    return flow

pending_oauth = {}

# ─────────────────────────────────────────────
# ÉTAT CONVERSATIONNEL (flow email/brouillon)
# ─────────────────────────────────────────────
# { user_id: { "etape": "destinataire"/"sujet"/"message", "type": "envoi"/"brouillon", "destinataire": "", "sujet": "" } }
conversation_state = {}

# ─────────────────────────────────────────────
# /start /aide
# ─────────────────────────────────────────────
@bot.message_handler(commands=['start', 'aide'])
def send_welcome(message):
    text = (
        "👋 *Bot EasyLife* — voilà ce que tu peux faire :\n\n"
        "━━━ ✅ HABITUDES ━━━\n"
        "`/ajouterhabitude [nom]` — créer une habitude\n"
        "`/fait [nom]` — cocher une habitude aujourd'hui\n"
        "`/habitudes` — voir tes habitudes & streaks\n"
        "`/supprimerhabitude [nom]` — supprimer une habitude\n\n"
        "━━━ 📋 TÂCHES ━━━\n"
        "`/ajoutertache [tâche]` — ajouter une tâche\n"
        "`/taches` — voir les tâches\n"
        "`/terminee [numéro]` — cocher une tâche\n"
        "`/nettoyertaches` — vider les tâches terminées\n\n"
        "━━━ 📝 NOTES ━━━\n"
        "`/note [texte]` — sauvegarder une note rapide\n"
        "`/notes` — voir tes notes récentes\n\n"
        "━━━ 😊 HUMEUR ━━━\n"
        "`/humeur [1-5]` — logger ton humeur\n\n"
        "━━━ 📊 RÉCAPS ━━━\n"
        "`/recap` — récap du jour\n"
        "`/semaine` — bilan de la semaine\n\n"
        "━━━ 📧 GMAIL ━━━\n"
        "`/connectergmail` — connecter ton Gmail\n"
        "`/envoyer` — envoyer un mail (guidé)\n"
        "`/brouillon` — créer un brouillon (guidé)\n"
        "`/gmailstatut` — vérifier la connexion\n"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# ─────────────────────────────────────────────
# HABITUDES
# ─────────────────────────────────────────────
@bot.message_handler(commands=['ajouterhabitude'])
def ajouter_habitude(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage : `/ajouterhabitude Sport`", parse_mode="Markdown")
        return
    nom = parts[1].strip().lower()
    user, _ = get_user(message.from_user.id)
    if nom in user["habitudes"]:
        bot.reply_to(message, f"⚠️ L'habitude *{nom}* existe déjà.", parse_mode="Markdown")
        return
    user["habitudes"][nom] = {"streak": 0, "dernier_fait": None, "historique": []}
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"✅ Habitude *{nom}* ajoutée ! Reviens la cocher chaque jour 💪", parse_mode="Markdown")

@bot.message_handler(commands=['fait'])
def fait_habitude(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage : `/fait sport`", parse_mode="Markdown")
        return
    nom = parts[1].strip().lower()
    user, _ = get_user(message.from_user.id)
    if nom not in user["habitudes"]:
        bot.reply_to(message, f"❌ Habitude *{nom}* introuvable. Utilise `/habitudes` pour voir la liste.", parse_mode="Markdown")
        return
    habitude = user["habitudes"][nom]
    t = today()
    if habitude["dernier_fait"] == t:
        bot.reply_to(message, f"✅ *{nom}* déjà cochée aujourd'hui !", parse_mode="Markdown")
        return
    hier = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    habitude["streak"] = (habitude["streak"] + 1) if habitude["dernier_fait"] == hier else 1
    habitude["dernier_fait"] = t
    habitude["historique"].append(t)
    save_user(message.from_user.id, user)
    streak = habitude["streak"]
    emoji = "🔥" if streak >= 7 else "⚡" if streak >= 3 else "✅"
    bot.reply_to(message, f"{emoji} *{nom}* cochée ! Streak : *{streak} jour{'s' if streak > 1 else ''}*", parse_mode="Markdown")

@bot.message_handler(commands=['habitudes'])
def liste_habitudes(message):
    user, _ = get_user(message.from_user.id)
    if not user["habitudes"]:
        bot.reply_to(message, "Pas encore d'habitudes. Utilise `/ajouterhabitude [nom]`.", parse_mode="Markdown")
        return
    t = today()
    lines = ["📋 *Tes habitudes :*\n"]
    for nom, h in user["habitudes"].items():
        faite = "✅" if h["dernier_fait"] == t else "⬜"
        streak = h["streak"]
        feu = " 🔥" if streak >= 7 else " ⚡" if streak >= 3 else ""
        lines.append(f"{faite} *{nom}* — {streak}j de streak{feu}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['supprimerhabitude'])
def supprimer_habitude(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage : `/supprimerhabitude sport`", parse_mode="Markdown")
        return
    nom = parts[1].strip().lower()
    user, _ = get_user(message.from_user.id)
    if nom not in user["habitudes"]:
        bot.reply_to(message, f"❌ Habitude *{nom}* introuvable.", parse_mode="Markdown")
        return
    del user["habitudes"][nom]
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"🗑️ Habitude *{nom}* supprimée.", parse_mode="Markdown")

# ─────────────────────────────────────────────
# TÂCHES
# ─────────────────────────────────────────────
@bot.message_handler(commands=['ajoutertache'])
def ajouter_tache(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage : `/ajoutertache Appeler le médecin`", parse_mode="Markdown")
        return
    user, _ = get_user(message.from_user.id)
    user["taches"].append({"tache": parts[1].strip(), "faite": False, "creee": now()})
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"📌 Tâche ajoutée : *{parts[1].strip()}*", parse_mode="Markdown")

@bot.message_handler(commands=['taches'])
def liste_taches(message):
    user, _ = get_user(message.from_user.id)
    en_cours = [t for t in user["taches"] if not t["faite"]]
    if not en_cours:
        bot.reply_to(message, "✅ Aucune tâche en cours — t'es à jour !")
        return
    lines = ["📋 *Tes tâches :*\n"]
    i = 1
    for t in user["taches"]:
        if not t["faite"]:
            lines.append(f"{i}. ⬜ {t['tache']}")
            i += 1
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['terminee'])
def terminer_tache(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        bot.reply_to(message, "❌ Usage : `/terminee 2`", parse_mode="Markdown")
        return
    idx = int(parts[1].strip()) - 1
    user, _ = get_user(message.from_user.id)
    en_cours = [t for t in user["taches"] if not t["faite"]]
    if idx < 0 or idx >= len(en_cours):
        bot.reply_to(message, "❌ Numéro invalide. Utilise `/taches` pour voir les numéros.", parse_mode="Markdown")
        return
    nom_tache = en_cours[idx]["tache"]
    for t in user["taches"]:
        if t["tache"] == nom_tache and not t["faite"]:
            t["faite"] = True
            break
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"✅ *{nom_tache}* — terminée !", parse_mode="Markdown")

@bot.message_handler(commands=['nettoyertaches'])
def nettoyer_taches(message):
    user, _ = get_user(message.from_user.id)
    avant = len(user["taches"])
    user["taches"] = [t for t in user["taches"] if not t["faite"]]
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"🧹 {avant - len(user['taches'])} tâche(s) terminée(s) supprimée(s).")

# ─────────────────────────────────────────────
# NOTES
# ─────────────────────────────────────────────
@bot.message_handler(commands=['note'])
def ajouter_note(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage : `/note mon idée`", parse_mode="Markdown")
        return
    user, _ = get_user(message.from_user.id)
    user["notes"].append({"texte": parts[1].strip(), "date": now()})
    save_user(message.from_user.id, user)
    bot.reply_to(message, "📝 Note sauvegardée ✅")

@bot.message_handler(commands=['notes'])
def liste_notes(message):
    user, _ = get_user(message.from_user.id)
    recentes = user["notes"][-10:][::-1]
    if not recentes:
        bot.reply_to(message, "Aucune note. Utilise `/note [texte]`.", parse_mode="Markdown")
        return
    lines = ["📝 *Tes 10 dernières notes :*\n"]
    for n in recentes:
        lines.append(f"• `{n['date']}` — {n['texte']}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────────
# HUMEUR
# ─────────────────────────────────────────────
HUMEUR_EMOJIS = {1: "😞", 2: "😕", 3: "😐", 4: "😊", 5: "🤩"}

@bot.message_handler(commands=['humeur'])
def logger_humeur(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        bot.reply_to(message, "❌ Usage : `/humeur 4` (entre 1 et 5)", parse_mode="Markdown")
        return
    score = int(parts[1].strip())
    if score < 1 or score > 5:
        bot.reply_to(message, "❌ Score entre 1 et 5.", parse_mode="Markdown")
        return
    user, _ = get_user(message.from_user.id)
    user["humeur"].append({"score": score, "date": today()})
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"{HUMEUR_EMOJIS[score]} Humeur *{score}/5* enregistrée.", parse_mode="Markdown")

# ─────────────────────────────────────────────
# RÉCAPS
# ─────────────────────────────────────────────
@bot.message_handler(commands=['recap'])
def recap_jour(message):
    user, _ = get_user(message.from_user.id)
    t = today()
    lines = [f"📊 *Récap du {t}*\n"]
    lines.append("━━━ ✅ HABITUDES ━━━")
    if user["habitudes"]:
        for nom, h in user["habitudes"].items():
            statut = "✅" if h["dernier_fait"] == t else "❌"
            lines.append(f"{statut} {nom} (streak {h['streak']}j)")
    else:
        lines.append("_Aucune habitude configurée_")
    lines.append("\n━━━ 📋 TÂCHES ━━━")
    lines.append(f"✅ Terminées : {len([x for x in user['taches'] if x['faite']])}  |  ⬜ Restantes : {len([x for x in user['taches'] if not x['faite']])}")
    lines.append("\n━━━ 😊 HUMEUR ━━━")
    humeur_today = [m for m in user["humeur"] if m["date"] == t]
    if humeur_today:
        score = humeur_today[-1]["score"]
        lines.append(f"{HUMEUR_EMOJIS[score]} {score}/5")
    else:
        lines.append("_Pas encore loggée — `/humeur [1-5]`_")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['semaine'])
def recap_semaine(message):
    user, _ = get_user(message.from_user.id)
    today_dt = datetime.date.today()
    jours = [(today_dt - datetime.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    lines = [f"📅 *Bilan semaine ({jours[0]} → {jours[-1]})*\n"]
    lines.append("━━━ ✅ HABITUDES ━━━")
    if user["habitudes"]:
        for nom, h in user["habitudes"].items():
            jours_faits = sum(1 for d in jours if d in h["historique"])
            barre = "".join(["🟩" if d in h["historique"] else "⬜" for d in jours])
            lines.append(f"*{nom}* : {jours_faits}/7  {barre}")
    else:
        lines.append("_Aucune habitude configurée_")
    lines.append("\n━━━ 📋 TÂCHES ━━━")
    lines.append(f"✅ {len([x for x in user['taches'] if x['faite']])} terminée(s) | ⬜ {len([x for x in user['taches'] if not x['faite']])} en cours")
    lines.append("\n━━━ 😊 HUMEUR MOYENNE ━━━")
    humeurs = [m["score"] for m in user["humeur"] if m["date"] in jours]
    if humeurs:
        moy = sum(humeurs) / len(humeurs)
        lines.append(f"Moyenne : *{moy:.1f}/5* sur {len(humeurs)} jour(s) {HUMEUR_EMOJIS[round(moy)]}")
    else:
        lines.append("_Aucune humeur loggée cette semaine_")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────────
# GMAIL — CONNEXION
# ─────────────────────────────────────────────
@bot.message_handler(commands=['connectergmail'])
def connecter_gmail(message):
    try:
        uid = message.from_user.id
        flow = make_flow()
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        pending_oauth[state] = uid
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔗 Connecter mon Gmail", url=auth_url))
        bot.reply_to(
            message,
            "Clique sur le bouton pour connecter ton Gmail ✅\n_Une fois autorisé, reviens ici !_",
            parse_mode="Markdown",
            reply_markup=markup
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Erreur : `{str(e)}`", parse_mode="Markdown")

@bot.message_handler(commands=['gmailstatut'])
def gmail_statut(message):
    tokens = load_tokens()
    uid = str(message.from_user.id)
    if uid in tokens:
        bot.reply_to(message, "✅ Gmail connecté et opérationnel !")
    else:
        bot.reply_to(message, "❌ Gmail pas connecté. Utilise `/connectergmail`.", parse_mode="Markdown")

# ─────────────────────────────────────────────
# GMAIL — FLOW CONVERSATIONNEL ENVOYER
# ─────────────────────────────────────────────
@bot.message_handler(commands=['envoyer'])
def envoyer_mail(message):
    service = get_gmail_service(message.from_user.id)
    if not service:
        bot.reply_to(message, "❌ Gmail pas connecté. Utilise `/connectergmail` d'abord.", parse_mode="Markdown")
        return
    conversation_state[message.from_user.id] = {"etape": "destinataire", "type": "envoi"}
    bot.reply_to(message, "📧 *Envoyer un mail*\n\nÀ qui ? _(adresse email)_", parse_mode="Markdown")

@bot.message_handler(commands=['brouillon'])
def creer_brouillon(message):
    service = get_gmail_service(message.from_user.id)
    if not service:
        bot.reply_to(message, "❌ Gmail pas connecté. Utilise `/connectergmail` d'abord.", parse_mode="Markdown")
        return
    conversation_state[message.from_user.id] = {"etape": "destinataire", "type": "brouillon"}
    bot.reply_to(message, "📝 *Créer un brouillon*\n\nÀ qui ? _(adresse email)_", parse_mode="Markdown")

# ─────────────────────────────────────────────
# GESTIONNAIRE CONVERSATIONNEL
# ─────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.from_user.id in conversation_state and not m.text.startswith('/'))
def gerer_conversation(message):
    uid = message.from_user.id
    state = conversation_state[uid]
    etape = state["etape"]
    texte = message.text.strip()

    if etape == "destinataire":
        state["destinataire"] = texte
        state["etape"] = "sujet"
        bot.reply_to(message, "✏️ Quel est le *sujet* du mail ?", parse_mode="Markdown")

    elif etape == "sujet":
        state["sujet"] = texte
        state["etape"] = "message"
        bot.reply_to(message, "💬 Écris ton *message* :", parse_mode="Markdown")

    elif etape == "message":
        state["message"] = texte
        del conversation_state[uid]

        destinataire = state["destinataire"]
        sujet = state["sujet"]
        corps = state["message"]
        type_action = state["type"]

        service = get_gmail_service(uid)
        if not service:
            bot.reply_to(message, "❌ Gmail déconnecté. Utilise `/connectergmail`.", parse_mode="Markdown")
            return

        try:
            mime = MIMEText(corps)
            mime['to'] = destinataire
            mime['subject'] = sujet
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()

            if type_action == "envoi":
                service.users().messages().send(userId='me', body={'raw': raw}).execute()
                bot.reply_to(message, f"📧 Mail envoyé à *{destinataire}* ✅", parse_mode="Markdown")
            else:
                service.users().drafts().create(userId='me', body={'message': {'raw': raw}}).execute()
                bot.reply_to(message, f"📝 Brouillon créé pour *{destinataire}* ✅\nSujet : *{sujet}*", parse_mode="Markdown")

        except Exception as e:
            bot.reply_to(message, f"❌ Erreur : `{str(e)}`", parse_mode="Markdown")

# ─────────────────────────────────────────────
# FLASK ROUTES
# ─────────────────────────────────────────────
@app.route('/', methods=['GET'])
def index():
    return "Bot EasyLife — envoie /start dans Telegram !"

@app.route('/oauth/callback', methods=['GET'])
def oauth_callback():
    state = request.args.get('state')
    code = request.args.get('code')
    if not state or state not in pending_oauth:
        return "❌ Session OAuth invalide ou expirée.", 400
    uid = pending_oauth.pop(state)
    try:
        flow = make_flow()
        flow.state = state
        flow.fetch_token(code=code)
        creds = flow.credentials
        save_tokens(uid, {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "scopes": list(creds.scopes) if creds.scopes else []
        })
        bot.send_message(uid, "✅ Gmail connecté ! Tu peux utiliser `/envoyer` et `/brouillon`.", parse_mode="Markdown")
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
