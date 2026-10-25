"""Metas de ahorro («Viaje a Japón: 2.000 € para agosto») y su aportación en cada ciclo de cobro.

Seguimiento:
- Vinculada a una cuenta (p. ej. un Espacio de N26): lo ahorrado es el saldo de esa cuenta (se
  actualiza con la actualización diaria). El dinero de esa cuenta no cuenta como dinero libre.
- Manual: lo ahorrado es lo que había al crearla más las aportaciones que registres.

Aportación de cada ciclo:
- aporte_modo «necesaria»: lo justo para llegar a tiempo, calculado al empezar el ciclo.
- aporte_modo «fija»: la cantidad que elijas (aporte_fijo).
El recordatorio siempre pide esa cantidad (en la franja de recordatorios) y se repite hasta que
confirmes: «ya lo moví», «otra cantidad» o «este mes no». Nada se da por hecho.
Cuándo empieza a recordar (recordar): «cobro» (el día del cobro), «cobro1» (el día después) o
«dia:N» (el día N del mes).

Tramos (v10): una meta puede aportar una cuota reducida (tramo_aporte; 0 = en pausa) mientras no se
cumpla tramo_hasta: «meta:ID» (hasta conseguir otra meta prioritaria) o «fecha:AAAA-MM-DD» (hasta ese
cobro). Después, según tramo_despues: «recuperar» (la cuota sube lo necesario para llegar a su fecha)
o «aplazar» (vuelve a su cuota normal; su fecha ya se movió al aplicarlo). prioridad: 1, 2… (0 = ninguna).
"""
import math
from datetime import date, datetime, timedelta

import ciclo
import config
import datos
from formato import dia_del_mes, sumar_meses

ACTIVA, COMPLETADA, BORRADA = 1, 0, -1
RECORDAR = {"cobro": "el día del cobro", "cobro1": "el día después del cobro"}
APORTE_MODOS = {"necesaria": "🧮 la necesaria para llegar a tiempo", "fija": "✍️ una cantidad fija"}


def hoy():
    return config.ahora().date()


def obtener(meta_id):
    return datos.uno("SELECT * FROM metas WHERE id = ?", meta_id)


def activas():
    """Metas activas (el colchón de emergencia, si está activado, primero)."""
    return datos.todos("SELECT * FROM metas WHERE activa = 1 ORDER BY especial = '' , fecha_limite, id")


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


def ahorrado_en(meta, fecha):
    """Lo ahorrado en una fecha pasada (saldo de la cuenta ese día, o aportaciones hasta ese día)."""
    if meta["uid"]:
        valor = saldo_cuenta(meta["uid"], fecha)
        if valor is None:
            valor = datos.valor("SELECT importe FROM saldos WHERE uid = ? ORDER BY fecha LIMIT 1", meta["uid"])
        return round(valor or 0.0, 2)
    aportado = datos.valor("SELECT COALESCE(SUM(importe), 0) FROM aportaciones WHERE meta_id = ? AND fecha <= ?",
                           meta["id"], fecha.isoformat())
    return round(meta["ahorrado"] + aportado, 2)


def meses_hasta(limite, d):
    return max(1, math.ceil((limite - d).days / 30.44)) if limite > d else 1


def progreso(meta, d=None):
    d = d or hoy()
    limite = date.fromisoformat(meta["fecha_limite"])
    creada = datetime.fromisoformat(meta["creada"]).date()
    llevas = ahorrado(meta)
    objetivo = meta["objetivo"]
    falta = max(0.0, round(objetivo - llevas, 2))
    meses = meses_hasta(limite, d)
    mensual = round(falta / meses, 2)
    # Progreso esperado si se ahorrara a ritmo constante desde que se creó la meta.
    duracion = max(1, (limite - creada).days)
    transcurrido = min(1.0, max(0.0, (d - creada).days / duracion))
    inicial = min(meta["ahorrado"], objetivo)
    esperado = inicial + (objetivo - inicial) * transcurrido
    espera = en_espera(meta, d) if meta["activa"] == ACTIVA else None
    if llevas >= objetivo:
        estado = "✅ ¡Conseguida!"
    elif espera:
        estado = f"⏸️ En espera {espera}"
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


# ---------- Aportación de cada ciclo ----------

def clave_ciclo(d=None):
    return ciclo.inicio(d or hoy()).isoformat()


def _campo(meta, cfg, campo):
    return cfg[campo] if cfg and campo in cfg else meta[campo]


def tramo_activo(meta, fecha_cobro, pendientes, cfg=None):
    """¿Aporta la cuota reducida en el cobro de fecha_cobro? pendientes: ids de metas aún sin conseguir."""
    if _campo(meta, cfg, "tramo_aporte") < 0:
        return False
    hasta = _campo(meta, cfg, "tramo_hasta") or ""
    if hasta.startswith("meta:"):
        return int(hasta[5:]) in pendientes
    if hasta.startswith("fecha:"):
        return fecha_cobro < date.fromisoformat(hasta[6:])
    return False


