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
    _deudas(d, ahora, anadir)  # deudas, lo que te deben y metas, repartidos en la franja (cada uno con su interruptor)
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
    """Recordatorios de deudas del día, repartidos en la franja FRANJA_DEUDAS (08:00–14:00).

    Nunca se da nada por pagado: cada recordatorio pide confirmación y, si no se confirma (o se pulsa
    «Ignorar»), vuelve al día siguiente. Orden: decisiones de cuotas no pagadas, atrasados, los de hoy,
    los de «dentro de 2 días» y las preguntas de lo que te deben sin día fijo. Si el ordenador estaba
    apagado, los que falten se envían al encenderlo ese mismo día.
    """
    candidatos = []  # (prioridad, clave, texto, botones)
    sentidos = [s for s, clave in (("debo", "AVISO_DEUDAS"), ("me_deben", "AVISO_ME_DEBEN")) if config.aviso_activo(clave)]
    decididos = set()

    # 1) Cuotas a plazos cuyo mes (o ciclo de cobro) terminó sin pagar: ¿qué hacemos?
    for deuda in [x for x in deudas.activas() if x["sentido"] in sentidos and x["tipo"] == "plazos"]:
        for item in deudas.periodos_sin_pagar_cerrados(deuda, d):
            per = item["periodo"]
            if datos.enviado(f"espera:{deuda['id']}:{per}"):
                continue  # «aún puede pagarla»: sigue como atrasada normal
            decididos.add((deuda["id"], per))
            if deuda["si_no_paga"] in ("pasar", "juntas"):
                texto, accion = deudas.saltar(deuda["id"], per, deuda["si_no_paga"])
                quien = analisis.e(deuda["nombre"])
                datos.encolar_aviso(f"⚠️ <b>{quien}</b>: la cuota de {deudas.nombre_periodo(per)} "
                                    f"({euros(item['importe'])}) no se pagó.\nComo tienes configurado, {texto}. "
                                    "<i>No cuenta como pagada.</i>", [[["↩️ Deshacer", f"desl:{accion}"]]],
                                    desde=max(ahora, _momento(d, "%02d:%02d" % config.franja_deudas()[0])))
                continue
            candidatos.append((0, f"saltar:{deuda['id']}:{per}:{d}", texto_salto(deuda, item), botones_salto(deuda, per)))

    # 2) Pagos de hoy o atrasados, y avisos previos
    for item in [i for sentido in sentidos for i in deudas.pendientes(d, sentido)]:
        deuda, per, vence = item["deuda"], item["periodo"], item["vence"]
        if (deuda["id"], per) in decididos or pospuesto(f"deuda:{deuda['id']}:{per}", ahora):
            continue
        sin_dia = deudas.modo(deuda) == "sin" and deuda["tipo"] in deudas.MENSUALES
        if sin_dia and not item["atrasada"]:
            if d.day in config.dias_aviso_sin_dia() or d == vence:
                candidatos.append((4, f"sin:{deuda['id']}:{per}:{d}", texto_sin_dia(item), botones_pago(deuda, per)))
            continue
        if d >= vence:
            if _al_cobrar(deuda, per) and vence == d:
                continue  # el día del cobro va en el mensaje «¡Cobrado!»; desde mañana, un recordatorio por pago
            prioridad = 1 if d > vence else 2
            candidatos.append((prioridad, f"pago:{deuda['id']}:{per}:{d}", texto_pago(item, d), botones_pago(deuda, per)))
        elif (not deudas.me_deben(deuda) and not _al_cobrar(deuda, per)
              and d == vence - timedelta(days=deuda["avisar_dias"])):  # con el cobro: sin aviso previo
            candidatos.append((3, f"antes:{deuda['id']}:{per}:{d}",
                               f"🔔 Dentro de {deuda['avisar_dias']} días ({fecha_corta(vence)}): "
                               f"<b>{analisis.e(deuda['nombre'])}</b>{_cuota(deuda, item)} · {euros(item['importe'])}",
                               botones_pago(deuda, per)))

    # 3) Dinero que mover a tus metas en este ciclo (hasta que lo confirmes)
    if config.aviso_activo("AVISO_METAS"):
        candidatos += _candidatos_metas(d, ahora)

    # 4) Reparto en la franja: el i-ésimo aviso del día sale a desde + i·(duración/n)
    candidatos.sort(key=lambda c: (c[0], c[1]))
    (h1, m1), (h2, m2) = config.franja_deudas()
    inicio = _momento(d, f"{h1:02d}:{m1:02d}")
    duracion = _momento(d, f"{h2:02d}:{m2:02d}") - inicio
    for n, (_, clave, texto, botones) in enumerate(candidatos):
        if ahora >= inicio + duracion * n / len(candidatos):
            anadir(clave, texto, botones)


