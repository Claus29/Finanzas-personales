"""Interfaz de Telegram de 💳 Deudas: apuntar, ficha, pagar, otra cantidad, saltar, ignorar y análisis.

bot.py le pasa los mensajes cuyo paso empieza por «deuda_» y los botones con los prefijos de PREFIJOS.
Nunca se da nada por pagado: solo cuenta lo que confirmas con «✅».
"""
import asyncio
import math
from datetime import date, datetime, time, timedelta

import analisis
import analisis_deudas
import ciclo
import config
import deudas
import graficos
from formato import (dia_del_mes, euros, euros_cortos, fecha_corta, leer_entero, leer_fecha, leer_importe,
                     sumar_meses)

PREFIJOS = {"d", "dn", "dnf", "dnm", "dpy", "dpf", "dpm", "dpc", "dps", "dgu", "dp", "dot", "dparte", "dsk", "dsq",
            "dig", "dm", "da", "dap", "de", "dcfg", "dcs", "dbo", "dbos", "ad",
            "dpx", "dcb", "dmo", "dvc"}  # v12: empieza en el próximo cobro, con el cobro, cambiar modo, verificar
EXPLICACION = {
    "fecha": "una cantidad con día de pago",
    "cobro": "se paga una sola vez, en cuanto cobres",
    "plazos": "un total que se paga en cuotas",
    "fijo": "cada mes o cada cobro, sin fin (alquiler, ayuda en casa...)",
    "suscripcion": "Netflix, Spotify... con su día de cobro",
    "sin_fecha": "aún no sabes el día (lo pones después)",
}


def _b():
    import bot
    return bot


def hoy():
    return config.ahora().date()


def _datos(espera):
    return {k: v for k, v in espera.items() if k != "paso"}


def _mes_de(texto):
    return date(int(texto[:4]), int(texto[5:7]), 1)


def primera_cuota(espera):
    """Fecha de la 1.ª cuota de una deuda con día fijo que se está apuntando (o None)."""
    if espera.get("modo") != "dia" or not espera.get("dia") or not espera.get("desde"):
        return None
    mes = _mes_de(espera["desde"])
    return dia_del_mes(mes.year, mes.month, int(espera["dia"]))


def texto_primera(espera):
    """Línea del resumen: cuándo es la 1.ª cuota y si resta ya de tu saldo neto."""
    if espera.get("sentido") == "me_deben":
        return ""
    proximo = ciclo.proximo_cobro()
    if espera.get("modo") == "cobro":
        if len(espera.get("desde", "")) == 10 and espera["desde"] <= hoy().isoformat():
            return "📌 1.ª cuota: con el cobro que ya cobraste · <b>se resta ya</b> de tu saldo neto"
        return f"📌 1.ª cuota: con tu próximo cobro (~{fecha_corta(proximo)}) · no se resta hasta que cobres"
    if espera.get("primera") == "cobro":
        return f"📌 1.ª cuota: con tu próximo cobro (~{fecha_corta(proximo)}) · no se resta hasta que cobres"
    vence = primera_cuota(espera)
    if not vence:
        return ""
    if vence < proximo:
        return f"📌 1.ª cuota: {fecha_corta(vence)}, antes de tu cobro · <b>se resta ya</b> de tu saldo neto"
    return f"📌 1.ª cuota: {fecha_corta(vence)} · no se resta hasta el ciclo de ese día"


# =====================================================================
# Pantallas
# =====================================================================

async def pantalla(update, context, nuevo=False):
    b = _b()
    filas = [[("➕ Nueva", "d:nueva"), ("✅ Marcar pagado", "d:pagar")]]
    lista = deudas.activas()
    for n in range(0, len(lista), 2):
        filas.append([(f"{'🤝' if deudas.me_deben(d) else deudas.TIPOS[d['tipo']].split(' ')[0]} {d['nombre'][:18]}",
                       f"d:ver:{d['id']}") for d in lista[n:n + 2]])
    filas.append([("📊 Análisis de deudas", "ad:res")])
    await b.mostrar(update, context, analisis.texto_deudas(), filas, nuevo)


