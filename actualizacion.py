"""Actualización diaria con el banco: saldos y movimientos de todas las cuentas, en silencio.

Es la ÚNICA vez que se pregunta al banco: a la hora configurada (00:00 por defecto) o, si el
ordenador estaba apagado, en cuanto vuelve. Además se puede forzar desde Ajustes («Actualizar
ahora»). Nunca envía notificaciones: lo que descubre de madrugada se avisa a partir de las 09:00.
"""
import logging
from datetime import date, timedelta

import requests

import config
import consultas
import contador
import datos
import deudas
import movimientos
from banco import ErrorBanco, elegir_saldo
from formato import euros

detalle = logging.getLogger("detalle")


def hoy():
    return config.ahora().date()


def hecha_hoy():
    return datos.valor("SELECT COUNT(*) FROM saldos WHERE fecha = ?", hoy().isoformat()) > 0


def toca():
    """True si ya ha pasado la hora de la actualización de hoy y aún no se ha hecho."""
    horas, minutos = config.hora_saldo_diario()
    momento = config.ahora()
    return momento >= momento.replace(hour=horas, minute=minutos, second=0, microsecond=0) and not hecha_hoy()


def momento_ultima():
    """Fecha y hora de la última actualización (o None)."""
    from datetime import datetime
    valor = datos.ultimo_envio("actualizacion:")
    return datetime.fromisoformat(valor) if valor else None


def actualizar():
    """Descarga saldos y movimientos (bloqueante). Gasta 1 consulta del día.

    Lanza consultas.PermisoCaducado, contador.LimiteAlcanzado o errores de red (sin gastar consulta).
    Devuelve {"total", "cuentas", "movimientos_nuevos"}.
    """
    cuentas = consultas.conexion().get("cuentas")
    if not cuentas or not config.valor("EB_SESSION_ID"):
        raise consultas.PermisoCaducado("No hay ninguna cuenta conectada.")
    contador.usar()
    eb = consultas.cliente()
    fecha = hoy()
    saldos = {}
    try:
        for cuenta in cuentas:
            lista = eb.saldos(cuenta["uid"])
            detalle.info("Saldos de %s: %s", consultas.nombre_cuenta(cuenta), "; ".join(
                f"{b.get('balance_type')}={b.get('balance_amount', {}).get('amount')}" for b in lista) or "ninguno")
            elegido = elegir_saldo(lista)
            saldos[cuenta["uid"]] = (float(elegido[0]), elegido[1]) if elegido else (0.0, "EUR")
    except (requests.ConnectionError, requests.Timeout):
        contador.devolver()
        raise
    except ErrorBanco as e:
        if e.permiso_caducado:
            contador.devolver()
            raise consultas.PermisoCaducado(str(e)) from e
        raise
    except Exception:
        contador.devolver()
        raise
    datos.varios("INSERT OR REPLACE INTO saldos (fecha, uid, importe, moneda) VALUES (?, ?, ?, ?)",
                 [(fecha.isoformat(), uid, importe, moneda) for uid, (importe, moneda) in saldos.items()])
    datos.marcar_enviado(f"actualizacion:{fecha.isoformat()}")

    # Movimientos: si fallan, se conservan los saldos y se reintentará mañana.
    importados = []
    for cuenta in cuentas:
        try:
            desde = movimientos.desde_cuando(cuenta["uid"], fecha)
            for t in eb.transacciones(cuenta["uid"], desde):
                m = movimientos.desde_banco(cuenta["uid"], t)
                if m:
                    importados.append(m)
        except (ErrorBanco, requests.RequestException, KeyError, ValueError) as e:
            detalle.warning("No se han podido descargar los movimientos de %s: %s", consultas.nombre_cuenta(cuenta), e)
    nuevos = movimientos.guardar(importados)
    apuntados = pagos_detectados(nuevos)
    if config.aviso_activo("AVISO_GASTO_GRANDE") and nuevos:
        for m in movimientos.gastos_grandes(nuevos, excluir=apuntados):
            nombre = m["contraparte"] or m["descripcion"] or "un cargo"
            datos.encolar_aviso(f"💸 <b>Gasto grande</b>: {euros(-m['importe'])} en {nombre} "
                                f"({m['fecha'][8:10]}/{m['fecha'][5:7]}).")
    datos.copia_de_seguridad()
    total = round(sum(importe for importe, _ in saldos.values()), 2)
    logging.info("Datos del banco actualizados · %s cuentas · %s movimientos nuevos", len(saldos), len(nuevos))
    return {"total": total, "cuentas": len(saldos), "movimientos_nuevos": len(nuevos)}


def pagos_detectados(nuevos):
    """Si aparece un cargo igual a una cuota o pago pendiente (±5 días), se marca como pagado y se avisa.

    Devuelve los ids de los movimientos que se han reconocido como pagos.
    """
    cargos = [m for m in nuevos if m["importe"] < 0]
    usados = set()
    if not cargos:
        return usados
    for item in deudas.pendientes():
        if item["deuda"]["tipo"] not in ("plazos", "fijo"):
            continue
        for m in cargos:
            if m["id"] in usados:
                continue
            cerca = abs((date.fromisoformat(m["fecha"]) - item["vence"]).days) <= 5
            if cerca and abs(-m["importe"] - item["importe"]) <= 0.5:
                _, accion = deudas.pagar(item["deuda"]["id"], item["periodo"])
                usados.add(m["id"])
                datos.encolar_aviso(
                    f"✅ He visto el pago de <b>{item['deuda']['nombre']}</b> ({euros(item['importe'])}, "
                    f"{m['fecha'][8:10]}/{m['fecha'][5:7]}) y lo he marcado como pagado.",
                    [[["↩️ No era ese pago", f"desl:{accion}"]]])
                break
    return usados
