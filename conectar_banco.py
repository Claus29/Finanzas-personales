"""Conecta tu cuenta de N26 (solo lectura) y guarda el EB_SESSION_ID en el archivo .env.

Ejecútalo la primera vez y cada vez que caduque el permiso (como mucho cada 6 meses):
    python conectar_banco.py
"""
import os
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv, set_key

from banco import EnableBanking, uids_de_cuentas

load_dotenv()

eb = EnableBanking(os.environ["EB_APP_ID"], os.environ["EB_KEY_PATH"])
banco = eb.buscar_banco("N26", os.environ.get("EB_COUNTRY", "ES"))
url, dias = eb.iniciar_autorizacion(banco, os.environ.get("EB_REDIRECT_URL", "https://localhost/callback"))

print(f"\n1) Abre este enlace y autoriza en N26 (permiso de {dias} días):\n\n{url}\n")
vuelta = input("2) Pega aquí la URL completa a la que te ha devuelto el navegador:\n> ").strip()
code = parse_qs(urlparse(vuelta).query).get("code", [vuelta])[0]

sesion = eb.crear_sesion(code)
set_key(".env", "EB_SESSION_ID", sesion["session_id"])
print("\n✅ Conectado. EB_SESSION_ID guardado en .env\n")

for uid in uids_de_cuentas(sesion):
    importe, moneda, _ = eb.saldo_actual(uid)
    print(f"Cuenta {uid}: {importe} {moneda}")
