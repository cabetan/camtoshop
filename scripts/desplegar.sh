#!/bin/zsh
# Despliega Camtoshop en Cloud Run. Es público porque Meta y los comercios deben llegar sin cuenta de Google;
# la app solo expone por internet el portal y los webhooks, que validan sesión o firma.
P=camtoshop-app-df5f; R=us-central1; IMAGEN=${1:-app:1}
S=""
for s in CAMTOSHOP_CLAVE IG_USUARIO_ID META_APP_SECRET META_CATALOGO_ID META_TOKEN MODEL_API_KEY SHOPIFY_CLIENT_ID \
         SHOPIFY_CLIENT_SECRET SHOPIFY_TIENDA WA_TELEFONO_ID WA_TOKEN WA_VERIFICACION; do S="$S,${s}=${s}:latest"; done
gcloud run deploy camtoshop --project $P --region $R --image $R-docker.pkg.dev/$P/camtoshop/$IMAGEN \
  --allow-unauthenticated --no-cpu-throttling --cpu 2 --memory 4Gi --min-instances 0 --max-instances 1 \
  --concurrency 20 --timeout 900 --execution-environment gen2 \
  --add-volume name=datos,type=cloud-storage,bucket=$P-datos --add-volume-mount volume=datos,mount-path=/datos \
  --set-env-vars CAMTOSHOP_DATOS=/datos,TZ=America/Bogota --set-secrets "${S#,}"