async def ver(update, context, deuda_id, nuevo=False):
    b = _b()
    deuda = deudas.obtener(deuda_id)
    if not deuda or deuda["activa"] != 1:
        return await b.mostrar(update, context, "Esa deuda ya no está activa.", [[("⬅️ Deudas", "m:deudas")]], nuevo)
    te_deben = deudas.me_deben(deuda)
    proximo = deudas.proximo_pago(deuda)
    filas = []
    if deuda["tipo"] in deudas.UNICOS:
        filas.append([("✅ Me ha pagado" if te_deben else "✅ Ya lo pagué", f"dp:{deuda_id}:unico"),
                      ("💸 Una parte", f"dparte:{deuda_id}")])
        if deuda["tipo"] == "sin_fecha":
            filas.append([("📅 Poner día de pago", f"de:{deuda_id}:fecha")])
        else:
            filas.append([("📅 Aplazar", f"da:{deuda_id}:unico")])
    elif proximo and proximo[1]:
        per = proximo[1]
        pagar = "✅ Me ha pagado la cuota" if te_deben else "✅ Pagué la cuota"
        filas.append([(f"{pagar} ({euros_cortos(proximo[2])})", f"dp:{deuda_id}:{per}")])
        segunda = [("💸 Otra cantidad", f"dot:{deuda_id}:{per}")]
        if deuda["tipo"] == "plazos":
            segunda.append(("⏭️ No se pagó", f"dsq:{deuda_id}:{per}"))
        if not te_deben and deudas.modo(deuda) == "dia":
            segunda.append(("📅 Aplazar", f"da:{deuda_id}:{per}"))
        filas.append(segunda)
        if not te_deben and any(i["deuda"]["id"] == deuda_id and i["periodo"] == per for i in deudas.pendientes()):
            filas.append([("💶 Esta cuota, con el próximo cobro", f"dcb:{deuda_id}:{per}")])
    if not te_deben and deuda["tipo"] in deudas.MENSUALES:
        filas.append([("🔁 Cambiar cuándo se paga", f"dmo:{deuda_id}")])
    if deuda["tipo"] == "plazos":
        filas.append([("⚙️ Si una cuota no se paga", f"dcfg:{deuda_id}")])
        campos = [("✏️ Total", "importe"), ("✏️ Cuota", "cuota")]
    elif deuda["tipo"] in ("fijo", "suscripcion"):
        campos = [("✏️ Importe", "importe")]
    elif deuda["tipo"] == "fecha":
        campos = [("✏️ Importe", "importe"), ("✏️ Día de pago", "fecha")]
    else:
        campos = [("✏️ Importe", "importe")]
    if deuda["tipo"] in deudas.MENSUALES and deudas.modo(deuda) == "dia":
        campos.append(("✏️ Día", "dia"))
    filas.append([(t, f"de:{deuda_id}:{c}") for t, c in campos] + [("✏️ Nombre", f"de:{deuda_id}:nombre")])
    filas.append([("🗑️ Borrar", f"dbo:{deuda_id}"), ("⬅️ Deudas", "m:deudas")])
    await b.mostrar(update, context, analisis.texto_deuda(deuda), filas, nuevo)


# =====================================================================
# Apuntar (pasos guiados)
# =====================================================================

async def preguntar_ya_pagado(context, espera):
    b = _b()
    b.esperar(context, "deuda_yapagado_boton", **_datos(espera))
    verbo = "te ha pagado ya algo" if espera.get("sentido") == "me_deben" else "llevas algo pagado ya"
    await b.enviar(context, f"🔁 Total: {euros(espera['importe'])}. ¿{verbo[0].upper() + verbo[1:]}?",
                   [[("No, nada", "dpy:0"), ("Sí, algo", "dpy:si")], b.CANCELAR])


async def preguntar_forma(context, espera):
    b = _b()
    b.esperar(context, "deuda_forma", **_datos(espera))
    queda = round(espera["importe"] - espera.get("ya_pagado", 0), 2)
    await b.enviar(context, f"Quedan {euros(queda)}. ¿Cómo se paga?",
                   [[("💶 Una cuota fija (ej. 80 €)", "dpf:cuota")], [("🔢 En X cuotas iguales", "dpf:n")], b.CANCELAR])


def plan(espera):
    """(cuotas, última cuota) de unos plazos."""
    queda = round(espera["importe"] - espera.get("ya_pagado", 0), 2)
    cuotas = max(1, math.ceil(queda / espera["cuota"] - 1e-9))
    return cuotas, round(queda - espera["cuota"] * (cuotas - 1), 2)


def texto_plan(espera):
    cuotas, ultima = plan(espera)
    if cuotas == 1:
        return f"Será 1 cuota de {euros(ultima)}."
    if abs(ultima - espera["cuota"]) < 0.005:
        return f"Serán {cuotas} cuotas de {euros(espera['cuota'])}."
    return f"Serán {cuotas} cuotas: {cuotas - 1} de {euros(espera['cuota'])} y la última de {euros(ultima)}."


async def preguntar_modo(context, espera, texto_previo=""):
    b = _b()
    b.esperar(context, "deuda_modo", **_datos(espera))
    if espera.get("sentido") == "me_deben":
        filas = [[("📅 Un día fijo del mes", "dpm:dia")], [("🕐 Sin día fijo (te pregunto los días 5, 15 y 25)", "dpm:sin")]]
        pregunta = "¿Cuándo te paga cada cuota?"
    else:
        filas = [[("📅 Un día fijo del mes", "dpm:dia")], [("💶 En cuanto cobro", "dpm:cobro")]]
        pregunta = "¿Cuándo se paga?" if espera["tipo"] == "fijo" else "¿Cuándo pagas cada cuota?"
    await b.enviar(context, f"{texto_previo}\n{pregunta}".strip(), filas + [b.CANCELAR])


