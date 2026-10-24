"""Diagnóstico: muestra todo lo que devuelve el banco de cada cuenta (todos los tipos de saldo).

No envía nada a Telegram ni cuenta como la consulta diaria. El resultado se guarda en
diagnostico.txt (con los IBAN ocultos) para poder compartirlo.
    python diagnostico.py
"""
import json
import os
import sys

from banco import TIPOS_SALDO, uids_de_cuentas
from saldo import BASE, cargar_config, cliente

NOMBRES_SALDO = {
    "ITAV": "disponible ahora", "CLAV": "disponible al cierre", "XPCD": "previsto",
    "ITBD": "contable ahora", "CLBD": "contable al cierre", "OPAV": "disponible al abrir",
    "OPBD": "contable al abrir", "FWAV": "disponible futuro", "INFO": "informativo", "OTHR": "otro",
}
lineas = []


def mostrar(texto=""):
    print(texto)
    lineas.append(texto)


def ocultar_iban(iban):
    return f"{iban[:4]} **** {iban[-4:]}" if iban and len(iban) > 8 else (iban or "-")


def main():
    cargar_config()
    eb = cliente()
    sesion = eb.sesion(os.environ["EB_SESSION_ID"])
    mostrar("DIAGNOSTICO DEL BOT FINANZAS")
    mostrar(f"Estado del permiso: {sesion.get('status')}")
    mostrar(f"Banco: {sesion.get('aspsp', {}).get('name')} ({sesion.get('aspsp', {}).get('country')})")
    mostrar(f"Permiso valido hasta: {sesion.get('access', {}).get('valid_until')}")
    cuentas = uids_de_cuentas(sesion)
    mostrar(f"Cuentas en el permiso: {len(cuentas)}")

    for n, uid in enumerate(cuentas, 1):
        mostrar(f"\n=== Cuenta {n} ===")
        try:
            d = eb.detalles(uid)
            mostrar(f"Nombre: {d.get('name') or '-'}")
            mostrar(f"Producto: {d.get('product') or '-'}  |  Tipo: {d.get('cash_account_type') or '-'}"
                    f"  |  Uso: {d.get('usage') or '-'}  |  Moneda: {d.get('currency') or '-'}")
            mostrar(f"IBAN: {ocultar_iban((d.get('account_id') or {}).get('iban'))}")
            if d.get("details"):
                mostrar(f"Detalles: {d['details']}")
        except Exception as e:
            mostrar(f"Detalles: ERROR {e}")
        try:
            saldos = eb.saldos(uid)
        except Exception as e:
            mostrar(f"Saldos: ERROR {e}")
            continue
        if not saldos:
            mostrar("Saldos: el banco no ha devuelto ninguno")
        for b in saldos:
            tipo = b.get("balance_type")
            importe = b.get("balance_amount", {})
            mostrar(f"  Saldo {tipo} ({NOMBRES_SALDO.get(tipo, '?')}): {importe.get('amount')} {importe.get('currency')}"
                    f"  | nombre: {b.get('name') or '-'}  | fecha: {b.get('reference_date') or b.get('last_change_date_time') or '-'}")
        if saldos:
            elegido = min(saldos, key=lambda b: TIPOS_SALDO.index(b.get("balance_type"))
                          if b.get("balance_type") in TIPOS_SALDO else len(TIPOS_SALDO))
            mostrar(f"  -> El bot muestra el saldo {elegido.get('balance_type')}")

    otros = {k: v for k, v in sesion.items() if k not in ("accounts", "accounts_data", "session_id")}
    mostrar(f"\nDatos del permiso: {json.dumps(otros, ensure_ascii=False, default=str)}")
    (BASE / "diagnostico.txt").write_text("\n".join(lineas), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.exit(f"\nERROR: {e}")
