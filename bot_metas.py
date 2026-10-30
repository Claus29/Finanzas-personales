"""Interfaz de Telegram de 🎯 Metas y 🛟 Colchón de emergencia.

bot.py le pasa los mensajes cuyo paso empieza por «meta_» o «col_» y los botones con los prefijos
de PREFIJOS. El bot NUNCA mueve dinero (el banco es solo lectura): calcula cuánto mover y a qué
cuenta, lo recuerda cada día (en la franja de recordatorios) y solo cuenta lo que confirmas.

Botones de la aportación de cada ciclo (los envía avisos.py y la ficha de la meta):
mt:ok:{id}[:{importe}] ya lo moví · mt:otra:{id} otra cantidad · mt:no:{id} este mes no ·
mt:ig:{id} ignorar hasta mañana · mt:fin:{id} dar por conseguida · mt:lista aportaciones pendientes.
Los de versiones anteriores (g:, gs:, ma:, mo:) siguen funcionando.
"""
import asyncio
import logging
from datetime import date, datetime, time, timedelta

import analisis
import colchon
import config
import consultas
import datos
import metas
from formato import barra, euros, euros_cortos, leer_entero, leer_importe, leer_mes

PREFIJOS = {"g", "gs", "ga", "gr", "gc", "gcf", "ma", "mo", "mt", "col"}
DIAS_RECORDAR = (1, 5, 10, 15, 20, 25)


def _b():
    import bot
    return bot


def hoy():
    return config.ahora().date()


def _datos(espera):
    return {k: v for k, v in espera.items() if k != "paso"}


def e(texto):
    return analisis.e(texto)


# =====================================================================
# Pantallas
# =====================================================================

async def pantalla(update, context, nuevo=False):
    """🎯 Metas (v13): en orden de prioridad, cuánto llevas, cuándo llegas y lo de este ciclo."""
    import vistas
    texto, filas = await asyncio.to_thread(vistas.metas_pantalla)
    await _b().mostrar(update, context, texto, filas, nuevo)


def filas_ficha(meta):
    filas = []
    pendiente = metas.pendiente_ciclo(meta) if meta["activa"] == metas.ACTIVA else 0
    if pendiente > 0:
        filas.append([(f"✅ Ya lo moví ({euros_cortos(pendiente)})", f"mt:ok:{meta['id']}"),
                      ("💸 Otra cantidad", f"mt:otra:{meta['id']}")])
        filas.append([("⏭️ Este mes no", f"mt:no:{meta['id']}")])
    if not meta["uid"]:
        filas.append([("➕ Aportar", f"g:ap:{meta['id']}"), ("➖ Retirar", f"g:re:{meta['id']}")])
    filas.append([("⚙️ Aportación", f"gc:ap:{meta['id']}"), ("⏰ Cuándo", f"gc:rec:{meta['id']}")])
    filas.append([("🔗 Cambiar cuenta" if meta["uid"] else "🔗 Vincular a una cuenta", f"gc:uid:{meta['id']}")])
    if meta["tramo_aporte"] >= 0 or meta["prioridad"]:
        filas.append([("✖️ Quitar prioridad/espera", f"gc:tq:{meta['id']}"), ("⚖️ Ver opciones", "pr:aju")])
    elif meta["activa"] == metas.ACTIVA:
        filas.append([("🥇 Priorizar esta meta", f"prq:{meta['id']}")])
    if meta["especial"] == "colchon":
        filas.append([("⬅️ Metas", "m:metas")])
    else:
        filas.append([("🏁 Terminar", f"gc:fin:{meta['id']}"), ("🗑️ Borrar", f"g:bo:{meta['id']}"),
                      ("⬅️ Metas", "m:metas")])
    return filas


async def ver(update, context, meta_id, nuevo=False):
    meta = metas.obtener(meta_id)
    if not meta or meta["activa"] < 0:
        return "Esa meta ya no existe"
    import vistas
    texto = await asyncio.to_thread(vistas.ficha_meta, meta)
    filas = filas_ficha(meta)
    filas.insert(-1, [("📊 Detalles", f"g:det:{meta['id']}")])
    await _b().mostrar(update, context, texto, filas, nuevo)
    return None


