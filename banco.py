"""Cliente mínimo de la API de Enable Banking (solo lectura de cuentas, AIS)."""
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import requests

API = "https://api.enablebanking.com"

# Orden de preferencia para el "saldo actual": disponible ahora > disponible al cierre > contable.
TIPOS_SALDO = ["ITAV", "CLAV", "XPCD", "ITBD", "CLBD", "OPAV", "OPBD"]


class ErrorBanco(Exception):
    pass


class EnableBanking:
    def __init__(self, app_id, key_path):
        self.app_id = app_id
        with open(key_path) as f:
            self.private_key = f.read()

    def _headers(self):
        now = int(time.time())
        token = jwt.encode(
            {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": now, "exp": now + 3600},
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.app_id},
        )
        return {"Authorization": f"Bearer {token}"}

    def _api(self, method, path, **kwargs):
        r = requests.request(method, f"{API}{path}", headers=self._headers(), timeout=30, **kwargs)
        if not r.ok:
            raise ErrorBanco(f"Error {r.status_code} en {method} {path}: {r.text}")
        return r.json()

    def buscar_banco(self, nombre, pais):
        bancos = self._api("GET", "/aspsps", params={"country": pais})["aspsps"]
        for banco in bancos:
            if nombre.upper() in banco["name"].upper():
                return banco
        raise ErrorBanco(f"{nombre} no aparece en la lista de bancos de {pais}.")

    def iniciar_autorizacion(self, banco, redirect_url, dias=90):
        maximo = banco.get("maximum_consent_validity", dias * 86400) // 86400
        dias = min(dias, maximo)
        auth = self._api("POST", "/auth", json={
            "access": {"valid_until": (datetime.now(timezone.utc) + timedelta(days=dias)).isoformat()},
            "aspsp": {"name": banco["name"], "country": banco["country"]},
            "state": str(uuid.uuid4()),
            "redirect_url": redirect_url,
            "psu_type": "personal",
        })
        return auth["url"], dias

    def crear_sesion(self, code):
        return self._api("POST", "/sessions", json={"code": code})

    def sesion(self, session_id):
        return self._api("GET", f"/sessions/{session_id}")

    def saldo_actual(self, uid):
        """Devuelve (importe, moneda, tipo) del saldo más representativo de la cuenta."""
        saldos = self._api("GET", f"/accounts/{uid}/balances").get("balances", [])
        if not saldos:
            raise ErrorBanco(f"La cuenta {uid} no ha devuelto ningún saldo.")
        saldos.sort(key=lambda b: TIPOS_SALDO.index(b.get("balance_type"))
                    if b.get("balance_type") in TIPOS_SALDO else len(TIPOS_SALDO))
        elegido = saldos[0]
        return elegido["balance_amount"]["amount"], elegido["balance_amount"]["currency"], elegido.get("balance_type")


def uids_de_cuentas(sesion):
    """La API devuelve las cuentas como lista de uids o como lista de objetos según el endpoint."""
    return [c if isinstance(c, str) else c["uid"] for c in sesion.get("accounts", [])]