def cuota(meta, ahorrado_ahora, fecha_cobro, pendientes, cfg=None):
    """Aportación en el cobro de fecha_cobro con lo ahorrado hasta entonces (con tramos y cambios simulados)."""
    falta = round(meta["objetivo"] - ahorrado_ahora, 2)
    if falta <= 0.004:
        return 0.0
    if tramo_activo(meta, fecha_cobro, pendientes, cfg):
        return round(min(max(0.0, _campo(meta, cfg, "tramo_aporte")), falta), 2)
    limite = date.fromisoformat(_campo(meta, cfg, "fecha_limite"))
    necesaria = falta / meses_hasta(limite, fecha_cobro)
    fijo = _campo(meta, cfg, "aporte_fijo")
    normal = min(fijo, falta) if _campo(meta, cfg, "aporte_modo") == "fija" and fijo > 0 else necesaria
    if _campo(meta, cfg, "tramo_aporte") >= 0 and _campo(meta, cfg, "tramo_despues") == "recuperar":
        normal = max(normal, necesaria)  # terminado el tramo, recupera para llegar a su fecha
    return round(min(normal, falta), 2)


def pendientes_ahora():
    """Ids de las metas activas que aún no han llegado a su objetivo."""
    return {m["id"] for m in activas() if ahorrado(m) < m["objetivo"] - 0.004}


def aporte_previsto(meta, d=None):
    """Lo que toca aportar en el ciclo actual: su parte del reparto automático si el ciclo lo tiene (v11);
    si no, la cuota reducida si está en tramo, la fija o la necesaria."""
    d = d or hoy()
    inicio = ciclo.inicio(d)
    import reparto
    parte = reparto.de_meta(meta["id"], inicio.isoformat())
    falta = max(0.0, meta["objetivo"] - ahorrado_en(meta, inicio - timedelta(days=1)))
    if parte is not None:
        return round(min(parte, falta), 2)
    return cuota(meta, ahorrado_en(meta, inicio - timedelta(days=1)), inicio, pendientes_ahora())


def en_espera(meta, d=None):
    """Texto corto si ahora aporta la cuota reducida de un tramo («hasta conseguir X»), o None."""
    d = d or hoy()
    import reparto
    if reparto.activo() or not tramo_activo(meta, ciclo.inicio(d), pendientes_ahora()):
        return None  # con el reparto automático no hay tramos: cada meta recibe su parte de lo que sobra
    return describir_hasta(meta["tramo_hasta"])


def describir_hasta(hasta):
    if hasta.startswith("meta:"):
        otra = obtener(int(hasta[5:]))
        return f"hasta conseguir «{otra['nombre']}»" if otra else "hasta conseguir tu meta prioritaria"
    if hasta.startswith("fecha:"):
        from formato import MESES
        fecha = date.fromisoformat(hasta[6:])
        return f"hasta el cobro de {MESES[fecha.month - 1]} {fecha.year}"
    return ""


def quitar_tramo(meta_id):
    datos.ejecutar("UPDATE metas SET tramo_aporte = -1, tramo_hasta = '', tramo_despues = '', prioridad = 0 "
                   "WHERE id = ?", meta_id)


def estado_ciclo(meta, d=None):
    """Fila de aportes_ciclo del ciclo actual (hecho / otra / saltado) o None si aún no se ha confirmado."""
    return datos.uno("SELECT * FROM aportes_ciclo WHERE meta_id = ? AND ciclo = ?", meta["id"], clave_ciclo(d))


def pendiente_ciclo(meta, d=None):
    """Lo que falta por apartar en este ciclo (0 si ya se confirmó, se saltó o la meta está cumplida)."""
    if estado_ciclo(meta, d) or progreso(meta, d)["falta"] <= 0:
        return 0.0
    return aporte_previsto(meta, d)


def aportado_en_ciclo(meta, d=None):
    fila = estado_ciclo(meta, d)
    return fila["importe"] if fila else 0.0


def inicio_recordatorio(meta, d=None):
    """Día del ciclo actual a partir del cual se recuerda la aportación (None si aún no has cobrado)."""
    d = d or hoy()
    if not ciclo.ultimo_salario(d):
        return None
    inicio = ciclo.inicio(d)
    recordar = meta["recordar"] or "cobro1"
    if recordar == "cobro":
        return inicio
    if recordar.startswith("dia:"):
        dia = int(recordar[4:])
        fecha = dia_del_mes(inicio.year, inicio.month, dia)
        return fecha if fecha >= inicio else sumar_meses(fecha, 1, dia)
    return inicio + timedelta(days=1)


def describir_recordar(meta):
    recordar = meta["recordar"] or "cobro1"
    if recordar.startswith("dia:"):
        return f"el día {recordar[4:]} de cada mes"
    return RECORDAR.get(recordar, RECORDAR["cobro1"])


