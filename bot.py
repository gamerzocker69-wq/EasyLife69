import os
TOKEN = os.getenv('8713779724:AAFJ3LZvGSqHfZp5vw_v4mb3c7olR5WshVw')
if not TOKEN:
    raise ValueError("TOKEN manquant ! Ajoute-le dans les variables Railway.")
