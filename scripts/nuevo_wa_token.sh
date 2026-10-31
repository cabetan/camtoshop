#!/bin/zsh
# Toma el token de WhatsApp del portapapeles, lo guarda en el llavero y en Secret Manager y reinicia el servicio.
P=camtoshop-app-df5f; R=us-central1
v=$(pbpaste)
case "$v" in EAA*) ;; *) echo "El portapapeles no parece un token de Meta"; exit 1;; esac
security add-generic-password -U -a "$USER" -s WA_TOKEN -w "$v" && echo "llavero: ok"
printf %s "$v" | gcloud secrets versions add WA_TOKEN --project $P --data-file=- >/dev/null 2>&1 && echo "nube: ok"
unset v; pbcopy < /dev/null
gcloud run services update camtoshop --project $P --region $R --update-env-vars WA_TOKEN_ROTADO=$(date +%s) 2>&1 | tail -1
