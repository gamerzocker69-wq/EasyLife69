import os
from flask import Flask, request
import telebot

app = Flask(__name__)

TOKEN = os.getenv('TOKEN')
bot = telebot.TeleBot(TOKEN)

# Tes handlers (exemple minimal, ajoute les tiens)
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Yo ! Bot productivité ready 🚀\nAjoute /addtodo [tâche] etc.")

# Ajoute tes autres handlers ici (/addtodo, /listtodo, etc.)

@app.route('/', methods=['GET'])
def index():
    return "Bot webhook ready - envoie /start dans Telegram !"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK'
    else:
        return 'Bad request', 403

if __name__ == '__main__':
    # Au démarrage : clean webhook old + set nouveau (exécute une fois, ou commente après)
    # bot.remove_webhook()
    # webhook_url = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}/{TOKEN}"  # Railway donne le domaine auto
    # bot.set_webhook(url=webhook_url)
    # print("Webhook set à :", webhook_url)

    port = int(os.getenv('PORT', 8080))  # Railway utilise PORT env
    app.run(host='0.0.0.0', port=port)