async def lista_pendientes(update, context):
    filas, lineas = [], ["💶 <b>Aportaciones de este ciclo</b>", ""]
    nombres = {c["uid"]: consultas.nombre_cuenta(c) for c in consultas.cuentas()}
    for m in metas.activas():
        pendiente = metas.pendiente_ciclo(m)
        if pendiente <= 0:
            continue
        destino = f"a «{e(nombres.get(m['uid'], 'su cuenta'))}»" if m["uid"] else "(apartar)"
        lineas.append(f"• {e(m['nombre'])}: <b>{euros(pendiente)}</b> {destino}")
        filas.append([(f"✅ {m['nombre'][:16]} {euros_cortos(pendiente)}", f"mt:ok:{m['id']}"),
                      ("💸 Otra", f"mt:otra:{m['id']}"), ("⏭️ No", f"mt:no:{m['id']}")])
    if not filas:
        lineas.append("✅ Ya has confirmado todas las aportaciones de este ciclo.")
    else:
        lineas += ["", "<i>Muévelo en la app de N26 y confírmalo aquí. Lo que no confirmes te lo recuerdo cada día.</i>"]
    await _b().mostrar(update, context, "\n".join(lineas), filas + [[("🎯 Ver metas", "m:metas")]], nuevo=True)


# =====================================================================
# Crear una meta (y activar el colchón, que usa los mismos pasos)
# =====================================================================

def necesaria(d):
    """Lo que habría que apartar al mes para llegar a tiempo con lo que se está creando."""
    if d.get("especial") == "colchon":
        objetivo = max(100.0, round(colchon.gasto_mensual_medio() * d.get("meses", 3) / 10) * 10)
        meses = 12
    else:
        objetivo = d["objetivo"]
        meses = metas.meses_hasta(date.fromisoformat(d["fecha"]), hoy())
    ya = (metas.saldo_cuenta(d["uid"]) or 0.0) if d.get("uid") else d.get("inicial", 0.0)
    return round(max(0.0, objetivo - ya) / meses, 2)


async def preguntar_seguimiento(context, espera):
    b = _b()
    b.esperar(context, "meta_seguimiento", **_datos(espera))
    filas = [[("✍️ Lo apunto yo (aportaciones)", "gs:manual")]]
    filas += [[(f"🔗 Es el saldo de {c['nombre'][:22]}", f"gs:cuenta:{n}")] for n, c in enumerate(consultas.cuentas())]
    await b.enviar(context, "¿Dónde guardas este dinero?\n• <b>En otra cuenta o Espacio de N26</b> (recomendado): lo "
                            "ahorrado es su saldo, se actualiza solo y te digo cuánto mover allí en cada cobro.\n"
                            "• <b>Manual</b>: me dices lo que vas apartando.", filas + [b.CANCELAR])


async def preguntar_aporte(context, espera):
    b = _b()
    b.esperar(context, "meta_aporte", **_datos(espera))
    await b.enviar(context, "💶 ¿Cuánto apartas en cada cobro?\nTe lo pediré siempre así, salvo que en un cobro elijas "
                            "otra cantidad o «este mes no».",
                   [[(f"🧮 La necesaria (~{euros_cortos(necesaria(espera))}/mes)", "ga:nec")],
                    [("✍️ Una cantidad fija", "ga:fija")], b.CANCELAR])


async def preguntar_recordar(context, espera):
    b = _b()
    b.esperar(context, "meta_recordar", **_datos(espera))
    await b.enviar(context, "⏰ ¿Cuándo te recuerdo moverlo? (cada día desde ese día, hasta que lo confirmes)",
                   [[("💶 El día del cobro", "gr:cobro"), ("📅 El día después", "gr:cobro1")],
                    [("🗓️ Un día fijo del mes", "gr:dia")], b.CANCELAR])


