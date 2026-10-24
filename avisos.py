"""Motor de avisos: decide qué recordatorios tocan ahora (el bot lo consulta cada minuto).

Cada aviso tiene una clave única para no repetirse. Ninguno de los automáticos se envía de
madrugada: lo que se descubre en la actualización de las 00:00 se encola y sale desde las 09:00.
Si el ordenador estaba apagado a la hora de un aviso, se envía si se enciende en las 3 horas
siguientes (los avisos importantes se repiten: el del cobro y los pagos atrasados).
"""
import json
from datetime import date, datetime, timedelta

import analisis
import ciclo
import config
import consultas
import datos
import deudas
import metas
import movimientos
from formato import DIAS_SEMANA, euros, euros_cortos, fecha_corta

MARGEN = timedelta(hours=3)
HORAS_COBRO_VENTANA = ["10:00", "18:00"]
HORAS_COBRO_INSISTIR = ["09:00", "12:00", "15:00", "18:00", "21:00"]
HORA_AVISOS = "10:00"


def _momento(d, hora):
    horas, minutos = (int(x) for x in hora.split(":"))
    return datetime(d.year, d.month, d.day, horas, minutos, tzinfo=config.zona())


def en_franja(hora, ahora=None):
    ahora = ahora or config.ahora()
    inicio = _momento(ahora.date(), hora)
    return inicio <= ahora < inicio + MARGEN


def pospuesto(clave, ahora):
    hasta = datos.pospuesto_hasta(clave)
    return hasta is not None and ahora < hasta


def calcular(ahora=None):
    """[(clave, texto HTML, botones)] que hay que enviar ahora. botones = [[(texto, datos)], ...]"""
    ahora = ahora or config.ahora()
    d = ahora.date()
    lista = []

    def anadir(clave, texto, botones=()):
        if not datos.enviado(clave):
            lista.append((clave, texto, [list(fila) for fila in botones]))

    for aviso in datos.avisos_listos():
        lista.append((f"cola:{aviso['id']}", aviso["texto"], json.loads(aviso["botones"])))

    _cobro(d, ahora, anadir)
    if config.aviso_activo("AVISO_DEUDAS"):
        _deudas(d, ahora, anadir)
    if config.aviso_activo("AVISO_METAS"):
        _metas(d, ahora, anadir)
    _permiso(d, ahora, anadir)
    if config.aviso_activo("AVISO_RESUMEN_SEMANAL") and d.weekday() == 6 and en_franja("20:00", ahora):
        anadir(f"semanal:{d}", analisis.texto_semana(d))
    if en_franja(HORA_AVISOS, ahora):
        _saldo(d, anadir)
        if config.aviso_activo("AVISO_SUSCRIPCIONES") and d.day == 1:
            anadir(f"suscripciones:{d:%Y-%m}", analisis.texto_suscripciones())
    _personalizados(d, ahora, anadir)
    return lista


def _cobro(d, ahora, anadir):
    if ciclo.cobrado_este_mes(d) or pospuesto("cobro", ahora):
        return
    candidato = movimientos.candidato_nomina(d) if movimientos.hay_movimientos() else None
    desde, hasta = config.dias_cobro()
    if d.day < desde and not candidato:
        return
    horas = HORAS_COBRO_VENTANA if d.day <= hasta else HORAS_COBRO_INSISTIR
    if candidato and d.day < desde:
        horas = ["09:00"] + horas
    actuales = [h for h in horas if en_franja(h, ahora)]
    if not actuales:
        return
    clave = f"cobro:{d}:{actuales[-1]}"
    if candidato:
        fila = datos.valor("SELECT rowid FROM movimientos WHERE id = ?", candidato["id"])
        fecha = date.fromisoformat(candidato["fecha"])
        quien = f" de {analisis.e(candidato['contraparte'])}" if candidato["contraparte"] else ""
        anadir(clave, f"💶 He visto un ingreso de <b>{euros(candidato['importe'])}</b>{quien} el {fecha:%d/%m}.\n"
                      "¿Es tu nómina?",
               [[("✅ Sí, es mi nómina", f"nom:si:{fila}")],
                [("❌ No", f"nom:no:{fila}"), ("✍️ Otro importe", "cobro:nuevo")]])
    else:
        insistir = "" if d.day <= hasta else "\n⚠️ Ya ha pasado el día habitual de cobro."
        anadir(clave, "💶 <b>¿Ya has cobrado este mes?</b>\nRegistra tu salario para que cuadren tus cuentas: "
                      f"el ciclo, el saldo neto y tus pagos dependen de ello.{insistir}",
               [[("💶 Registrar cobro", "cobro:nuevo")], [("⏰ Aún no he cobrado", "cobro:aun")]])


