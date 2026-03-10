import requests

token = 'TON_NOUVEL_TOKEN'  # après revoke
url = f"https://api.telegram.org/bot{token}/getUpdates?offset=-1&timeout=10"
response = requests.get(url)
print("Statut :", response.status_code)
print("Réponse :", response.text)