def confirmar(meta_id, importe=None, estado="hecho"):
    """Aportación del ciclo confirmada (o «este mes no» con estado «saltado»). Devuelve (acción, ¿conseguida?)."""
    meta = obtener(meta_id)
    ciclo_actual = clave_ciclo()
    if estado == "saltado":
        importe = 0.0
    elif importe is None:
        importe = aporte_previsto(meta)
    aportacion_id = None
    if not meta["uid"] and importe:
        aportacion_id = datos.ejecutar("INSERT INTO aportaciones (meta_id, fecha, importe) VALUES (?, ?, ?)",
                                       meta_id, hoy().isoformat(), round(importe, 2))
    datos.ejecutar("INSERT OR REPLACE INTO aportes_ciclo (meta_id, ciclo, estado, importe, fecha, aportacion_id) "
                   "VALUES (?, ?, ?, ?, ?, ?)", meta_id, ciclo_actual, estado, round(importe, 2), hoy().isoformat(),
                   aportacion_id)
    fila = datos.valor("SELECT rowid FROM aportes_ciclo WHERE meta_id = ? AND ciclo = ?", meta_id, ciclo_actual)
    accion = datos.registrar_accion(
        "aportes_ciclo", fila,
        "DELETE FROM aportaciones WHERE id = (SELECT aportacion_id FROM aportes_ciclo WHERE rowid = ?1); "
        "UPDATE metas SET activa = 1, completada = NULL WHERE id = (SELECT meta_id FROM aportes_ciclo WHERE rowid = ?1); "
        "DELETE FROM aportes_ciclo WHERE rowid = ?1", f"Aportación a «{meta['nombre']}»")
    conseguida = comprobar_completada(meta_id) if estado != "saltado" else False
    return accion, conseguida


def ritmo_real(meta, d=None):
    """Lo que de verdad ahorras al mes en esta meta (media de los últimos ~3 meses)."""
    d = d or hoy()
    creada = datetime.fromisoformat(meta["creada"]).date()
    desde = max(creada, d - timedelta(days=91))
    meses = max(1.0, (d - desde).days / 30.44)
    return round((ahorrado(meta) - ahorrado_en(meta, desde)) / meses, 2)


def fecha_estimada(meta, d=None):
    """Cuándo llegarías al objetivo a tu ritmo real (None si no avanzas)."""
    d = d or hoy()
    p = progreso(meta, d)
    if p["falta"] <= 0:
        return d
    ritmo = ritmo_real(meta, d)
    if ritmo <= 0:
        return None
    return sumar_meses(d, math.ceil(p["falta"] / ritmo), 28)


# ---------- Cambios ----------

def crear(nombre, objetivo, fecha_limite, uid=None, ya_ahorrado=0.0, aporte_modo="necesaria", aporte_fijo=0.0,
          recordar="cobro1", especial=""):
    if uid:
        ya_ahorrado = saldo_cuenta(uid) or 0.0  # punto de partida para calcular si vas bien
    meta_id = datos.ejecutar("INSERT INTO metas (nombre, objetivo, fecha_limite, ahorrado, uid, creada, aporte_modo, "
                             "aporte_fijo, recordar, especial) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             nombre, round(objetivo, 2), fecha_limite.isoformat(), round(ya_ahorrado, 2), uid,
                             config.ahora().isoformat(), aporte_modo, round(aporte_fijo or 0, 2), recordar, especial)
    accion = datos.registrar_accion("metas", meta_id, "DELETE FROM metas WHERE id = ?1", f"Meta «{nombre}» creada")
    return meta_id, accion


def configurar(meta_id, campo, valor):
    if campo not in ("aporte_modo", "aporte_fijo", "recordar", "uid", "objetivo", "fecha_limite", "nombre",
                     "prioridad", "tramo_aporte", "tramo_hasta", "tramo_despues"):
        raise ValueError(campo)
    datos.ejecutar(f"UPDATE metas SET {campo} = ? WHERE id = ?", valor, meta_id)
    if campo == "uid" and valor:
        # Al vincular una cuenta, el punto de partida pasa a ser su saldo actual.
        datos.ejecutar("UPDATE metas SET ahorrado = ? WHERE id = ?", saldo_cuenta(valor) or 0.0, meta_id)


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
    if meta["activa"] == ACTIVA and not meta["especial"] and ahorrado(meta) >= meta["objetivo"]:
        terminar(meta_id)
        return True
    return False


def terminar(meta_id):
    datos.ejecutar("UPDATE metas SET activa = 0, completada = ? WHERE id = ?", hoy().isoformat(), meta_id)


def borrar(meta_id):
    meta = obtener(meta_id)
    datos.ejecutar("UPDATE metas SET activa = -1 WHERE id = ?", meta_id)
    return datos.registrar_accion("metas", meta_id, "UPDATE metas SET activa = 1 WHERE id = ?1",
                                  f"Meta «{meta['nombre']}» borrada")