def _deudas(d, ahora, anadir):
    """Recordatorio el día de pago (a HORA_AVISO_PAGO, 00:00 por defecto) y cada día si se atrasa.

    Para lo que debes, además, un aviso unos días antes (a las 10:00). Si el ordenador estaba apagado
    a la hora del recordatorio, se envía en cuanto se encienda ese mismo día.
    """
    hora_pago = _momento(d, config.hora_aviso_pago())
    items = []
    if config.aviso_activo("AVISO_DEUDAS"):
        items += deudas.pendientes(d, "debo")
    if config.aviso_activo("AVISO_ME_DEBEN"):
        items += deudas.pendientes(d, "me_deben")
    for item in items:
        deuda, per, vence = item["deuda"], item["periodo"], item["vence"]
        base = f"deuda:{deuda['id']}:{per}"
        if pospuesto(base, ahora):
            continue
        if d >= vence and ahora >= hora_pago:
            anadir(f"pago:{deuda['id']}:{per}:{d}", texto_pago(item, d), botones_pago(deuda, per))
        elif (not deudas.me_deben(deuda) and d == vence - timedelta(days=deuda["avisar_dias"])
              and en_franja(HORA_AVISOS, ahora)):
            anadir(f"{base}:{d}:antes", f"🔔 Dentro de {deuda['avisar_dias']} días ({fecha_corta(vence)}): "
                                        f"<b>{analisis.e(deuda['nombre'])}</b>{_cuota(deuda, per)} · {euros(item['importe'])}",
                   botones_pago(deuda, per))


def _cuota(deuda, per):
    if deuda["tipo"] != "plazos":
        return ""
    return f" (cuota {deudas.periodos(deuda).index(per) + 1}/{deuda['cuotas_total']})"


def texto_pago(item, d):
    deuda, per, vence = item["deuda"], item["periodo"], item["vence"]
    nombre = f"<b>{analisis.e(deuda['nombre'])}</b>{_cuota(deuda, per)}"
    importe = f"<b>{euros(item['importe'])}</b>"
    atraso = f"\n⚠️ Era el {fecha_corta(vence)}: va con retraso." if d > vence else ""
    if deudas.me_deben(deuda):
        return f"🤝 Hoy {nombre} te tiene que pagar {importe}.{atraso}"
    if deuda["tipo"] == "suscripcion":
        return f"📺 Hoy se cobra {nombre}: {importe}.{atraso}"
    if deudas.aplazada(deuda, per):
        return f"📅 Hoy vence lo que aplazaste: {nombre} · {importe}.{atraso}"
    return f"💳 Hoy toca pagar {nombre} · {importe}.{atraso}"


def botones_pago(deuda, per):
    pagado = "✅ Me ha pagado" if deudas.me_deben(deuda) else "✅ Pagado"
    filas = [[(pagado, f"dp:{deuda['id']}:{per}"), ("⏰ Mañana", f"dm:{deuda['id']}:{per}")],
             [("📅 Aplazar", f"da:{deuda['id']}:{per}")]]
    if deuda["tipo"] in deudas.UNICOS:
        filas[1].append(("💸 Una parte", f"dparte:{deuda['id']}"))
    return filas


def _metas(d, ahora, anadir):
    inicio = ciclo.inicio(d)
    if not ciclo.ultimo_salario(d) or d != inicio + timedelta(days=1) or not en_franja(HORA_AVISOS, ahora):
        return
    for meta in metas.activas():
        falta = metas.pendiente_ciclo(meta, d)
        if falta <= 0:
            continue
        if meta["uid"]:
            cuenta = next((c for c in consultas.cuentas() if c["uid"] == meta["uid"]), None)
            destino = f" a «{analisis.e(consultas.nombre_cuenta(cuenta))}»" if cuenta else ""
            anadir(f"meta:{meta['id']}:{inicio}", f"🎯 <b>{analisis.e(meta['nombre'])}</b>: este ciclo toca apartar "
                                                  f"<b>{euros_cortos(falta)}</b>{destino}.")
        else:
            anadir(f"meta:{meta['id']}:{inicio}", f"🎯 <b>{analisis.e(meta['nombre'])}</b>: este ciclo toca apartar "
                                                  f"<b>{euros_cortos(falta)}</b>.",
                   [[(f"✅ Aparté {euros_cortos(falta)}", f"ma:{meta['id']}:{falta}"), ("✍️ Otro importe", f"mo:{meta['id']}")]])