async def siguiente(update, context, espera):
    """Decide el siguiente paso cuando ya se sabe cuándo se paga."""
    b = _b()
    vence = primera_cuota(espera)
    if (vence and espera.get("sentido", "debo") == "debo" and "primera" not in espera
            and vence < ciclo.proximo_cobro()):
        # v12: la 1.ª cuota cae antes del próximo cobro → se restaría ya del saldo neto. Se pregunta siempre.
        proximo = ciclo.proximo_cobro()
        que = "La <b>1.ª cuota</b>" if espera["tipo"] == "plazos" else "El <b>primer pago</b>"
        lo = "la" if espera["tipo"] == "plazos" else "lo"
        importe = espera.get("cuota") or espera["importe"]
        b.esperar(context, "deuda_verificar", **_datos(espera))
        pasada = " (ya pasó y no está pagada)" if vence < hoy() else ""
        return await b.enviar(context, f"📌 {que} ({euros(importe)}) es el <b>{fecha_corta(vence)}</b>{pasada}, "
                                       f"antes de tu cobro (~{fecha_corta(proximo)}).\nSi {lo} pagas este ciclo, "
                                       f"se resta ya de tu saldo neto. ¿Cuándo {lo} pagas?",
                              [[("✅ Este ciclo", "dvc:este")],
                               [(f"💶 En cuanto cobre (~{fecha_corta(proximo)})", "dvc:cobro")],
                               [("📅 Empiezo el mes que viene", "dvc:sig")], b.CANCELAR])
    if espera["tipo"] == "plazos" and "si_no_paga" not in espera:
        b.esperar(context, "deuda_si_no_paga", **_datos(espera))
        quien = "no te paga" if espera.get("sentido") == "me_deben" else "no se paga"
        return await b.enviar(context, f"Si una cuota {quien} en su mes, ¿qué hacemos?\n"
                                       "<i>(una cuota sin pagar nunca cuenta como pagada)</i>",
                              [[("❓ Preguntarme cada vez", "dps:preguntar")],
                               [("➡️ Pasarla al mes siguiente", "dps:pasar")],
                               [("➕ Pagar las dos juntas", "dps:juntas")], b.CANCELAR])
    if espera["tipo"] == "plazos":
        b.esperar(context, "deuda_confirmar", **_datos(espera))
        return await b.enviar(context, texto_resumen(espera), [[("✅ Guardar", "dgu")], b.CANCELAR])
    return await crear(update, context, espera)


def texto_resumen(espera):
    te_deben = espera.get("sentido") == "me_deben"
    ya = espera.get("ya_pagado", 0)
    cuotas, ultima = plan(espera)
    cuando = {"dia": f"el día {espera.get('dia')} de cada mes", "cobro": "en cuanto cobres",
              "sin": "sin día fijo (te pregunto los días " + ", ".join(map(str, config.dias_aviso_sin_dia())) + ")"}[espera["modo"]]
    lineas = [f"🔁 <b>{analisis.e(espera['nombre'])}</b> · {'te lo deben' if te_deben else 'lo debes'}",
              f"Total {euros(espera['importe'])}" + (f" · ya {'pagado' if not te_deben else 'cobrado'} {euros(ya)}" if ya else ""),
              f"Quedan <b>{euros(round(espera['importe'] - ya, 2))}</b>: {texto_plan(espera).lower().replace('será', '').replace('serán', '').strip().rstrip('.')}",
              f"Cada cuota: {cuando}",
              f"Si una cuota no se paga: {deudas.SI_NO_PAGA[espera['si_no_paga']]}"]
    primera = texto_primera(espera)
    if primera:
        lineas.append(primera)
    return "\n".join(lineas) + "\n\n¿Lo guardo?"


async def crear(update, context, d):
    b = _b()
    context.user_data.pop("espera", None)
    tipo, nombre, importe = d["tipo"], d["nombre"], d["importe"]
    sentido = d.get("sentido", "debo")
    if tipo == "plazos":
        cuotas, _ = plan(d)
        deuda_id, accion = deudas.crear(nombre, tipo, importe, cuota=d["cuota"], cuotas_total=cuotas, dia=d.get("dia"),
                                        desde=d["desde"], sentido=sentido, modo=d["modo"], si_no_paga=d["si_no_paga"],
                                        ya_pagado=d.get("ya_pagado", 0))
    elif tipo in ("fijo", "suscripcion"):
        deuda_id, accion = deudas.crear(nombre, tipo, importe, cuota=importe, dia=d.get("dia"), desde=d["desde"],
                                        modo=d.get("modo", "dia"))
    elif tipo == "fecha":
        deuda_id, accion = deudas.crear(nombre, tipo, importe, fecha=d["fecha"], sentido=sentido)
    elif tipo == "cobro":
        # Una sola vez, con el próximo salario (a partir de mañana si ya cobraste este mes).
        deuda_id, accion = deudas.crear(nombre, tipo, importe, desde=(hoy() + timedelta(days=1)).isoformat()
                                        if ciclo.cobrado_este_mes() else hoy().isoformat())
    else:
        deuda_id, accion = deudas.crear(nombre, "sin_fecha", importe, sentido=sentido)
    if d.get("primera") == "cobro" and deudas.modo(deudas.obtener(deuda_id)) == "dia":
        deudas.al_cobro(deuda_id, d["desde"][:7])  # la 1.ª cuota, con el próximo cobro (todo el plan se mueve)
    deuda = deudas.obtener(deuda_id)
    b.logging.info("Apuntado: %s", nombre)
    (h1, m1), (h2, m2) = config.franja_deudas()
    nota = ""
    if deuda["tipo"] == "sin_fecha":
        nota = "\n💡 Cuando sepas el día, pónselo (📅 Poner día de pago) y te lo recordaré."
    else:
        nota = f"\n🔔 Te lo recordaré entre las {h1:02d}:{m1:02d} y las {h2:02d}:{m2:02d} hasta que lo confirmes."
    if sentido == "debo" and deuda["tipo"] != "sin_fecha":
        nota = f"\n{analisis.texto_en_neto(deuda)}" + nota
    await b.enviar(context, f"✅ Apuntado:\n{analisis.linea_deuda(deuda)}{nota}",
                   b.con_deshacer(accion, [[("💳 Ver deudas", "m:deudas")]]))
    await b.avisar_proyeccion(context)


