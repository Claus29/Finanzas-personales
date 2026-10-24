"""🛟 Colchón de emergencia: dinero apartado para imprevistos (por defecto, 3 meses de gastos).

Viene DESACTIVADO (COLCHON_ACTIVO=0). Al activarlo desde ⚙️ Ajustes se crea una meta especial
(especial = «colchon») que funciona como las demás metas (cuenta vinculada o manual, aportación
necesaria o fija, recordatorios hasta confirmar), pero:
- su objetivo se recalcula solo: COLCHON_MESES × tu gasto mensual medio (últimos 90 días);
- nunca se da por «conseguida»: si gastas de él, vuelve a pedir aportaciones;
- cuenta en el índice de salud financiera (si está desactivado, ese apartado no se evalúa).
Aunque esté desactivado, el análisis muestra cuántos meses de gastos cubre tu dinero libre.
"""
from datetime import date, timedelta

import config
import datos
import deudas
import metas
import movimientos
from formato import sumar_meses

NOMBRE = "Colchón de emergencia"
MESES_POSIBLES = (3, 6)


def activo():
    return config.valor("COLCHON_ACTIVO") == "1" and meta() is not None


def meta():
    return datos.uno("SELECT * FROM metas WHERE especial = 'colchon' AND activa = 1")


def meses_objetivo():
    return config.entero("COLCHON_MESES", 1, 12)


def gasto_mensual_medio():
    """Gasto medio al mes (sin traspasos entre tus cuentas) de los últimos 90 días."""
    hoy = config.ahora().date()
    if not movimientos.hay_movimientos():
        return 0.0
    primero = datos.valor("SELECT MIN(fecha) FROM movimientos")
    desde = max(hoy - timedelta(days=90), date.fromisoformat(primero))
    dias = max(30, (hoy - desde).days + 1)
    gastos, _ = movimientos.gastos_e_ingresos(desde, hoy + timedelta(days=1))
    return round(gastos / dias * 30.44, 2)


def objetivo_calculado():
    gasto = gasto_mensual_medio()
    return max(100.0, round(gasto * meses_objetivo() / 10) * 10) if gasto else 100.0


def activar(meses=3, uid=None, ya_ahorrado=0.0, aporte_modo="necesaria", aporte_fijo=0.0, recordar="cobro1"):
    config.guardar("COLCHON_MESES", meses)
    existente = datos.uno("SELECT * FROM metas WHERE especial = 'colchon' ORDER BY id DESC LIMIT 1")
    if existente:  # se reactiva el de antes (con lo que ya tenía) y se guardan las nuevas preferencias
        meta_id = existente["id"]
        datos.ejecutar("UPDATE metas SET activa = 1, aporte_modo = ?, aporte_fijo = ?, recordar = ? WHERE id = ?",
                       aporte_modo, round(aporte_fijo or 0, 2), recordar, meta_id)
        if uid and uid != existente["uid"]:
            metas.configurar(meta_id, "uid", uid)
    else:
        meta_id, _ = metas.crear(NOMBRE, objetivo_calculado(), sumar_meses(config.ahora().date(), 12, 28), uid=uid,
                                 ya_ahorrado=ya_ahorrado, aporte_modo=aporte_modo, aporte_fijo=aporte_fijo,
                                 recordar=recordar, especial="colchon")
    config.guardar("COLCHON_ACTIVO", "1")
    actualizar_objetivo()
    return meta_id


def desactivar():
    """Se desactiva sin borrar nada (los datos se conservan por si se vuelve a activar)."""
    existente = meta()
    if existente:
        datos.ejecutar("UPDATE metas SET activa = -1 WHERE id = ?", existente["id"])
    config.guardar("COLCHON_ACTIVO", "0")


def actualizar_objetivo():
    """Recalcula el objetivo con tu gasto real. Se llama al arrancar y en cada cobro."""
    existente = meta()
    if existente and config.valor("COLCHON_ACTIVO") == "1":
        datos.ejecutar("UPDATE metas SET objetivo = ? WHERE id = ?", objetivo_calculado(), existente["id"])


def dinero_en_metas():
    """Saldo de las cuentas vinculadas a metas (ese dinero no es libre)."""
    total = 0.0
    for m in metas.activas():
        if m["uid"]:
            total += metas.saldo_cuenta(m["uid"]) or 0.0
    return round(total, 2)


def dinero_libre(saldo_total):
    """Saldo − dinero de las cuentas de las metas − lo que te toca pagar este ciclo."""
    pendiente = sum(i["importe"] for i in deudas.pendientes())
    return round(saldo_total - dinero_en_metas() - pendiente, 2)


def meses_cubiertos(saldo_total):
    """Cuántos meses de gastos cubre el colchón (si está activo) o tu dinero libre (si no)."""
    gasto = gasto_mensual_medio()
    if not gasto:
        return None
    base = metas.ahorrado(meta()) if activo() else dinero_libre(saldo_total)
    return round(max(0.0, base) / gasto, 1)
