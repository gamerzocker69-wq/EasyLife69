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

SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/calendar.events'
]

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

def get_calendar_service(user_id):
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
    return build("calendar", "v3", credentials=creds)

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
# ÉTAT CONVERSATIONNEL
# ─────────────────────────────────────────────
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
        "`/fait` — cocher une habitude (boutons)\n"
        "`/habitudes` — voir tes habitudes & streaks\n"
        "`/supprimerhabitude` — supprimer une habitude\n\n"
        "━━━ 📋 TÂCHES ━━━\n"
        "`/ajoutertache [tâche]` — ajouter une tâche\n"
        "`/taches` — voir & cocher les tâches\n"
        "`/nettoyertaches` — vider les tâches terminées\n\n"
        "━━━ 📝 NOTES ━━━\n"
        "`/note [texte]` — sauvegarder une note\n"
        "`/notes` — voir tes notes récentes\n\n"
        "━━━ 😊 HUMEUR ━━━\n"
        "`/humeur` — logger ton humeur (boutons)\n\n"
        "━━━ 📊 RÉCAPS ━━━\n"
        "`/recap` — récap du jour\n"
        "`/semaine` — bilan de la semaine\n\n"
        "━━━ 📧 GMAIL ━━━\n"
        "`/connectergmail` — connecter Gmail & Calendar\n"
        "`/envoyer` — envoyer un mail (guidé)\n"
        "`/brouillon` — créer un brouillon (guidé)\n\n"
        "━━━ 📅 AGENDA ━━━\n"
        "`/rdv` — créer un event (guidé)\n"
        "`/agenda` — voir les prochains events\n"
        "`/gmailstatut` — vérifier la connexion\n\n"
        "━━━ 💰 BUDGET ━━━\n"
        "`/depense` — logger une dépense (guidé)\n"
        "`/revenu` — logger un revenu (guidé)\n"
        "`/budget` — solde & récap du mois\n"
        "`/budgetmois` — toutes les dépenses détaillées\n"
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
    bot.reply_to(message, f"✅ Habitude *{nom}* ajoutée ! 💪", parse_mode="Markdown")

@bot.message_handler(commands=['fait'])
def fait_habitude(message):
    user, _ = get_user(message.from_user.id)
    if not user["habitudes"]:
        bot.reply_to(message, "Pas encore d'habitudes. Utilise `/ajouterhabitude [nom]`.", parse_mode="Markdown")
        return
    t = today()
    # Construire les boutons — coché ou pas
    markup = types.InlineKeyboardMarkup(row_width=2)
    boutons = []
    for nom, h in user["habitudes"].items():
        faite = h["dernier_fait"] == t
        label = f"✅ {nom}" if faite else f"⬜ {nom}"
        boutons.append(types.InlineKeyboardButton(label, callback_data=f"fait:{nom}"))
    markup.add(*boutons)
    bot.reply_to(message, "💪 *Coche tes habitudes du jour :*", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("fait:"))
