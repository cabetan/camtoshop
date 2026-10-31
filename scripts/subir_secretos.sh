#!/bin/zsh
# Copia las credenciales del llavero del Mac a Secret Manager. No las muestra en pantalla.
P=camtoshop-app-df5f
for s in CAMTOSHOP_CLAVE IG_USUARIO_ID META_APP_SECRET META_CATALOGO_ID META_TOKEN MODEL_API_KEY SHOPIFY_CLIENT_ID \
         SHOPIFY_CLIENT_SECRET SHOPIFY_DOMINIO_PUBLICO SHOPIFY_TIENDA WA_TELEFONO_ID WA_TOKEN WA_VERIFICACION; do
  v=$(security find-generic-password -a "$USER" -s $s -w 2>/dev/null)
  if [ -z "$v" ]; then echo "$s: no está en el llavero"; continue; fi
  gcloud secrets create $s --project $P --replication-policy=automatic >/dev/null 2>&1
  printf %s "$v" | gcloud secrets versions add $s --project $P --data-file=- >/dev/null 2>&1 && echo "$s: ok" || echo "$s: FALLÓ"
done
unset v