async def crear(update, context, d):
    b = _b()
    context.user_data.pop("espera", None)
    if d.get("especial") == "colchon":
        meta_id = colchon.activar(d.get("meses", 3), uid=d.get("uid"), ya_ahorrado=d.get("inicial", 0.0),
                                  aporte_modo=d["aporte_modo"], aporte_fijo=d.get("aporte_fijo", 0.0),
                                  recordar=d["recordar"])
        await b.enviar(context, "🛟 <b>Colchón de emergencia activado</b>\nSu objetivo se recalcula solo con tu gasto real "
                                f"({d.get('meses', 3)} meses de gastos) y cuenta en tu índice de salud financiera.\n\n"
                       + analisis.texto_meta(metas.obtener(meta_id)), [[("⚙️ Ajustes", "m:ajustes")]])
        return
    meta_id, accion = metas.crear(d["nombre"], d["objetivo"], date.fromisoformat(d["fecha"]), uid=d.get("uid"),
                                  ya_ahorrado=d.get("inicial", 0.0), aporte_modo=d["aporte_modo"],
                                  aporte_fijo=d.get("aporte_fijo", 0.0), recordar=d["recordar"])
    logging.info("Meta creada: %s", d["nombre"])
    await b.enviar(context, "✅ Meta creada:\n\n" + analisis.texto_meta(metas.obtener(meta_id)),
                   b.con_deshacer(accion, [[("🎯 Ver metas", "m:metas")]]))
    await b.avisar_proyeccion(context)


async def responder(update, context, espera, escrito):
    """Respuestas escritas de los pasos «meta_*» y «col_*». Devuelve True si las ha atendido."""
    b = _b()
    paso = espera["paso"]
    d = hoy()
    if paso == "meta_nombre":
        b.esperar(context, "meta_objetivo", nombre=escrito[:40])
        await b.enviar(context, f"🎯 {e(escrito[:40])}\n¿Cuánto quieres ahorrar? (ej. 2000)", [b.CANCELAR])
        return True
    if paso == "meta_objetivo":
        importe = leer_importe(escrito)
        if not importe:
            await b.repetir(update, "Escribe el objetivo, por ejemplo <b>2000</b>.")
            return True
        b.esperar(context, "meta_fecha", nombre=espera["nombre"], objetivo=importe)
        await b.enviar(context, "¿Para cuándo? Escribe el mes, por ejemplo <b>agosto 2027</b> o <b>08/2027</b>.", [b.CANCELAR])
        return True
    if paso == "meta_fecha":
        fecha = leer_mes(escrito, d)
        if not fecha:
            await b.repetir(update, "Escribe un mes futuro, por ejemplo <b>agosto 2027</b> o <b>08/2027</b>.")
            return True
        await preguntar_seguimiento(context, {**_datos(espera), "fecha": fecha.isoformat()})
        return True
    if paso == "meta_inicial":
        importe = 0.0 if escrito.strip().lower() in ("0", "0,00", "nada") else leer_importe(escrito)
        if importe is None:
            await b.repetir(update, "Escribe cuánto llevas ya ahorrado (0 si nada).")
            return True
        await preguntar_aporte(context, {**_datos(espera), "inicial": importe})
        return True
    if paso == "meta_fijo":
        importe = leer_importe(escrito)
        if not importe:
            await b.repetir(update, "Escribe la cantidad de cada cobro, por ejemplo <b>100</b>.")
            return True
        await preguntar_recordar(context, {**_datos(espera), "aporte_modo": "fija", "aporte_fijo": importe})
        return True
    if paso == "meta_dia":
        dia = leer_entero(escrito, 1, 28)
        if not dia:
            await b.repetir(update, "Escribe un día del 1 al 28.")
            return True
        await crear(update, context, {**_datos(espera), "recordar": f"dia:{dia}"})
        return True
    if paso in ("meta_aportar", "meta_retirar"):
        importe = leer_importe(escrito)
        if not importe:
            await b.repetir(update, "Escribe el importe, por ejemplo <b>100</b>.")
            return True
        context.user_data.pop("espera", None)
        await aportar(context, espera["meta"], importe if paso == "meta_aportar" else -importe)
        return True
    if paso == "meta_otra":
        importe = leer_importe(escrito)
        if not importe:
            await b.repetir(update, "Escribe cuánto has movido, por ejemplo <b>80</b>.")
            return True
        context.user_data.pop("espera", None)
        await confirmar(update, context, espera["meta"], importe, "otra")
        return True
    if paso == "meta_cfg_fijo":
        importe = leer_importe(escrito)
        if not importe:
            await b.repetir(update, "Escribe la cantidad de cada cobro, por ejemplo <b>100</b>.")
            return True
        context.user_data.pop("espera", None)
        metas.configurar(espera["meta"], "aporte_modo", "fija")
        metas.configurar(espera["meta"], "aporte_fijo", round(importe, 2))
        await b.enviar(context, f"✅ Desde ahora te pediré {euros(importe)} en cada cobro.")
        await ver(update, context, espera["meta"], nuevo=True)
        return True
    if paso == "meta_cfg_dia":
        dia = leer_entero(escrito, 1, 28)
        if not dia:
            await b.repetir(update, "Escribe un día del 1 al 28.")
            return True
        context.user_data.pop("espera", None)
        metas.configurar(espera["meta"], "recordar", f"dia:{dia}")
        await ver(update, context, espera["meta"], nuevo=True)
        return True
    return False


