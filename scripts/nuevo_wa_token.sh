#!/bin/zsh
# Toma el token de WhatsApp del portapapeles (o el del llavero), lo cambia por uno de 60 días si es temporal,
# lo guarda en el llavero y en Secret Manager y reinicia el servicio. No lo muestra.
P=camtoshop-app-df5f; R=us-central1
cd "$(dirname "$0")/.."
v=$(pbpaste); case "$v" in
  EAA*) echo "origen: portapapeles";;
  *) echo "origen: llavero (el portapapeles no trae un token)"; v=$(security find-generic-password -a "$USER" -s WA_TOKEN -w);;
esac
n=$(printf %s "$v" | .venv/bin/python -c "
import sys, requests
from camtoshop.adaptadores.config import secreto
t = sys.stdin.read().strip()
r = requests.get('https://graph.facebook.com/v23.0/oauth/access_token', timeout=30, params={
    'grant_type': 'fb_exchange_token', 'client_id': '2033143300693121',
    'client_secret': secreto('META_APP_SECRET'), 'fb_exchange_token': t})
if not r.ok:
    sys.exit(r.json().get('error', {}).get('message', 'Meta rechazó el token'))
print(r.json()['access_token'])
" 2>&1 | tail -1)
case "$n" in EAA*) ;; *) echo "Meta respondió: $n"; exit 1;; esac
security add-generic-password -U -a "$USER" -s WA_TOKEN -w "$n" && echo "llavero: ok"
printf %s "$n" | gcloud secrets versions add WA_TOKEN --project $P --data-file=- >/dev/null 2>&1 && echo "nube: ok"
unset v n; pbcopy < /dev/null
gcloud run services update camtoshop --project $P --region $R --update-env-vars WA_TOKEN_ROTADO=$(date +%s) 2>&1 | tail -1
