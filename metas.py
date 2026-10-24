"""Metas de ahorro («Viaje a Japón: 2.000 € para agosto»).

Dos formas de seguir el progreso:
- Vinculada a una cuenta (por ejemplo un Espacio de N26): lo ahorrado es el saldo de esa cuenta,
  que se actualiza solo con la actualización diaria.
- Manual: lo ahorrado es lo que había al crearla más las aportaciones que registres.
"""
import math
from datetime import date, datetime

import ciclo
import config
import datos

ACTIVA, COMPLETADA, BORRADA = 1, 0, -1


def hoy():
    return config.ahora().date()


def obtener(meta_id):
    return datos.uno("SELECT * FROM metas WHERE id = ?", meta_id)


def activas():
    return datos.todos("SELECT * FROM metas WHERE activa = 1 ORDER BY fecha_limite, id")


def completadas():
    return datos.todos("SELECT * FROM metas WHERE activa = 0 ORDER BY completada DESC")


def saldo_cuenta(uid, hasta=None):
    """Último saldo guardado de una cuenta (en o antes de `hasta`)."""
    if hasta:
        return datos.valor("SELECT importe FROM saldos WHERE uid = ? AND fecha <= ? ORDER BY fecha DESC LIMIT 1",
                           uid, hasta.isoformat())
    return datos.valor("SELECT importe FROM saldos WHERE uid = ? ORDER BY fecha DESC LIMIT 1", uid)


def ahorrado(meta):
    if meta["uid"]:
        return round(saldo_cuenta(meta["uid"]) or 0.0, 2)
    aportado = datos.valor("SELECT COALESCE(SUM(importe), 0) FROM aportaciones WHERE meta_id = ?", meta["id"])
    return round(meta["ahorrado"] + aportado, 2)


def progreso(meta, d=None):
    d = d or hoy()
    limite = date.fromisoformat(meta["fecha_limite"])
    creada = datetime.fromisoformat(meta["creada"]).date()
    llevas = ahorrado(meta)
    objetivo = meta["objetivo"]
    falta = max(0.0, round(objetivo - llevas, 2))
    meses = max(1, math.ceil((limite - d).days / 30.44)) if limite > d else 1
    mensual = round(falta / meses, 2)
    # Progreso esperado si se ahorrara a ritmo constante desde que se creó la meta.
    duracion = max(1, (limite - creada).days)
    transcurrido = min(1.0, max(0.0, (d - creada).days / duracion))
    inicial = min(meta["ahorrado"], objetivo)
    esperado = inicial + (objetivo - inicial) * transcurrido
    if llevas >= objetivo:
        estado = "✅ ¡Conseguida!"
    elif limite < d:
        estado = "🔴 Ha pasado la fecha"
    elif llevas >= esperado - 0.01:
        estado = "🟢 Vas bien"
    elif llevas >= esperado * 0.85:
        estado = "🟡 Vas justo"
    else:
        estado = "🔴 Vas tarde"
    return {"ahorrado": llevas, "objetivo": objetivo, "fraccion": llevas / objetivo if objetivo else 1.0,
            "falta": falta, "meses": meses, "mensual": mensual, "estado": estado, "limite": limite}


def aportado_en_ciclo(meta, d=None):
    d = d or hoy()
    inicio = ciclo.inicio(d)
    if meta["uid"]:
        antes = saldo_cuenta(meta["uid"], inicio)
        if antes is None:
            antes = datos.valor("SELECT importe FROM saldos WHERE uid = ? ORDER BY fecha LIMIT 1", meta["uid"]) or 0.0
        return round((saldo_cuenta(meta["uid"]) or 0.0) - antes, 2)
    return round(datos.valor("SELECT COALESCE(SUM(importe), 0) FROM aportaciones WHERE meta_id = ? AND fecha >= ?",
                             meta["id"], inicio.isoformat()), 2)


def pendiente_ciclo(meta, d=None):
    """Lo que faltaría apartar en este ciclo para ir al ritmo de la meta."""
    p = progreso(meta, d)
    if p["falta"] <= 0:
        return 0.0
    return round(max(0.0, p["mensual"] - max(0.0, aportado_en_ciclo(meta, d))), 2)


def crear(nombre, objetivo, fecha_limite, uid=None, ya_ahorrado=0.0):
    if uid:
        ya_ahorrado = saldo_cuenta(uid) or 0.0  # punto de partida para calcular si vas bien
    meta_id = datos.ejecutar("INSERT INTO metas (nombre, objetivo, fecha_limite, ahorrado, uid, creada) "
                             "VALUES (?, ?, ?, ?, ?, ?)", nombre, round(objetivo, 2), fecha_limite.isoformat(),
                             round(ya_ahorrado, 2), uid, config.ahora().isoformat())
    accion = datos.registrar_accion("metas", meta_id, "DELETE FROM metas WHERE id = ?1", f"Meta «{nombre}» creada")
    return meta_id, accion


def aportar(meta_id, importe):
    """Suma (o resta, si es negativo) dinero a una meta manual. Devuelve (id de acción, ¿completada ahora?)."""
    meta = obtener(meta_id)
    aportacion = datos.ejecutar("INSERT INTO aportaciones (meta_id, fecha, importe) VALUES (?, ?, ?)",
                                meta_id, hoy().isoformat(), round(importe, 2))
    accion = datos.registrar_accion(
        "aportaciones", aportacion,
        "UPDATE metas SET activa = 1, completada = NULL WHERE id = (SELECT meta_id FROM aportaciones WHERE id = ?1); "
        "DELETE FROM aportaciones WHERE id = ?1", f"Aportación a «{meta['nombre']}»")
    return accion, comprobar_completada(meta_id)


def comprobar_completada(meta_id):
    meta = obtener(meta_id)
    if meta["activa"] == ACTIVA and ahorrado(meta) >= meta["objetivo"]:
        datos.ejecutar("UPDATE metas SET activa = 0, completada = ? WHERE id = ?", hoy().isoformat(), meta_id)
        return True
    return False


def borrar(meta_id):
    meta = obtener(meta_id)
    datos.ejecutar("UPDATE metas SET activa = -1 WHERE id = ?", meta_id)
    return datos.registrar_accion("metas", meta_id, "UPDATE metas SET activa = 1 WHERE id = ?1",
                                  f"Meta «{meta['nombre']}» borrada")