# =====================================================================
# Aportaciones
# =====================================================================

def texto_progreso(meta):
    p = metas.progreso(meta)
    return f"{barra(p['fraccion'])} {p['fraccion']:.0%}  {euros_cortos(p['ahorrado'])} / {euros_cortos(p['objetivo'])}"


async def aportar(context, meta_id, importe):
    """Aportación o retirada manual (metas sin cuenta vinculada)."""
    b = _b()
    accion, conseguida = metas.aportar(meta_id, importe)
    meta = metas.obtener(meta_id)
    texto = (f"{'✅ Aportados' if importe > 0 else '➖ Retirados'} {euros(abs(importe))} a «{e(meta['nombre'])}».\n"
             + texto_progreso(meta))
    if conseguida:
        texto += f"\n\n🎉🎉 <b>¡Meta conseguida!</b> Has ahorrado {euros(meta['objetivo'])} para «{e(meta['nombre'])}»."
    await b.enviar(context, texto, b.con_deshacer(accion))


async def confirmar(update, context, meta_id, importe=None, estado="hecho"):
    b = _b()
    meta = metas.obtener(meta_id)
    if not meta or meta["activa"] != metas.ACTIVA:
        await b.mostrar(update, context, "Esa meta ya no está activa.")
        return
    previo = metas.estado_ciclo(meta)
    if previo and estado != "otra":
        hecho = "lo saltaste" if previo["estado"] == "saltado" else f"confirmaste {euros(previo['importe'])}"
        await b.mostrar(update, context, f"Este ciclo ya {hecho} para «{e(meta['nombre'])}».", [[("🎯 Ver meta", f"g:ver:{meta_id}")]])
        return
    if previo and previo["aportacion_id"]:
        datos.ejecutar("DELETE FROM aportaciones WHERE id = ?", previo["aportacion_id"])  # se sustituye por la nueva
    accion, conseguida = metas.confirmar(meta_id, importe, estado)
    meta = metas.obtener(meta_id)
    if estado == "saltado":
        siguiente = ("el próximo cobro te pediré algo más para llegar a tiempo" if meta["aporte_modo"] != "fija"
                     else "el próximo cobro te lo vuelvo a pedir")
        texto = f"⏭️ Este ciclo no apartas para «{e(meta['nombre'])}»: {siguiente}."
    else:
        fila = metas.estado_ciclo(meta)
        texto = f"✅ Apuntado: {euros(fila['importe'])} para «{e(meta['nombre'])}».\n{texto_progreso(meta)}"
        if meta["uid"]:
            texto += "\n<i>Lo comprobaré en la próxima actualización con el saldo de su cuenta.</i>"
    if conseguida:
        texto += f"\n\n🎉🎉 <b>¡Meta conseguida!</b> Has llegado a {euros(meta['objetivo'])} para «{e(meta['nombre'])}»."
    filas = [[("💶 Otras aportaciones", "mt:lista")]] if any(metas.pendiente_ciclo(m) > 0 for m in metas.activas()) else []
    await b.mostrar(update, context, texto, b.con_deshacer(accion, filas))


# =====================================================================
# Botones
# =====================================================================

