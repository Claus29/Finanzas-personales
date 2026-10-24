"""Actualización diaria con el banco: saldos y movimientos de todas las cuentas, en silencio.

Es la ÚNICA vez que se pregunta al banco: a la hora configurada (00:00 por defecto) o, si el
ordenador estaba apagado, en cuanto vuelve. Además se puede forzar desde Ajustes («Actualizar
ahora»). Nunca envía notificaciones: lo que descubre de madrugada se avisa a partir de las 09:00.
"""
import html
import logging
from datetime import date

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
    cambios_en_metas(fecha)

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
    """Busca en los movimientos nuevos los pagos apuntados (±5 días, mismo importe) y PREGUNTA.

    Nunca se marca nada como pagado sin tu confirmación: se envía (en la franja de recordatorios de
    deudas) «¿Es el pago de X?» con [Sí, márcalo] [No]. Devuelve los ids de esos movimientos.
    """
    usados = set()
    cargos = [m for m in nuevos if m["importe"] < 0]
    abonos = [m for m in nuevos if m["importe"] > 0]
    candidatos = [(i, cargos) for i in deudas.pendientes(sentido="debo")]
    candidatos += [(i, abonos) for i in deudas.por_cobrar()]
    (horas, minutos), _ = config.franja_deudas()
    ahora = config.ahora()
    desde = max(ahora, ahora.replace(hour=horas, minute=minutos, second=0, microsecond=0))
    for item, lista in candidatos:
        for m in lista:
            if m["id"] in usados:
                continue
            cerca = abs((date.fromisoformat(m["fecha"]) - item["vence"]).days) <= 5
            if cerca and abs(abs(m["importe"]) - item["importe"]) <= 0.5:
                usados.add(m["id"])
                deuda = item["deuda"]
                quien = m["contraparte"] or m["descripcion"] or "—"
                cuando = f"{m['fecha'][8:10]}/{m['fecha'][5:7]}"
                if deudas.me_deben(deuda):
                    texto = (f"💡 He visto un ingreso de {euros(abs(m['importe']))} de {quien} ({cuando}).\n"
                             f"¿Es lo que te debía <b>{deuda['nombre']}</b>?")
                    si = "✅ Sí, me ha pagado"
                else:
                    texto = (f"💡 He visto un cargo de {euros(abs(m['importe']))} a {quien} ({cuando}).\n"
                             f"¿Es el pago de <b>{deuda['nombre']}</b>?")
                    si = "✅ Sí, márcalo pagado"
                datos.encolar_aviso(texto, [[[si, f"dp:{deuda['id']}:{item['periodo']}"], ["❌ No", "borrar"]]], desde=desde)
                break
    return usados


def cambios_en_metas(fecha):
    """Compara el saldo de las cuentas vinculadas a metas con el anterior y PREGUNTA (nunca da por hecho).

    - Si sube y hay aportación pendiente: «¿Es tu aportación a X?» [Sí] [No].
    - Si baja: aviso de cuánto ha bajado el progreso.
    - Si llega al objetivo: «¿Doy la meta por conseguida?» [Sí] [Aún no].
    Los avisos salen en la franja de recordatorios (nunca de madrugada).
    """
    import metas
    (horas, minutos), _ = config.franja_deudas()
    ahora = config.ahora()
    desde = max(ahora, ahora.replace(hour=horas, minute=minutos, second=0, microsecond=0))
    nombres = {c["uid"]: consultas.nombre_cuenta(c) for c in consultas.cuentas()}
    for meta in metas.activas():
        if not meta["uid"]:
            continue
        actual = datos.valor("SELECT importe FROM saldos WHERE uid = ? AND fecha = ?", meta["uid"], fecha.isoformat())
        anterior = datos.valor("SELECT importe FROM saldos WHERE uid = ? AND fecha < ? ORDER BY fecha DESC LIMIT 1",
                               meta["uid"], fecha.isoformat())
        if actual is None or anterior is None:
            continue
        cuenta = nombres.get(meta["uid"], "la cuenta")
        diferencia = round(actual - anterior, 2)
        if diferencia >= 1 and metas.pendiente_ciclo(meta) > 0:
            datos.encolar_aviso(f"💡 He visto que «{cuenta}» ha subido {euros(diferencia)}.\n"
                                f"¿Es tu aportación a <b>{html.escape(meta['nombre'])}</b> de este mes?",
                                [[["✅ Sí, es la aportación", f"mt:ok:{meta['id']}:{diferencia}"], ["❌ No", "borrar"]]],
                                desde=desde)
        elif diferencia <= -1:
            p = metas.progreso(meta)
            datos.encolar_aviso(f"⚠️ «{cuenta}» ha bajado {euros(-diferencia)}: <b>{html.escape(meta['nombre'])}</b> va ahora "
                                f"al {p['fraccion']:.0%} ({euros(p['ahorrado'])} de {euros(p['objetivo'])}).", desde=desde)
        if actual >= meta["objetivo"] and not meta["especial"] and not datos.enviado(f"meta_lista:{meta['id']}"):
            datos.marcar_enviado(f"meta_lista:{meta['id']}")
            datos.encolar_aviso(f"🎉 «{cuenta}» ya tiene {euros(actual)}: ¡has llegado al objetivo de "
                                f"<b>{html.escape(meta['nombre'])}</b> ({euros(meta['objetivo'])})!\n¿La doy por conseguida?",
                                [[["🎉 Sí, conseguida", f"mt:fin:{meta['id']}"], ["Aún no", "borrar"]]], desde=desde)

