import os

TOKEN = os.getenv('TOKEN')  # ← ICI c'est 'TOKEN' (le nom exact de la variable que tu as créée sur Railway)

if not TOKEN:
    print("ERREUR : Aucune variable d'environnement nommée 'TOKEN' trouvée")
    raise ValueError("TOKEN manquant ! Ajoute-le dans les variables Railway.")
else:
    print(f"TOKEN chargé avec succès (longueur {len(TOKEN)} caractères)")