async def responder(update, context, espera, escrito):
    """Respuestas escritas de los pasos «deuda_...». Devuelve True si las ha atendido."""
    b = _b()
    paso = espera["paso"]
    d = hoy()

    if paso == "deuda_nombre":
        b.esperar(context, "deuda_importe", **{**_datos(espera), "nombre": escrito[:40]})
        te_deben = espera.get("sentido") == "me_deben"
        pregunta = {"plazos": "¿Cuánto es <b>en total</b>?", "fijo": "¿Cuánto es <b>cada vez</b>?",
                    "suscripcion": "¿Cuánto cuesta <b>al mes</b>?"}.get(espera["tipo"],
                                                                         "¿Cuánto te debe?" if te_deben else "¿Cuánto es?")
        await b.enviar(context, f"💳 {analisis.e(escrito[:40])}\n{pregunta} (por ejemplo 409,25)", [b.CANCELAR])
        return True
    if paso == "deuda_importe":
        importe = leer_importe(escrito)
        if not importe:
            await b.repetir(update, "Escribe solo el importe, por ejemplo <b>409,25</b>.")
            return True
        espera = {**espera, "importe": importe}
        tipo = espera["tipo"]
        if tipo == "plazos":
            await preguntar_ya_pagado(context, espera)
        elif tipo == "fijo":
            await preguntar_modo(context, espera)
        elif tipo == "suscripcion":
            b.esperar(context, "deuda_dia", **{**_datos(espera), "modo": "dia"})
            await b.enviar(context, "📅 ¿Qué <b>día del mes</b> se cobra? (1-31)", [b.CANCELAR])
        elif tipo == "fecha":
            b.esperar(context, "deuda_fecha", **_datos(espera))
            fin = sumar_meses(d, 0, 31)
            pregunta = "¿Qué día te lo tiene que pagar?" if espera.get("sentido") == "me_deben" else "¿Para cuándo?"
            await b.enviar(context, f"📅 {pregunta} Escribe la fecha (ej. <b>20/11</b>) o elige:",
                           [[("Mañana", f"dnf:{(d + timedelta(days=1)).isoformat()}"),
                             ("En 1 semana", f"dnf:{(d + timedelta(days=7)).isoformat()}")],
                            [("A fin de mes", f"dnf:{fin.isoformat()}")], b.CANCELAR])
        else:
            await crear(update, context, _datos(espera))
        return True
    if paso == "deuda_yapagado":
        importe = leer_importe(escrito)
        if not importe or importe >= espera["importe"]:
            await b.repetir(update, f"Escribe cuánto llevas (menos de {euros(espera['importe'])}).")
            return True
        await preguntar_forma(context, {**espera, "ya_pagado": importe})
        return True
    if paso == "deuda_cuota":
        importe = leer_importe(escrito)
        queda = round(espera["importe"] - espera.get("ya_pagado", 0), 2)
        if not importe or importe > queda:
            await b.repetir(update, f"Escribe la cuota, por ejemplo <b>80</b> (como mucho {euros(queda)}).")
            return True
        espera = {**espera, "cuota": importe}
        await preguntar_modo(context, espera, f"👍 {texto_plan(espera)}")
        return True
    if paso == "deuda_ncuotas":
        cuotas = leer_entero(escrito, 1, 360)
        if not cuotas:
            await b.repetir(update, "Escribe el número de cuotas, por ejemplo <b>5</b>.")
            return True
        queda = round(espera["importe"] - espera.get("ya_pagado", 0), 2)
        espera = {**espera, "cuota": math.ceil(queda / cuotas * 100) / 100}
        await preguntar_modo(context, espera, f"👍 {texto_plan(espera)}")
        return True
    if paso == "deuda_dia":
        dia = leer_entero(escrito, 1, 31)
        if not dia:
            await b.repetir(update, "Escribe un día del 1 al 31.")
            return True
        espera = {**espera, "dia": dia}
        if dia < d.day:
            b.esperar(context, "deuda_mes", **_datos(espera))
            te_deben = espera.get("sentido") == "me_deben"
            que = "la cuota" if espera["tipo"] == "plazos" else "el pago"
            pregunta = f"¿Ya te ha pagado {que} de este mes?" if te_deben else f"¿Ya está pagado {que} de este mes?"
            await b.enviar(context, f"El día {dia} de este mes ya ha pasado. {pregunta}",
                           [[("✅ Sí", "dnm:siguiente"), ("❌ Aún no", "dnm:este")], b.CANCELAR])
        else:
            await siguiente(update, context, {**espera, "desde": f"{d:%Y-%m}"})
        return True
    if paso == "deuda_nuevo_dia":  # 🔁 cambiar a día fijo
        dia = leer_entero(escrito, 1, 31)
        if not dia:
            await b.repetir(update, "Escribe un día del 1 al 31.")
            return True
        context.user_data.pop("espera", None)
        deuda_id = espera["deuda"]
        texto, accion, per = deudas.cambiar_modo(deuda_id, "dia", dia)
        filas = [[("👀 Ver", f"d:ver:{deuda_id}")]]
        vence = deudas.vencimiento(deudas.obtener(deuda_id), per)
        if vence < ciclo.proximo_cobro():
            texto += (f".\n📌 Cae antes de tu cobro, así que <b>se resta ya</b> de tu saldo neto. "
                      "Si prefieres pagarla en cuanto cobres, pulsa 💶")
            filas.insert(0, [("💶 Esa cuota, con el próximo cobro", f"dcb:{deuda_id}:{per}")])
        await b.enviar(context, f"🔁 {analisis.e(deudas.obtener(deuda_id)['nombre'])}: {texto}.",
                       b.con_deshacer(accion, filas))
        return True
    if paso == "deuda_fecha":
        fecha = leer_fecha(escrito, d)
        if not fecha:
            await b.repetir(update, "Escribe la fecha como <b>20/11</b> o <b>20/11/2026</b>.")
            return True
        await crear(update, context, {**_datos(espera), "fecha": fecha.isoformat()})
        return True
    if paso in ("deuda_parte", "deuda_otra"):
        importe = leer_importe(escrito)
        deuda = deudas.obtener(espera["deuda"])
        maximo = deuda["importe"] if paso == "deuda_parte" else (
            deudas.restante(deuda)[0] if deuda["tipo"] == "plazos" else 100000)
        if not importe or importe > maximo + 0.004:
            await b.repetir(update, f"Escribe el importe (como mucho {euros(maximo)}).")
            return True
        context.user_data.pop("espera", None)
        per = "unico" if paso == "deuda_parte" else espera["periodo"]
        resultado, accion = deudas.pagar(deuda["id"], per, importe)
        await b.enviar(context, f"✅ {analisis.e(deuda['nombre'])}: {analisis.e(resultado)}.", b.con_deshacer(accion))
        await b.repartir_lo_que_te_pagan(context, deuda)
        return True
    if paso == "deuda_aplazar":
        fecha = leer_fecha(escrito, d)
        if not fecha or fecha <= d:
            await b.repetir(update, "Escribe una fecha futura, por ejemplo <b>28/11</b>.")
            return True
        context.user_data.pop("espera", None)
        resultado = deudas.aplazar(espera["deuda"], espera["periodo"], nueva_fecha=fecha)
        await b.enviar(context, f"📅 {analisis.e(deudas.obtener(espera['deuda'])['nombre'])}: {resultado}.")
        return True
    if paso == "deuda_editar":
        deuda = deudas.obtener(espera["deuda"])
        campo = espera["campo"]
        if campo in ("importe", "cuota"):
            valor = leer_importe(escrito)
        elif campo == "dia":
            valor = leer_entero(escrito, 1, 31)
        elif campo == "fecha":
            fecha = leer_fecha(escrito, d)
            valor = fecha.isoformat() if fecha else None
        else:
            valor = escrito[:40]
        if not valor:
            await b.repetir(update, "No lo he entendido, prueba otra vez.")
            return True
        context.user_data.pop("espera", None)
        deudas.cambiar(deuda["id"], campo, valor)
        await b.enviar(context, "✅ Cambiado.")
        await ver(update, context, deuda["id"], nuevo=True)
        return True
    return False