def _permiso(d, ahora, anadir):
    if datos.enviado("permiso_caducado") and ahora.hour >= 9:
        anadir(f"permiso:{d}", "⚠️ <b>El permiso de N26 ha caducado o se ha desvinculado.</b>\n"
                               "Ve al ordenador: la ventana «Bot Finanzas» te guía para renovarlo. Mientras tanto "
                               "sigo funcionando con los últimos datos.")
        return
    caduca = consultas.conexion().get("valido_hasta")
    if not caduca or not en_franja(HORA_AVISOS, ahora):
        return
    dias = (datetime.fromisoformat(caduca.replace("Z", "+00:00")).date() - d).days
    if 0 <= dias <= 15 and dias % 3 == 0:
        anadir(f"caduca:{d}", f"⏳ El permiso de N26 caduca en {dias} días. Cuando caduque, la ventana del bot "
                              "te pedirá renovarlo (tarda un minuto).")


def _saldo(d, anadir):
    s = analisis.saldo_actual()
    if not s:
        return
    neto, _ = deudas.neto(s["total"], d)
    umbral = config.importe("UMBRAL_SALDO_BAJO")
    if config.aviso_activo("AVISO_SALDO_BAJO") and umbral and neto < umbral:
        anadir(f"bajo:{d}", f"⚠️ <b>Saldo neto bajo</b>: {euros(neto)} (tu aviso está en {euros_cortos(umbral)}).\n"
                            f"Quedan {ciclo.dias_hasta_cobro(d)} días para el cobro.")
        return
    if config.aviso_activo("AVISO_RITMO") and movimientos.hay_movimientos():
        c = analisis.datos_ciclo(d)
        restantes = ciclo.dias_hasta_cobro(d)
        ultimo = datos.ultimo_envio("ritmo:")
        reciente = ultimo and (d - datetime.fromisoformat(ultimo).date()).days < 3
        if c["transcurridos"] >= 5 and not reciente and neto - c["normal"] * restantes < 0:
            dias_llega = int(neto / c["normal"]) if c["normal"] > 0 else restantes
            anadir(f"ritmo:{d}", f"📉 <b>Cuidado con el ritmo</b>: gastas ~{euros_cortos(c['normal'])}/día y a este ritmo "
                                 f"el dinero te llega para ~{max(0, dias_llega)} días, pero faltan {restantes} para el cobro.\n"
                                 f"Para llegar: ~{euros_cortos(max(0, neto) / restantes)}/día.")


def _personalizados(d, ahora, anadir):
    for r in datos.todos("SELECT * FROM recordatorios WHERE activo = 1"):
        if not en_franja(r["hora"], ahora):
            continue
        toca = (r["frecuencia"] == "diaria"
                or (r["frecuencia"] == "una" and r["fecha"] == d.isoformat())
                or (r["frecuencia"] == "semanal" and r["dia_semana"] == d.weekday())
                or (r["frecuencia"] == "mensual" and _dia_mensual(r["dia_mes"], d)))
        if toca:
            anadir(f"rec:{r['id']}:{d}", f"⏰ <b>Recordatorio</b>\n{analisis.e(r['texto'])}")


def _dia_mensual(dia, d):
    from calendar import monthrange
    return d.day == min(dia, monthrange(d.year, d.month)[1])


def enviado(clave):
    """Marca un aviso como enviado (y desactiva los recordatorios de una sola vez)."""
    if clave.startswith("cola:"):
        datos.marcar_aviso_enviado(int(clave.split(":")[1]))
        return
    datos.marcar_enviado(clave)
    if clave.startswith("rec:"):
        datos.ejecutar("UPDATE recordatorios SET activo = 0 WHERE id = ? AND frecuencia = 'una'", int(clave.split(":")[1]))


def describir_recordatorio(r):
    hora = r["hora"]
    if r["frecuencia"] == "diaria":
        cuando = f"cada día a las {hora}"
    elif r["frecuencia"] == "semanal":
        cuando = f"cada {DIAS_SEMANA[r['dia_semana']]} a las {hora}"
    elif r["frecuencia"] == "mensual":
        cuando = f"el día {r['dia_mes']} de cada mes a las {hora}"
    else:
        cuando = f"el {date.fromisoformat(r['fecha']):%d/%m/%Y} a las {hora}"
    return cuando