async def boton(update, context, partes):  # noqa: C901  (enrutador de botones de metas)
    b = _b()
    clave = partes[0]
    espera = context.user_data.get("espera") or {}

    if clave == "g":
        if partes[1] == "nueva":
            b.esperar(context, "meta_nombre")
            await b.mostrar(update, context, "🎯 ¿Cómo se llama tu meta? (ej. <b>Viaje a Japón</b>)", [b.CANCELAR], nuevo=True)
        elif partes[1] == "ver":
            return await ver(update, context, int(partes[2]))
        elif partes[1] == "det":  # 📊 Detalles: la ficha completa de antes (ritmo real, aportación, recordatorio…)
            meta = metas.obtener(int(partes[2]))
            if meta:
                await b.mostrar(update, context, analisis.texto_meta(meta), [[("⬅️ Volver", f"g:ver:{meta['id']}")]])
        elif partes[1] in ("ap", "re"):
            b.esperar(context, "meta_aportar" if partes[1] == "ap" else "meta_retirar", meta=int(partes[2]))
            await b.mostrar(update, context, f"¿Cuánto {'aportas' if partes[1] == 'ap' else 'retiras'}?", [b.CANCELAR], nuevo=True)
        elif partes[1] == "bo":
            accion = metas.borrar(int(partes[2]))
            await b.mostrar(update, context, "🗑️ Meta borrada.", b.con_deshacer(accion, [[("🎯 Ver metas", "m:metas")]]))
        return None

    # --- Pasos de creación (meta o colchón)
    if clave == "gs":
        if espera.get("paso") != "meta_seguimiento":
            return "Empieza otra vez"
        if partes[1] == "manual":
            b.esperar(context, "meta_inicial", **_datos(espera))
            await b.mostrar(update, context, "¿Cuánto llevas ya ahorrado para esto? (0 si nada)", [b.CANCELAR])
        else:
            cuenta = consultas.cuentas()[int(partes[2])]
            await preguntar_aporte(context, {**_datos(espera), "uid": cuenta["uid"]})
        return None
    if clave == "ga":
        if espera.get("paso") != "meta_aporte":
            return "Empieza otra vez"
        if partes[1] == "nec":
            await preguntar_recordar(context, {**_datos(espera), "aporte_modo": "necesaria", "aporte_fijo": 0.0})
        else:
            b.esperar(context, "meta_fijo", **_datos(espera))
            await b.mostrar(update, context, "✍️ ¿Cuánto en cada cobro? (ej. <b>100</b>)", [b.CANCELAR])
        return None
    if clave == "gr":
        if espera.get("paso") not in ("meta_recordar", "meta_dia"):
            return "Empieza otra vez"
        if partes[1] == "dia":
            b.esperar(context, "meta_dia", **_datos(espera))
            await b.mostrar(update, context, "🗓️ ¿Qué día del mes? Elige o escribe (1–28):",
                            [[(str(n), f"gr:d:{n}") for n in DIAS_RECORDAR], b.CANCELAR])
        elif partes[1] == "d":
            await crear(update, context, {**_datos(espera), "recordar": f"dia:{int(partes[2])}"})
        else:
            await crear(update, context, {**_datos(espera), "recordar": partes[1]})
        return None

    # --- Configurar una meta existente
    if clave == "gc":
        meta = metas.obtener(int(partes[2]))
        if not meta:
            return "Esa meta ya no existe"
        volver = [("⬅️ Volver", f"g:ver:{meta['id']}")]
        if partes[1] == "tq":
            metas.quitar_tramo(meta["id"])
            await ver(update, context, meta["id"])
            return "Vuelve a su cuota normal"
        if partes[1] == "ap":
            await b.mostrar(update, context, f"💶 ¿Cuánto apartas en cada cobro para «{e(meta['nombre'])}»?",
                            [[(f"🧮 La necesaria (~{euros_cortos(metas.progreso(meta)['mensual'])}/mes)", f"gcf:nec:{meta['id']}")],
                             [("✍️ Una cantidad fija", f"gcf:fija:{meta['id']}")], volver])
        elif partes[1] == "rec":
            await b.mostrar(update, context, "⏰ ¿Cuándo empiezo a recordarte la aportación de cada ciclo?",
                            [[("💶 El día del cobro", f"gcf:r:{meta['id']}:cobro"),
                              ("📅 El día después", f"gcf:r:{meta['id']}:cobro1")],
                             [(f"Día {n}", f"gcf:r:{meta['id']}:dia:{n}") for n in DIAS_RECORDAR[:3]],
                             [(f"Día {n}", f"gcf:r:{meta['id']}:dia:{n}") for n in DIAS_RECORDAR[3:]],
                             [("✍️ Otro día", f"gcf:rd:{meta['id']}")], volver])
        elif partes[1] == "uid":
            filas = [[(f"🔗 {c['nombre'][:28]}", f"gcf:u:{meta['id']}:{n}")] for n, c in enumerate(consultas.cuentas())
                     if c["uid"] != meta["uid"]]
            if meta["uid"]:
                filas.append([("✍️ Pasar a manual", f"gcf:u:{meta['id']}:-")])
            await b.mostrar(update, context, "🔗 ¿En qué cuenta guardas el dinero de esta meta?\n"
                                             "<i>Lo ahorrado pasará a ser el saldo de esa cuenta.</i>", filas + [volver])
        elif partes[1] == "fin":
            await b.mostrar(update, context, f"🏁 ¿Dar por terminada «{e(meta['nombre'])}»? Deja de pedir aportaciones.",
                            [[("🎉 Sí, conseguida", f"mt:fin:{meta['id']}"), ("No", f"g:ver:{meta['id']}")]])
        return None
    if clave == "gcf":
        meta_id = int(partes[2])
        if partes[1] == "nec":
            metas.configurar(meta_id, "aporte_modo", "necesaria")
            await ver(update, context, meta_id)
            return "Te pediré la necesaria"
        if partes[1] == "fija":
            b.esperar(context, "meta_cfg_fijo", meta=meta_id)
            await b.mostrar(update, context, "✍️ ¿Cuánto en cada cobro? (ej. <b>100</b>)", [b.CANCELAR], nuevo=True)
        elif partes[1] == "r":
            metas.configurar(meta_id, "recordar", ":".join(partes[3:]))
            await ver(update, context, meta_id)
            return "Guardado"
        elif partes[1] == "rd":
            b.esperar(context, "meta_cfg_dia", meta=meta_id)
            await b.mostrar(update, context, "🗓️ Escribe el día del mes (1–28):", [b.CANCELAR], nuevo=True)
        elif partes[1] == "u":
            uid = None if partes[3] == "-" else consultas.cuentas()[int(partes[3])]["uid"]
            if uid is None:
                meta = metas.obtener(meta_id)
                # Pasa a manual con lo que hay ahora en la cuenta como punto de partida.
                datos.ejecutar("UPDATE metas SET ahorrado = ?, uid = NULL WHERE id = ?", metas.ahorrado(meta), meta_id)
                datos.ejecutar("DELETE FROM aportaciones WHERE meta_id = ?", meta_id)
            else:
                metas.configurar(meta_id, "uid", uid)
            await ver(update, context, meta_id)
            return "Guardado"
        return None

    # --- Aportación del ciclo
    if clave == "mt":
        if partes[1] == "lista":
            await lista_pendientes(update, context)
            return None
        meta_id = int(partes[2])
        if partes[1] == "ok":
            importe = float(partes[3]) if len(partes) > 3 else None
            await confirmar(update, context, meta_id, importe, "hecho" if importe is None else "otra")
        elif partes[1] == "otra":
            b.esperar(context, "meta_otra", meta=meta_id)
            await b.mostrar(update, context, "💸 ¿Cuánto has movido/apartado este ciclo? (ej. <b>80</b>)", [b.CANCELAR], nuevo=True)
        elif partes[1] == "no":
            await confirmar(update, context, meta_id, estado="saltado")
        elif partes[1] == "ig":
            manana = datetime.combine(hoy() + timedelta(days=1), time(0, 0), tzinfo=config.zona())
            datos.posponer(f"meta:{meta_id}", manana)
            (h1, m1), (h2, m2) = config.franja_deudas()
            await b.mostrar(update, context, f"🙈 Ignorado por hoy. Mañana te lo vuelvo a recordar "
                                             f"(entre las {h1:02d}:{m1:02d} y las {h2:02d}:{m2:02d}).")
        elif partes[1] == "fin":
            meta = metas.obtener(meta_id)
            if not meta or meta["activa"] != metas.ACTIVA or meta["especial"]:
                return "Esa meta no se puede terminar"
            metas.terminar(meta_id)
            accion = datos.registrar_accion("metas", meta_id, "UPDATE metas SET activa = 1, completada = NULL WHERE id = ?1",
                                            f"Meta «{meta['nombre']}» terminada")
            await b.mostrar(update, context, f"🎉🎉 <b>¡Meta conseguida!</b> «{e(meta['nombre'])}» "
                                             f"({euros(metas.ahorrado(meta))}). Ya no te pediré aportaciones.",
                            b.con_deshacer(accion, [[("🎯 Ver metas", "m:metas")]]))
        return None

    # --- Botones de versiones anteriores (avisos ya enviados)
    if clave == "ma":
        await aportar(context, int(partes[1]), float(partes[2]))
        return "Apuntado"
    if clave == "mo":
        b.esperar(context, "meta_aportar", meta=int(partes[1]))
        await b.mostrar(update, context, "¿Cuánto has apartado?", [b.CANCELAR], nuevo=True)
        return None

    # --- 🛟 Colchón de emergencia (desde Ajustes)
    if clave == "col":
        return await boton_colchon(update, context, partes)
    return None


