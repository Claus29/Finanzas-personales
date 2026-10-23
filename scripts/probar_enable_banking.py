"""Prueba de conexión con Enable Banking: lee saldos y movimientos de tus cuentas N26.

Uso:
    export EB_APP_ID="tu-application-id"
    export EB_KEY_PATH="/ruta/a/tu-application-id.pem"
    python scripts/probar_enable_banking.py              # autoriza y crea una sesión nueva
    python scripts/probar_enable_banking.py SESSION_ID   # reutiliza una sesión ya creada
"""
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import requests

API = "https://api.enablebanking.com"
APP_ID = os.environ["EB_APP_ID"]
KEY_PATH = os.environ.get("EB_KEY_PATH", f"{APP_ID}.pem")
COUNTRY = os.environ.get("EB_COUNTRY", "ES")
REDIRECT_URL = os.environ.get("EB_REDIRECT_URL", "https://localhost/callback")

with open(KEY_PATH) as f:
    PRIVATE_KEY = f.read()


def headers():
    now = int(time.time())
    token = jwt.encode(
        {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": now, "exp": now + 3600},
        PRIVATE_KEY,
        algorithm="RS256",
        headers={"kid": APP_ID},
    )
    return {"Authorization": f"Bearer {token}"}


def api(method, path, **kwargs):
    r = requests.request(method, f"{API}{path}", headers=headers(), timeout=30, **kwargs)
    if not r.ok:
        sys.exit(f"Error {r.status_code} en {method} {path}: {r.text}")
    return r.json()


def buscar_n26():
    bancos = api("GET", "/aspsps", params={"country": COUNTRY})["aspsps"]
    n26 = [b for b in bancos if "N26" in b["name"].upper()]
    if not n26:
        sys.exit(f"N26 no aparece en la lista de bancos de {COUNTRY}. Prueba con EB_COUNTRY=DE.")
    return n26[0]


def crear_sesion():
    banco = buscar_n26()
    dias = min(90, banco.get("maximum_consent_validity", 90 * 86400) // 86400)
    auth = api("POST", "/auth", json={
        "access": {"valid_until": (datetime.now(timezone.utc) + timedelta(days=dias)).isoformat()},
        "aspsp": {"name": banco["name"], "country": banco["country"]},
        "state": str(uuid.uuid4()),
        "redirect_url": REDIRECT_URL,
        "psu_type": "personal",
    })
    print(f"\n1) Abre este enlace y autoriza en N26 (permiso de {dias} días):\n\n{auth['url']}\n")
    vuelta = input("2) Pega aquí la URL completa a la que te ha devuelto el navegador:\n> ").strip()
    code = parse_qs(urlparse(vuelta).query).get("code", [vuelta])[0]
    sesion = api("POST", "/sessions", json={"code": code})
    print(f"\n✅ Sesión creada. Guarda este SESSION_ID para no tener que autorizar otra vez:\n{sesion['session_id']}")
    return sesion


def movimientos(uid, desde):
    params = {"date_from": desde.isoformat()}
    while True:
        datos = api("GET", f"/accounts/{uid}/transactions", params=params)
        yield from datos.get("transactions", [])
        if not datos.get("continuation_key"):
            break
        params["continuation_key"] = datos["continuation_key"]


def main():
    sesion = api("GET", f"/sessions/{sys.argv[1]}") if len(sys.argv) > 1 else crear_sesion()
    cuentas = sesion["accounts"]
    for cuenta in cuentas:
        uid = cuenta if isinstance(cuenta, str) else cuenta["uid"]
        print(f"\n=== Cuenta {uid} ===")
        for b in api("GET", f"/accounts/{uid}/balances").get("balances", []):
            print(f"Saldo ({b.get('balance_type')}): {b['balance_amount']['amount']} {b['balance_amount']['currency']}")
        print("\nMovimientos de los últimos 30 días:")
        for t in movimientos(uid, date.today() - timedelta(days=30)):
            signo = "-" if t.get("credit_debit_indicator") == "DBIT" else "+"
            otra_parte = (t.get("creditor") if signo == "-" else t.get("debtor")) or {}
            concepto = " ".join(t.get("remittance_information") or [])
            fecha = t.get("booking_date") or t.get("value_date") or t.get("transaction_date")
            importe = t["transaction_amount"]
            print(f"{fecha}  {signo}{importe['amount']:>10} {importe['currency']}  {otra_parte.get('name', '')}  {concepto}")


if __name__ == "__main__":
    main()