# =====================================================================
# Botones
# =====================================================================

async def boton(update, context, partes):  # noqa: C901  (enrutador de botones de deudas)
    b = _b()
    clave = partes[0]
    d = hoy()
    espera = context.user_data.get("espera") or {}

    if clave == "d":
        if partes[1] == "nueva" and len(partes) == 2:
            await b.mostrar(update, context, "💳 ¿Qué quieres apuntar?",
                            [[("💸 Lo que YO debo", "d:nueva:debo")], [("🤝 Lo que ME DEBEN", "d:nueva:me_deben")], b.CANCELAR])
        elif partes[1] == "nueva":
            sentido = partes[2]
            tipos = deudas.TIPOS_POR_SENTIDO[sentido]
            titulo = "🤝 <b>Lo que te deben</b>" if sentido == "me_deben" else "💸 <b>Lo que debes</b>"
            texto_tipos = "\n".join(f"• <b>{deudas.TIPOS[t].split(' ', 1)[1]}</b>: {EXPLICACION[t]}" for t in tipos)
            await b.mostrar(update, context, f"{titulo}\n{texto_tipos}",
                            [[(deudas.TIPOS[t], f"dn:{t}:{sentido}")] for t in tipos] + [b.CANCELAR])
        elif partes[1] == "ver":
            await ver(update, context, int(partes[2]))
        elif partes[1] == "pagar":
            items = deudas.pendientes() + deudas.por_cobrar()
            filas = [[(f"{'🤝 ' if deudas.me_deben(i['deuda']) else ''}{i['deuda']['nombre'][:18]} "
                       f"{euros_cortos(i['importe'])} ({fecha_corta(i['vence'])})",
                       f"dp:{i['deuda']['id']}:{i['periodo']}")] for i in items]
            texto = ("✅ ¿Qué has pagado (o qué te han pagado 🤝)?" if items
                     else "No hay pagos pendientes en este ciclo ✅")
            await b.mostrar(update, context, texto, filas + [[("⬅️ Deudas", "m:deudas")]])
        return None
    if clave == "dn":
        sentido = partes[2] if len(partes) > 2 else "debo"
        b.esperar(context, "deuda_nombre", tipo=partes[1], sentido=sentido)
        if sentido == "me_deben":
            pregunta, ejemplo = "¿Quién te lo debe?", {"fecha": "Pedro", "plazos": "Laura"}.get(partes[1], "Marcos")
        else:
            pregunta = "¿Qué nombre le pongo?"
            ejemplo = {"fecha": "Juan", "cobro": "Mamá", "plazos": "Mamá", "fijo": "Alquiler",
                       "suscripcion": "Netflix"}.get(partes[1], "Deuda")
        await b.mostrar(update, context, f"{deudas.TIPOS[partes[1]]}\n{pregunta} (ej. <b>{ejemplo}</b>)", [b.CANCELAR])
        return None

    if clave == "dcb":  # 💶 esta cuota, con el próximo cobro (todo el plan se mueve)
        deuda_id, per = int(partes[1]), ":".join(partes[2:])
        deuda = deudas.obtener(deuda_id)
        if not deuda or deuda["activa"] != 1 or per in deudas.periodos_pagados(deuda_id):
            await b.mostrar(update, context, "Esa cuota ya no está pendiente.")
            return None
        texto, accion = deudas.al_cobro(deuda_id, per)
        await b.mostrar(update, context, f"💶 {analisis.e(deuda['nombre'])}: {texto}.\n<i>No cuenta como pagada: "
                                         "te la recordaré con el cobro.</i>",
                        b.con_deshacer(accion, [[("🧮 Saldo neto", "m:neto")]]) if accion else [[("🧮 Saldo neto", "m:neto")]])
        return None
    if clave == "dmo":  # 🔁 cambiar cuándo se paga: día fijo ↔ en cuanto cobre
        deuda = deudas.obtener(int(partes[1]))
        if len(partes) == 2:
            actual = "💶 en cuanto cobras" if deudas.modo(deuda) == "cobro" else f"📅 el día {deuda['dia']} de cada mes"
            await b.mostrar(update, context, f"🔁 «{analisis.e(deuda['nombre'])}» ahora se paga {actual}.\n"
                                             "¿Cuándo quieres pagar cada cuota?",
                            [[("📅 Un día fijo del mes", f"dmo:{deuda['id']}:dia")],
                             [("💶 En cuanto cobro", f"dmo:{deuda['id']}:cobro")],
                             [("⬅️ Volver", f"d:ver:{deuda['id']}")]])
            return None
        if partes[2] == "dia":
            b.esperar(context, "deuda_nuevo_dia", deuda=deuda["id"])
            await b.mostrar(update, context, "📅 ¿Qué <b>día del mes</b>? (1-31)", [b.CANCELAR])
            return None
        texto, accion, _ = deudas.cambiar_modo(deuda["id"], "cobro")
        await b.mostrar(update, context, f"🔁 {analisis.e(deuda['nombre'])}: {texto}.",
                        b.con_deshacer(accion, [[("👀 Ver", f"d:ver:{deuda['id']}")]]))
        return None
    if clave == "dvc":  # verificación al apuntar: la 1.ª cuota cae antes del cobro
        if espera.get("paso") != "deuda_verificar":
            return "Empieza otra vez desde 💳 Deudas"
        datos_espera = _datos(espera)
        if partes[1] == "sig":
            mes = _mes_de(datos_espera["desde"])
            datos_espera["desde"] = f"{sumar_meses(mes, 1, 1):%Y-%m}"
        await siguiente(update, context, {**datos_espera, "primera": partes[1]})
        return None

    # --- Pasos guiados con botones
    if clave in ("dnf", "dpy", "dpf", "dpm", "dpc", "dps", "dgu", "dnm") and not espera.get("paso", "").startswith("deuda_"):
        return "Empieza otra vez desde 💳 Deudas"
    if clave == "dnf":
        await crear(update, context, {**_datos(espera), "fecha": partes[1]})
        return None
    if clave == "dpy":
        if partes[1] == "0":
            await preguntar_forma(context, {**espera, "ya_pagado": 0})
        else:
            b.esperar(context, "deuda_yapagado", **_datos(espera))
            await b.mostrar(update, context, "¿Cuánto llevas ya?", [b.CANCELAR])
        return None
    if clave == "dpf":
        b.esperar(context, "deuda_cuota" if partes[1] == "cuota" else "deuda_ncuotas", **_datos(espera))
        await b.mostrar(update, context, "¿De cuánto es cada cuota? (ej. <b>80</b>)" if partes[1] == "cuota"
                        else "¿En cuántas cuotas? (ej. <b>5</b>)", [b.CANCELAR])
        return None
    if clave == "dpm":
        espera = {**espera, "modo": partes[1]}
        if partes[1] == "dia":
            b.esperar(context, "deuda_dia", **_datos(espera))
            await b.mostrar(update, context, "📅 ¿Qué <b>día del mes</b>? (1-31)", [b.CANCELAR])
        elif partes[1] == "cobro":
            if ciclo.cobrado_este_mes(d):
                b.esperar(context, "deuda_modo", **_datos(espera))
                salario = ciclo.ultimo_salario(d)
                cuando = f"el {salario['fecha'][8:10]}/{salario['fecha'][5:7]}" if salario else "este mes"
                que = "la 1.ª cuota" if espera["tipo"] == "plazos" else "el primer pago"
                await b.mostrar(update, context, f"Ya cobraste {cuando}. ¿Con qué cobro pagas {que}?",
                                [[("⏭️ Con el próximo cobro", "dpc:si")],
                                 [("💶 Con el que ya cobré, aún sin pagar", "dpc:no")],
                                 [("✅ Con el que ya cobré, ya pagada" if espera["tipo"] == "plazos"
                                   else "✅ Con el que ya cobré, ya pagado", "dpc:si")], b.CANCELAR])
            else:
                await siguiente(update, context, {**espera, "desde": d.isoformat()})
        else:  # sin día fijo
            b.esperar(context, "deuda_mes", **_datos(espera))
            await b.mostrar(update, context, "¿Ya te ha pagado la cuota de este mes?",
                            [[("✅ Sí", "dnm:siguiente"), ("❌ Aún no", "dnm:este")], b.CANCELAR])
        return None
    if clave == "dpc":
        salario = ciclo.ultimo_salario(d)
        desde = (d + timedelta(days=1)).isoformat() if partes[1] == "si" or not salario else salario["fecha"]
        await siguiente(update, context, {**espera, "desde": desde})
        return None
    if clave == "dpx":
        deuda = deudas.obtener(int(partes[1]))
        if not deuda or not deudas.cuota_de_cobro_ya_cobrado(deuda):
            await b.mostrar(update, context, "Eso ya no hace falta: no hay ninguna cuota de un cobro ya cobrado.")
            return None
        texto, accion = deudas.empezar_en_proximo_cobro(deuda["id"])
        await b.mostrar(update, context, f"⏭️ {analisis.e(deuda['nombre'])}: {texto}.", b.con_deshacer(accion))
        return None
    if clave == "dnm":
        mes = d if partes[1] == "este" else sumar_meses(d, 1, 1)
        await siguiente(update, context, {**espera, "desde": f"{mes:%Y-%m}"})
        return None
    if clave == "dps":
        await siguiente(update, context, {**espera, "si_no_paga": partes[1]})
        return None
    if clave == "dgu":
        await crear(update, context, _datos(espera))
        return "Guardado"

    # --- Pagos, otra cantidad, saltos, ignorar
    if clave == "dp":
        deuda = deudas.obtener(int(partes[1]))
        if not deuda or deuda["activa"] != 1:
            return "Ya estaba marcada"
        per = ":".join(partes[2:])
        if per != "unico" and per in deudas.periodos_pagados(deuda["id"]):
            return "Ese pago ya estaba marcado"
        resultado, accion = deudas.pagar(deuda["id"], per)
        b.logging.info("%s: %s", "Cobro confirmado" if deudas.me_deben(deuda) else "Pago confirmado", deuda["nombre"])
        await b.mostrar(update, context, f"✅ {analisis.e(deuda['nombre'])}: {analisis.e(resultado)}.", b.con_deshacer(accion))
        await b.repartir_lo_que_te_pagan(context, deuda)
        return "Hecho"
    if clave == "dot":
        deuda = deudas.obtener(int(partes[1]))
        b.esperar(context, "deuda_otra", deuda=deuda["id"], periodo=":".join(partes[2:]))
        pregunta = "¿Cuánto te ha pagado?" if deudas.me_deben(deuda) else "¿Cuánto has pagado?"
        await b.mostrar(update, context, f"💸 {pregunta}\n<i>Cubre la cuota de este mes; la diferencia va al final.</i>",
                        [b.CANCELAR], nuevo=True)
        return None
    if clave == "dparte":
        deuda = deudas.obtener(int(partes[1]))
        b.esperar(context, "deuda_parte", deuda=deuda["id"])
        await b.mostrar(update, context, "💸 ¿Cuánto te ha pagado?" if deudas.me_deben(deuda) else "💸 ¿Cuánto has pagado?",
                        [b.CANCELAR], nuevo=True)
        return None
    if clave == "dsq":
        deuda = deudas.obtener(int(partes[1]))
        per = ":".join(partes[2:])
        await b.mostrar(update, context, f"⏭️ La cuota de {deudas.nombre_periodo(per)} de «{analisis.e(deuda['nombre'])}» "
                                         "no se ha pagado. ¿Qué hacemos?\n<i>Nunca cuenta como pagada.</i>",
                        [[("➡️ Pasar al mes siguiente", f"dsk:{deuda['id']}:pasar:{per}")],
                         [("➕ Las dos juntas el mes siguiente", f"dsk:{deuda['id']}:juntas:{per}")],
                         [("⏳ Aún puede pagarse", f"dsk:{deuda['id']}:espera:{per}")], b.CANCELAR])
        return None
    if clave == "dsk":
        deuda_id, decision, per = int(partes[1]), partes[2], ":".join(partes[3:])
        if decision == "espera":
            b.datos.marcar_enviado(f"espera:{deuda_id}:{per}")
            await b.mostrar(update, context, "⏳ Vale: sigue pendiente y te lo recordaré cada día hasta que se pague.")
            return None
        texto, accion = deudas.saltar(deuda_id, per, decision)
        await b.mostrar(update, context, f"✅ {analisis.e(deudas.obtener(deuda_id)['nombre'])}: {texto}.",
                        b.con_deshacer(accion))
        return None
    if clave in ("dig", "dm"):
        manana = datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=config.zona())
        b.datos.posponer(f"deuda:{partes[1]}:{':'.join(partes[2:])}", manana)
        (h1, m1), (h2, m2) = config.franja_deudas()
        await b.mostrar(update, context, f"🙈 Ignorado por hoy. Mañana te lo vuelvo a recordar "
                                         f"(entre las {h1:02d}:{m1:02d} y las {h2:02d}:{m2:02d}).")
        return None
    if clave == "da":
        deuda = deudas.obtener(int(partes[1]))
        per = ":".join(partes[2:])
        filas = [[("+3 días", f"dap:{deuda['id']}:3:{per}"), ("+1 semana", f"dap:{deuda['id']}:7:{per}")]]
        if not deudas.me_deben(deuda):
            filas.append([("💶 Al próximo cobro", f"dap:{deuda['id']}:cobro:{per}")])
        filas += [[("✍️ Otra fecha", f"dap:{deuda['id']}:otra:{per}")], b.CANCELAR]
        await b.mostrar(update, context, f"📅 ¿Cuál es el nuevo día de pago de «{analisis.e(deuda['nombre'])}»?", filas)
        return None
    if clave == "dap":
        deuda_id, opcion, per = int(partes[1]), partes[2], ":".join(partes[3:])
        if opcion == "otra":
            b.esperar(context, "deuda_aplazar", deuda=deuda_id, periodo=per)
            await b.mostrar(update, context, "Escribe la nueva fecha (ej. <b>28/11</b>):", [b.CANCELAR])
            return None
        if opcion == "cobro":
            resultado, _ = deudas.al_cobro(deuda_id, per)
        else:
            resultado = deudas.aplazar(deuda_id, per, nueva_fecha=d + timedelta(days=int(opcion)))
        await b.mostrar(update, context, f"📅 {analisis.e(deudas.obtener(deuda_id)['nombre'])}: {resultado}.")
        return None
    if clave == "dcfg":
        deuda = deudas.obtener(int(partes[1]))
        filas = [[(("✔️ " if deuda["si_no_paga"] == k else "") + v, f"dcs:{deuda['id']}:{k}")] for k, v in deudas.SI_NO_PAGA.items()]
        await b.mostrar(update, context, f"⚙️ Si una cuota de «{analisis.e(deuda['nombre'])}» no se paga en su mes:\n"
                                         "<i>(nunca cuenta como pagada)</i>", filas + [[("⬅️ Volver", f"d:ver:{deuda['id']}")]])
        return None
    if clave == "dcs":
        deudas.cambiar(int(partes[1]), "si_no_paga", partes[2])
        await ver(update, context, int(partes[1]))
        return deudas.SI_NO_PAGA[partes[2]]
    if clave == "de":
        b.esperar(context, "deuda_editar", deuda=int(partes[1]), campo=partes[2])
        pregunta = {"importe": "el nuevo importe (total, si es a plazos)", "cuota": "la nueva cuota",
                    "dia": "el nuevo día del mes (1-31)", "fecha": "la nueva fecha (ej. 20/11)",
                    "nombre": "el nuevo nombre"}[partes[2]]
        await b.mostrar(update, context, f"✏️ Escribe {pregunta}:", [b.CANCELAR], nuevo=True)
        return None
    if clave == "dbo":
        deuda = deudas.obtener(int(partes[1]))
        await b.mostrar(update, context, f"🗑️ ¿Borrar «{analisis.e(deuda['nombre'])}»?",
                        [[("Sí, borrar", f"dbos:{deuda['id']}"), ("No", f"d:ver:{deuda['id']}")]])
        return None
    if clave == "dbos":
        accion = deudas.borrar(int(partes[1]))
        await b.mostrar(update, context, "🗑️ Borrada.", b.con_deshacer(accion, [[("💳 Ver deudas", "m:deudas")]]))
        return None

    # --- Análisis de deudas
    if clave == "ad":
        volver = [[("📅 Próximos 30 días", "ad:cal"), ("📉 Gráfico", "ad:gra")], [("⬅️ Análisis", "m:analisis")]]
        if partes[1] == "res":
            await b.mostrar(update, context, analisis_deudas.texto_analisis(), volver, nuevo=True)
        elif partes[1] == "cal":
            await b.mostrar(update, context, analisis_deudas.texto_calendario(), volver)
        elif partes[1] == "gra":
            serie = analisis_deudas.proyeccion()
            marcado = b.teclado(volver)
            if len(serie) >= 2:
                imagen = await asyncio.to_thread(graficos.barras_meses, analisis_deudas.etiquetas_meses(serie),
                                                 [v for _, v in serie], "Lo que debes al final de cada mes")
                fin = serie[-1][0]
                await context.bot.send_photo(b.estado["chat_id"], photo=imagen, reply_markup=marcado,
                                             caption=f"📉 Si pagas tus cuotas, a final de {analisis_deudas.mes_anio(fin)} "
                                                     "habrás terminado tus deudas.")
            else:
                await context.bot.send_message(b.estado["chat_id"], "📉 No tienes deudas pendientes que proyectar 🎉",
                                               reply_markup=marcado)
        return None
    return None