def callback_fait_habitude(call):
    nom = call.data.split(":", 1)[1]
    user, _ = get_user(call.from_user.id)
    if nom not in user["habitudes"]:
        bot.answer_callback_query(call.id, "Habitude introuvable.")
        return
    habitude = user["habitudes"][nom]
    t = today()
    if habitude["dernier_fait"] == t:
        bot.answer_callback_query(call.id, f"✅ {nom} déjà cochée aujourd'hui !")
        return
    hier = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    habitude["streak"] = (habitude["streak"] + 1) if habitude["dernier_fait"] == hier else 1
    habitude["dernier_fait"] = t
    habitude["historique"].append(t)
    save_user(call.from_user.id, user)
    streak = habitude["streak"]
    emoji = "🔥" if streak >= 7 else "⚡" if streak >= 3 else "✅"
    bot.answer_callback_query(call.id, f"{emoji} {nom} cochée ! Streak : {streak}j")
    # Mettre à jour les boutons
    markup = types.InlineKeyboardMarkup(row_width=2)
    boutons = []
    for n, h in user["habitudes"].items():
        faite = h["dernier_fait"] == t
        label = f"✅ {n}" if faite else f"⬜ {n}"
        boutons.append(types.InlineKeyboardButton(label, callback_data=f"fait:{n}"))
    markup.add(*boutons)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    except:
        pass

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
    user, _ = get_user(message.from_user.id)
    if not user["habitudes"]:
        bot.reply_to(message, "Pas d'habitudes à supprimer.", parse_mode="Markdown")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    boutons = [types.InlineKeyboardButton(f"🗑️ {nom}", callback_data=f"supprimer_hab:{nom}") for nom in user["habitudes"]]
    markup.add(*boutons)
    bot.reply_to(message, "Quelle habitude supprimer ?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("supprimer_hab:"))
def callback_supprimer_habitude(call):
    nom = call.data.split(":", 1)[1]
    user, _ = get_user(call.from_user.id)
    if nom in user["habitudes"]:
        del user["habitudes"][nom]
        save_user(call.from_user.id, user)
        bot.answer_callback_query(call.id, f"🗑️ {nom} supprimée !")
        bot.edit_message_text(f"🗑️ Habitude *{nom}* supprimée.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    else:
        bot.answer_callback_query(call.id, "Introuvable.")

# ─────────────────────────────────────────────
# TÂCHES avec boutons
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
    markup = types.InlineKeyboardMarkup(row_width=1)
    for i, t in enumerate(user["taches"]):
        if not t["faite"]:
            markup.add(types.InlineKeyboardButton(f"⬜ {t['tache']}", callback_data=f"tache_done:{i}"))
    bot.reply_to(message, "📋 *Tes tâches — clique pour terminer :*", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("tache_done:"))
def callback_tache_done(call):
    idx = int(call.data.split(":")[1])
    user, _ = get_user(call.from_user.id)
    if idx < len(user["taches"]) and not user["taches"][idx]["faite"]:
        nom = user["taches"][idx]["tache"]
        user["taches"][idx]["faite"] = True
        save_user(call.from_user.id, user)
        bot.answer_callback_query(call.id, f"✅ {nom} terminée !")
        # Rafraîchir les boutons
        en_cours = [(i, t) for i, t in enumerate(user["taches"]) if not t["faite"]]
        if en_cours:
            markup = types.InlineKeyboardMarkup(row_width=1)
            for i, t in en_cours:
                markup.add(types.InlineKeyboardButton(f"⬜ {t['tache']}", callback_data=f"tache_done:{i}"))
            try:
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
            except:
                pass
        else:
            try:
                bot.edit_message_text("✅ Toutes les tâches sont terminées !", call.message.chat.id, call.message.message_id)
            except:
                pass
    else:
        bot.answer_callback_query(call.id, "Déjà terminée !")

@bot.message_handler(commands=['nettoyertaches'])
def nettoyer_taches(message):
    user, _ = get_user(message.from_user.id)
    avant = len(user["taches"])
    user["taches"] = [t for t in user["taches"] if not t["faite"]]
    save_user(message.from_user.id, user)
    bot.reply_to(message, f"🧹 {avant - len(user['taches'])} tâche(s) supprimée(s).")

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
# HUMEUR avec boutons
# ─────────────────────────────────────────────
HUMEUR_EMOJIS = {1: "😞", 2: "😕", 3: "😐", 4: "😊", 5: "🤩"}

@bot.message_handler(commands=['humeur'])
def logger_humeur(message):
    markup = types.InlineKeyboardMarkup(row_width=5)
    boutons = [types.InlineKeyboardButton(f"{HUMEUR_EMOJIS[i]} {i}", callback_data=f"humeur:{i}") for i in range(1, 6)]
    markup.add(*boutons)
    bot.reply_to(message, "😊 *Comment tu te sens aujourd'hui ?*", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("humeur:"))
def callback_humeur(call):
    score = int(call.data.split(":")[1])
    user, _ = get_user(call.from_user.id)
    user["humeur"].append({"score": score, "date": today()})
    save_user(call.from_user.id, user)
    bot.answer_callback_query(call.id, f"{HUMEUR_EMOJIS[score]} Humeur {score}/5 enregistrée !")
    bot.edit_message_text(f"{HUMEUR_EMOJIS[score]} Humeur *{score}/5* enregistrée pour aujourd'hui.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

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
        lines.append("_Pas encore loggée — `/humeur`_")
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
        markup.add(types.InlineKeyboardButton("🔗 Connecter Gmail & Agenda", url=auth_url))
        bot.reply_to(message, "Clique pour connecter ton Gmail et Google Agenda ✅\n_Une fois autorisé, reviens ici !_", parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        bot.reply_to(message, f"❌ Erreur : `{str(e)}`", parse_mode="Markdown")

@bot.message_handler(commands=['gmailstatut'])
def gmail_statut(message):
    tokens = load_tokens()
    uid = str(message.from_user.id)
    if uid in tokens:
        bot.reply_to(message, "✅ Gmail & Agenda connectés et opérationnels !")
    else:
        bot.reply_to(message, "❌ Pas connecté. Utilise `/connectergmail`.", parse_mode="Markdown")

# ─────────────────────────────────────────────
# GMAIL — FLOW CONVERSATIONNEL
# ─────────────────────────────────────────────
@bot.message_handler(commands=['envoyer'])
def envoyer_mail(message):
    if not get_gmail_service(message.from_user.id):
        bot.reply_to(message, "❌ Gmail pas connecté. Utilise `/connectergmail`.", parse_mode="Markdown")
        return
    conversation_state[message.from_user.id] = {"etape": "destinataire", "type": "envoi"}
    bot.reply_to(message, "📧 *Envoyer un mail*\n\nÀ qui ? _(adresse email)_", parse_mode="Markdown")

@bot.message_handler(commands=['brouillon'])
def creer_brouillon(message):
    if not get_gmail_service(message.from_user.id):
        bot.reply_to(message, "❌ Gmail pas connecté. Utilise `/connectergmail`.", parse_mode="Markdown")
        return
    conversation_state[message.from_user.id] = {"etape": "destinataire", "type": "brouillon"}
    bot.reply_to(message, "📝 *Créer un brouillon*\n\nÀ qui ? _(adresse email)_", parse_mode="Markdown")

# ─────────────────────────────────────────────
# AGENDA — FLOW CONVERSATIONNEL
# ─────────────────────────────────────────────
@bot.message_handler(commands=['rdv'])
def creer_rdv(message):
    if not get_calendar_service(message.from_user.id):
        bot.reply_to(message, "❌ Agenda pas connecté. Utilise `/connectergmail`.", parse_mode="Markdown")
        return
    conversation_state[message.from_user.id] = {"etape": "rdv_titre", "type": "rdv"}
    bot.reply_to(message, "📅 *Créer un rendez-vous*\n\nQuel est le titre ? _(ex: Dentiste, Réunion équipe)_", parse_mode="Markdown")

@bot.message_handler(commands=['agenda'])
def voir_agenda(message):
    service = get_calendar_service(message.from_user.id)
    if not service:
        bot.reply_to(message, "❌ Agenda pas connecté. Utilise `/connectergmail`.", parse_mode="Markdown")
        return
    try:
        maintenant = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary',
            timeMin=maintenant,
            maxResults=5,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        if not events:
            bot.reply_to(message, "📅 Aucun événement à venir dans ton agenda.")
            return
        lines = ["📅 *Tes 5 prochains événements :*\n"]
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date', ''))
            if 'T' in start:
                dt = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                start_str = dt.strftime("%d/%m à %Hh%M")
            else:
                start_str = start
            lines.append(f"• *{event.get('summary', 'Sans titre')}* — {start_str}")
        bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erreur : `{str(e)}`", parse_mode="Markdown")

# ─────────────────────────────────────────────
# GESTIONNAIRE CONVERSATIONNEL UNIFIÉ
# ─────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.from_user.id in conversation_state and not m.text.startswith('/'))
def gerer_conversation(message):
    uid = message.from_user.id
    state = conversation_state[uid]
    etape = state["etape"]
    texte = message.text.strip()

    # ── FLOW EMAIL / BROUILLON ──
    if etape == "destinataire":
        state["destinataire"] = texte
        state["etape"] = "sujet"
        bot.reply_to(message, "✏️ Quel est le *sujet* ?", parse_mode="Markdown")

    elif etape == "sujet":
        state["sujet"] = texte
        state["etape"] = "message"
        bot.reply_to(message, "💬 Écris ton *message* :", parse_mode="Markdown")

    elif etape == "message":
        state["message"] = texte
        del conversation_state[uid]
        service = get_gmail_service(uid)
        if not service:
            bot.reply_to(message, "❌ Gmail déconnecté.", parse_mode="Markdown")
            return
        try:
            mime = MIMEText(state["message"])
            mime['to'] = state["destinataire"]
            mime['subject'] = state["sujet"]
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
            if state["type"] == "envoi":
                service.users().messages().send(userId='me', body={'raw': raw}).execute()
                bot.reply_to(message, f"📧 Mail envoyé à *{state['destinataire']}* ✅", parse_mode="Markdown")
            else:
                service.users().drafts().create(userId='me', body={'message': {'raw': raw}}).execute()
                bot.reply_to(message, f"📝 Brouillon créé pour *{state['destinataire']}* ✅", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Erreur : `{str(e)}`", parse_mode="Markdown")

    # ── FLOW BUDGET ──
    elif etape == "budget_montant":
        try:
            montant = float(texte.replace(",", ".").replace("€", "").strip())
            state["montant"] = montant
            if state["type"] == "revenu":
                # Pas besoin de catégorie pour un revenu
                state["etape"] = "budget_description"
                bot.reply_to(message, "💬 Description ? _(ex: Salaire mars — ou tape *skip*)_", parse_mode="Markdown")
            else:
                state["etape"] = "budget_categorie"
                markup = types.InlineKeyboardMarkup(row_width=2)
                boutons = [types.InlineKeyboardButton(label, callback_data=f"cat:{key}") for key, label in CATEGORIES_BUDGET.items()]
                markup.add(*boutons)
                bot.reply_to(message, f"💸 *{montant:.2f}€* — Quelle catégorie ?", parse_mode="Markdown", reply_markup=markup)
        except:
            bot.reply_to(message, "❌ Montant invalide. Essaie *45.50* ou *120*", parse_mode="Markdown")

    elif etape == "budget_description":
        description = "" if texte.lower() == "skip" else texte
        del conversation_state[uid]
        user, _ = get_user(uid)
        if "budget" not in user:
            user["budget"] = {"entrees": []}
        user["budget"]["entrees"].append({
            "type": state["type"],
            "montant": state["montant"],
            "categorie": state.get("categorie", "divers"),
            "description": description,
            "date": today(),
            "mois": get_mois()
        })
        save_user(uid, user)
        if state["type"] == "depense":
            label = CATEGORIES_BUDGET.get(state.get("categorie", "divers"), "divers")
            bot.reply_to(message, f"💸 Dépense de *{state['montant']:.2f}€* enregistrée\n{label}{f' — {description}' if description else ''} ✅", parse_mode="Markdown")
        else:
            bot.reply_to(message, f"💰 Revenu de *{state['montant']:.2f}€* enregistré{f' — {description}' if description else ''} ✅", parse_mode="Markdown")

    # ── FLOW RENDEZ-VOUS ──
    elif etape == "rdv_titre":
        state["titre"] = texte
        state["etape"] = "rdv_date"
        bot.reply_to(message, "📆 Quelle date ? _(ex: 2026-03-15 ou 15/03/2026)_", parse_mode="Markdown")

    elif etape == "rdv_date":
        # Accepte DD/MM/YYYY ou YYYY-MM-DD
        try:
            if "/" in texte:
                parts = texte.split("/")
                date_obj = datetime.date(int(parts[2]), int(parts[1]), int(parts[0]))
            else:
                date_obj = datetime.date.fromisoformat(texte)
            state["date"] = date_obj.isoformat()
            state["etape"] = "rdv_heure"
            bot.reply_to(message, "⏰ À quelle heure ? _(ex: 14h30 ou 14:30)_", parse_mode="Markdown")
        except:
            bot.reply_to(message, "❌ Format non reconnu. Essaie *15/03/2026* ou *2026-03-15*", parse_mode="Markdown")

    elif etape == "rdv_heure":
        try:
            texte_heure = texte.replace("h", ":").replace("H", ":")
            if ":" not in texte_heure:
                texte_heure = texte_heure + ":00"
            h, m = texte_heure.split(":")
            heure = datetime.time(int(h), int(m))
            state["heure"] = heure.strftime("%H:%M")
            state["etape"] = "rdv_duree"
            bot.reply_to(message, "⏱️ Durée en minutes ? _(ex: 30, 60, 90 — tape 0 pour toute la journée)_", parse_mode="Markdown")
        except:
            bot.reply_to(message, "❌ Format non reconnu. Essaie *14h30* ou *14:30*", parse_mode="Markdown")

    elif etape == "rdv_duree":
        try:
            duree = int(texte)
            del conversation_state[uid]
            service = get_calendar_service(uid)
            if not service:
                bot.reply_to(message, "❌ Agenda déconnecté.", parse_mode="Markdown")
                return

            date_str = state["date"]
            heure_str = state["heure"]
            titre = state["titre"]

            if duree == 0:
                # Événement toute la journée
                event = {
                    'summary': titre,
                    'start': {'date': date_str},
                    'end': {'date': date_str},
                }
            else:
                debut = datetime.datetime.fromisoformat(f"{date_str}T{heure_str}:00")
                fin = debut + datetime.timedelta(minutes=duree)
                event = {
                    'summary': titre,
                    'start': {'dateTime': debut.isoformat(), 'timeZone': 'Europe/Paris'},
                    'end': {'dateTime': fin.isoformat(), 'timeZone': 'Europe/Paris'},
                }

            created = service.events().insert(calendarId='primary', body=event).execute()
            date_affiche = datetime.date.fromisoformat(date_str).strftime("%d/%m/%Y")
            bot.reply_to(message, f"📅 Rendez-vous *{titre}* créé !\n📆 {date_affiche} à {heure_str}\n⏱️ {'Toute la journée' if duree == 0 else f'{duree} min'} ✅", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Erreur : `{str(e)}`", parse_mode="Markdown")

# ─────────────────────────────────────────────
# FLASK ROUTES
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# BUDGET
# ─────────────────────────────────────────────
CATEGORIES_BUDGET = {
    "loyer": "🏠 Loyer",
    "nourriture": "🛒 Nourriture",
    "abonnements": "📺 Abonnements",
    "energie": "⚡ Énergie",
    "transports": "🚇 Transports",
    "telephone": "📱 Téléphone",
    "credit": "💳 Crédit",
    "loisirs": "🎮 Loisirs",
    "sante": "💊 Santé",
    "shopping": "👕 Shopping",
    "divers": "🔧 Divers"
}

def get_mois():
    return datetime.date.today().strftime("%Y-%m")

@bot.message_handler(commands=["depense"])
def ajouter_depense(message):
    conversation_state[message.from_user.id] = {"etape": "budget_montant", "type": "depense"}
    bot.reply_to(message, "💸 *Nouvelle dépense*\n\nMontant ? _(ex: 45.50)_", parse_mode="Markdown")

@bot.message_handler(commands=["revenu"])
def ajouter_revenu(message):
    conversation_state[message.from_user.id] = {"etape": "budget_montant", "type": "revenu"}
    bot.reply_to(message, "💰 *Nouveau revenu*\n\nMontant ? _(ex: 2500)_", parse_mode="Markdown")

@bot.message_handler(commands=["budget"])
def voir_budget(message):
    user, _ = get_user(message.from_user.id)
    mois = get_mois()
    budget = user.get("budget", {})
    entrees = [e for e in budget.get("entrees", []) if e["mois"] == mois]
    total_revenus = sum(e["montant"] for e in entrees if e["type"] == "revenu")
    total_depenses = sum(e["montant"] for e in entrees if e["type"] == "depense")
    solde = total_revenus - total_depenses
    emoji_solde = "✅" if solde >= 0 else "🔴"
    lines = [f"💰 *Budget — {mois}*\n"]
    lines.append(f"📈 Revenus : *+{total_revenus:.2f}€*")
    lines.append(f"📉 Dépenses : *-{total_depenses:.2f}€*")
    lines.append(f"{emoji_solde} Solde : *{solde:+.2f}€*")
    if total_depenses > 0:
        lines.append("\n━━━ Par catégorie ━━━")
        cats = {}
        for e in entrees:
            if e["type"] == "depense":
                cat = e.get("categorie", "divers")
                cats[cat] = cats.get(cat, 0) + e["montant"]
        for cat, montant in sorted(cats.items(), key=lambda x: x[1], reverse=True):
            label = CATEGORIES_BUDGET.get(cat, cat)
            pct = (montant / total_depenses * 100) if total_depenses > 0 else 0
            barre = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            lines.append(f"{label}\n`{barre}` {montant:.2f}€ ({pct:.0f}%)")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=["budgetmois"])
def detail_budget_mois(message):
    user, _ = get_user(message.from_user.id)
    mois = get_mois()
    budget = user.get("budget", {})
    entrees = [e for e in budget.get("entrees", []) if e["mois"] == mois and e["type"] == "depense"]
    if not entrees:
        bot.reply_to(message, "Aucune dépense ce mois-ci. Utilise `/depense` pour en ajouter.", parse_mode="Markdown")
        return
    lines = [f"📋 *Dépenses détaillées — {mois}*\n"]
    for e in sorted(entrees, key=lambda x: x["date"], reverse=True)[:20]:
        label = CATEGORIES_BUDGET.get(e.get("categorie", "divers"), e.get("categorie", "divers"))
        desc = f" — {e['description']}" if e.get("description") else ""
        lines.append(f"• {label} *{e['montant']:.2f}€*{desc} `{e['date']}`")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("cat:"))
def callback_categorie(call):
    cat = call.data.split(":", 1)[1]
    uid = call.from_user.id
    if uid not in conversation_state:
        bot.answer_callback_query(call.id, "Session expirée.")
        return
    state = conversation_state[uid]
    state["categorie"] = cat
    state["etape"] = "budget_description"
    label = CATEGORIES_BUDGET.get(cat, cat)
    bot.answer_callback_query(call.id, f"{label} sélectionné")
    bot.edit_message_text(
        f"Catégorie : {label} ✅\n\n💬 Description ? _(ex: Courses Lidl — ou tape *skip* pour passer)_",
        call.message.chat.id, call.message.message_id, parse_mode="Markdown"
    )

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
        bot.send_message(uid, "✅ Gmail & Google Agenda connectés ! Utilise `/envoyer`, `/brouillon` et `/rdv`.", parse_mode="Markdown")
        return "<h2>✅ Connecté ! Retourne sur Telegram.</h2>"
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