def _al_cobrar(deuda, per=None):
    """True si el pago va con un cobro (la deuda es «al cobrar» o esta cuota se pasó al cobro)."""
    return (deuda["tipo"] == "cobro" or (deuda["tipo"] in deudas.MENSUALES and deudas.modo(deuda) == "cobro")
            or bool(per and deudas.al_cobro_desde(deuda["id"], per)))


def _cuota(deuda, item):
    if deuda["tipo"] != "plazos":
        return ""
    numero, total = deudas.numero_cuota(deuda)
    juntas = f", incluye {item['juntas']} cuotas" if item.get("juntas", 1) > 1 else ""
    return f" (cuota {numero}/{total}{juntas})"


def texto_pago(item, d):
    deuda, per, vence = item["deuda"], item["periodo"], item["vence"]
    nombre = f"<b>{analisis.e(deuda['nombre'])}</b>{_cuota(deuda, item)}"
    importe = f"<b>{euros(item['importe'])}</b>"
    if deudas.me_deben(deuda):
        if d > vence:
            return f"🤝 {nombre} te tenía que pagar {importe} el {fecha_corta(vence)}.\n¿Te ha pagado ya?"
        return f"🤝 Hoy {nombre} te tiene que pagar {importe}.\n¿Te ha pagado?"
    if d > vence and _al_cobrar(deuda, per):
        return f"💶 Desde que cobraste el {fecha_corta(vence)} tienes pendiente: {nombre} · {importe}.\n¿Ya lo pagaste?"
    if d > vence:
        return f"⚠️ Pendiente desde el {fecha_corta(vence)}: {nombre} · {importe}.\n¿Ya lo pagaste?"
    if deuda["tipo"] == "suscripcion":
        return f"📺 Hoy se cobra {nombre}: {importe}.\n¿Confirmas que está pagada?"
    if deudas.aplazada(deuda, per):
        return f"📅 Hoy vence lo que aplazaste: {nombre} · {importe}.\n¿Ya lo pagaste?"
    return f"💳 Hoy toca pagar {nombre} · {importe}.\n¿Ya lo pagaste?"


def texto_sin_dia(item):
    deuda = item["deuda"]
    return (f"🤝 ¿Te ha pagado <b>{analisis.e(deuda['nombre'])}</b> la cuota de {deudas.nombre_periodo(item['periodo'])}"
            f"{_cuota(deuda, item)}? · {euros(item['importe'])}")


def texto_salto(deuda, item):
    quien = analisis.e(deuda["nombre"])
    mes = deudas.nombre_periodo(item["periodo"])
    if deudas.me_deben(deuda):
        cabecera = f"⚠️ <b>{quien}</b> no te ha pagado la cuota de {mes} ({euros(item['importe'])})."
    else:
        cabecera = f"⚠️ No consta pagada la cuota de {mes} de <b>{quien}</b> ({euros(item['importe'])})."
    return (f"{cabecera}\n¿Qué hacemos? <i>(una cuota sin pagar nunca cuenta como pagada)</i>\n"
            "• ➡️ <b>Pasar al mes siguiente</b>: se paga el mes que viene y todo el plan se retrasa un mes.\n"
            "• ➕ <b>Las dos juntas</b>: el mes que viene tocan dos cuotas.\n"
            "• ⏳ <b>Aún puede pagarse</b>: sigue pendiente y te lo recuerdo cada día.")


