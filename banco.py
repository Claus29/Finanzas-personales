"""Cliente mínimo de la API de Enable Banking (solo lectura de cuentas, AIS)."""
import time
from datetime import datetime, timedelta, timezone

import jwt
import requests

API = "https://api.enablebanking.com"

# Orden de preferencia para el "saldo actual": disponible ahora > disponible al cierre > contable.
TIPOS_SALDO = ["ITAV", "CLAV", "XPCD", "ITBD", "CLBD", "OPAV", "OPBD"]


class ErrorBanco(Exception):
    def __init__(self, estado, texto):
        super().__init__(f"Error {estado}: {texto}")
        self.estado = estado
        self.texto = texto

    @property
    def permiso_caducado(self):
        return self.estado == 401 or any(c in self.texto for c in ("EXPIRED_SESSION", "REVOKED", "CLOSED_SESSION"))

    @property
    def demasiadas_consultas(self):
        return self.estado == 429


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
            raise ErrorBanco(r.status_code, r.text)
        return r.json()

    # --- Llamadas a Enable Banking (no llegan al banco: no cuentan en el límite diario) ---

    def aplicacion(self):
        return self._api("GET", "/application")

    def bancos(self, pais):
        return self._api("GET", "/aspsps", params={"country": pais})["aspsps"]

    def iniciar_autorizacion(self, banco, redirect_url, dias, state):
        return self._api("POST", "/auth", json={
            "access": {"valid_until": (datetime.now(timezone.utc) + timedelta(days=dias)).isoformat()},
            "aspsp": {"name": banco["name"], "country": banco["country"]},
            "state": state,
            "redirect_url": redirect_url,
            "psu_type": "personal",
        })["url"]

    def crear_sesion(self, code):
        return self._api("POST", "/sessions", json={"code": code})

    def sesion(self, session_id):
        return self._api("GET", f"/sessions/{session_id}")

    # --- Llamadas que llegan al banco (cuentan en el límite diario) ---

    def saldos(self, uid):
        return self._api("GET", f"/accounts/{uid}/balances").get("balances", [])


def elegir_saldo(saldos):
    """Devuelve (importe, moneda, tipo) del saldo más representativo, o None si no hay ninguno."""
    if not saldos:
        return None
    elegido = min(saldos, key=lambda b: TIPOS_SALDO.index(b.get("balance_type"))
                  if b.get("balance_type") in TIPOS_SALDO else len(TIPOS_SALDO))
    return elegido["balance_amount"]["amount"], elegido["balance_amount"]["currency"], elegido.get("balance_type")
