"""Crea el comercio demo, que publica con las cuentas de Camtoshop, y le vincula un celular.

Uso: python scripts/sembrar_demo.py 573001234567
La clave del portal se genera y queda en el llavero como CAMTOSHOP_DEMO_CLAVE; no se imprime.
"""

import os
import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from camtoshop.adaptadores.config import secreto
from camtoshop.adaptadores.repo_comercios import RepoComercios
from camtoshop.aplicacion.servicio import DATOS
from camtoshop.dominio.comercio import normalizar_celular
from camtoshop.dominio.portal import resumir_clave

CORREO = "demo@camtoshop.app"

repo = RepoComercios(DATOS.parent)
demo = repo.por_correo(CORREO) or repo.crear("Camtoshop Demo", CORREO)
demo.demo = True
demo.conexiones.instagram_id = secreto("IG_USUARIO_ID") or ""
demo.conexiones.instagram_usuario = "camtoshop.app"
demo.conexiones.pagina_nombre = "Camtoshop"
demo.conexiones.shopify_tienda = secreto("SHOPIFY_TIENDA") or ""
celular = normalizar_celular(sys.argv[1])
if celular not in demo.celulares:
    demo.celulares.append(celular)
repo.guardar(demo)
if not repo.token(demo.id, "clave"):
    clave = secrets.token_urlsafe(18)
    subprocess.run(["security", "add-generic-password", "-U", "-a", os.environ.get("USER", ""),
                    "-s", "CAMTOSHOP_DEMO_CLAVE", "-w", clave], check=True, capture_output=True)
    repo.guardar_token(demo.id, "clave", resumir_clave(clave))
print(f"Comercio demo listo: {demo.id}, {len(demo.celulares)} celular(es)")