# =====================================================================
# 🛟 Colchón de emergencia
# =====================================================================

def texto_colchon():
    gasto = colchon.gasto_mensual_medio()
    s = analisis.saldo_actual()
    lineas = ["🛟 <b>Colchón de emergencia</b>", "",
              "Dinero apartado solo para imprevistos (avería, paro, médico…). Lo habitual es tener "
              "<b>3 a 6 meses de gastos</b>, en una cuenta aparte."]
    if gasto:
        lineas.append(f"Tu gasto medio es {euros(gasto)}/mes → 3 meses = {euros_cortos(round(gasto * 3))} · "
                      f"6 meses = {euros_cortos(round(gasto * 6))}")
    if colchon.activo():
        meta = colchon.meta()
        p = metas.progreso(meta)
        lineas += ["", f"✅ <b>Activado</b>: objetivo {colchon.meses_objetivo()} meses = {euros(meta['objetivo'])}",
                   f"{barra(p['fraccion'])} {p['fraccion']:.0%} ({euros(p['ahorrado'])})"]
    else:
        lineas += ["", "Ahora está <b>desactivado</b>: no te pido aportaciones ni cuenta en tu índice de salud."]
        if s:
            cubiertos = colchon.meses_cubiertos(s["total"])
            if cubiertos is not None:
                lineas.append(f"Tu dinero libre cubriría {str(cubiertos).replace('.', ',')} meses de gastos.")
    return "\n".join(lineas)