def botones_salto(deuda, per):
    pagado = "✅ Sí, me ha pagado" if deudas.me_deben(deuda) else "✅ Sí, la pagué"
    return [[(pagado, f"dp:{deuda['id']}:{per}"), ("💸 Otra cantidad", f"dot:{deuda['id']}:{per}")],
            [("➡️ Pasar al mes siguiente", f"dsk:{deuda['id']}:pasar:{per}")],
            [("➕ Las dos juntas", f"dsk:{deuda['id']}:juntas:{per}")],
            [("⏳ Aún puede pagarse", f"dsk:{deuda['id']}:espera:{per}")]]


def botones_pago(deuda, per):
    te_deben = deudas.me_deben(deuda)
    filas = [[("✅ Me ha pagado" if te_deben else "✅ Ya lo pagué", f"dp:{deuda['id']}:{per}")]]
    if deuda["tipo"] in deudas.UNICOS:
        filas[0].append(("💸 Una parte", f"dparte:{deuda['id']}"))
    else:
        filas[0].append(("💸 Otra cantidad", f"dot:{deuda['id']}:{per}"))
    if not te_deben and deuda["tipo"] in deudas.MENSUALES:
        filas.append([("💶 La pago con el próximo cobro", f"dcb:{deuda['id']}:{per}")])
    segunda = []
    if te_deben and deuda["tipo"] == "plazos":
        segunda.append(("⏭️ Saltar este pago", f"dsq:{deuda['id']}:{per}"))
    elif not te_deben and (deuda["tipo"] in deudas.UNICOS or deudas.modo(deuda) == "dia"):
        segunda.append(("📅 Aplazar", f"da:{deuda['id']}:{per}"))
    segunda.append(("🙈 Ignorar", f"dig:{deuda['id']}:{per}"))
    return filas + [segunda]


def _candidatos_metas(d, ahora):
    """Recordatorio de mover/apartar la aportación de cada meta, cada día desde su día hasta confirmarla."""
    lista = []
    nombres = {c["uid"]: consultas.nombre_cuenta(c) for c in consultas.cuentas()}
    posible = None
    for meta in metas.activas():
        pendiente = metas.pendiente_ciclo(meta, d)
        inicio = metas.inicio_recordatorio(meta, d)
        if pendiente <= 0 or not inicio or d < inicio or pospuesto(f"meta:{meta['id']}", ahora):
            continue
        if posible is None:  # v13: lo que se puede mover hoy sin tocar tu libre (las metas ceden primero)
            import resumen
            a = resumen.ahora()
            posible = {m["id"]: parte for m, _, parte in a["metas"]} if a else {}
        texto = texto_meta(meta, pendiente, inicio, d, nombres)
        parte = posible.get(meta["id"], pendiente)
        if parte < pendiente - 0.004:
            texto += (f"\n⚠️ Ahora solo hay <b>{euros(parte)}</b> para esta meta sin tocar tu libre: mueve eso "
                      "(💸 Otra cantidad) o espera a tener más.")
        lista.append((2, f"meta:{meta['id']}:{metas.clave_ciclo(d)}:{d}", texto, botones_meta(meta, pendiente)))
    return lista


def texto_meta(meta, importe, inicio, d, nombres):
    nombre = analisis.e(meta["nombre"])
    desde = f"\n<i>Pendiente desde el {fecha_corta(inicio)}.</i>" if d > inicio else ""
    espera = metas.en_espera(meta, d)
    if espera:
        desde += f"\n<i>Cuota reducida {analisis.e(espera)} (prioridad).</i>"
    icono = "🛟" if meta["especial"] == "colchon" else "🎯"
    if meta["uid"]:
        cuenta = analisis.e(nombres.get(meta["uid"], "su cuenta"))
        return (f"{icono} Mueve <b>{euros(importe)}</b> a «{cuenta}» para <b>{nombre}</b>.\n"
                f"Hazlo en la app de N26 y confírmamelo.{desde}")
    return f"{icono} Aparta <b>{euros(importe)}</b> para <b>{nombre}</b> y confírmamelo.{desde}"


def botones_meta(meta, importe):
    return [[(f"✅ Ya lo moví ({euros_cortos(importe)})", f"mt:ok:{meta['id']}"), ("💸 Otra cantidad", f"mt:otra:{meta['id']}")],
            [("⏭️ Este mes no", f"mt:no:{meta['id']}"), ("🙈 Ignorar", f"mt:ig:{meta['id']}")]]


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