async def boton_colchon(update, context, partes):
    b = _b()
    accion = partes[1]
    if accion == "ver":
        if colchon.activo():
            filas = [[("🎯 Ver su ficha", f"g:ver:{colchon.meta()['id']}")],
                     [(f"{'✅ ' if colchon.meses_objetivo() == n else ''}{n} meses", f"col:m:{n}") for n in colchon.MESES_POSIBLES],
                     [("🚫 Desactivar", "col:off")], [("⬅️ Ajustes", "m:ajustes")]]
        else:
            filas = [[("✅ Activar", "col:on")], [("⬅️ Ajustes", "m:ajustes")]]
        await b.mostrar(update, context, texto_colchon(), filas)
    elif accion == "on":
        await b.mostrar(update, context, "🛟 ¿Cuántos meses de gastos quieres cubrir?",
                        [[(f"{n} meses", f"col:n:{n}") for n in colchon.MESES_POSIBLES], b.CANCELAR])
    elif accion == "n":
        await preguntar_seguimiento(context, {"especial": "colchon", "meses": int(partes[2]), "nombre": colchon.NOMBRE})
    elif accion == "m":
        config.guardar("COLCHON_MESES", int(partes[2]))
        colchon.actualizar_objetivo()
        await boton_colchon(update, context, ["col", "ver"])
        return f"Objetivo: {partes[2]} meses"
    elif accion == "off":
        await b.mostrar(update, context, "🚫 ¿Desactivar el colchón? Dejo de pedirte aportaciones; el dinero y los datos "
                                         "se quedan como están.", [[("Sí, desactivar", "col:off2"), ("No", "col:ver")]])
    elif accion == "off2":
        colchon.desactivar()
        await b.mostrar(update, context, "🛟 Colchón desactivado.", [[("⬅️ Ajustes", "m:ajustes")]])
    return None


def linea_ajustes():
    if colchon.activo():
        return f"🛟 Colchón de emergencia: {colchon.meses_objetivo()} meses ({euros_cortos(colchon.meta()['objetivo'])})"
    return "🛟 Colchón de emergencia: desactivado"
