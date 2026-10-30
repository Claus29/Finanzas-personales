"""Pantallas sencillas (v13): solo lo esencial, en el orden 1️⃣ pagos → 2️⃣ tu libre → 3️⃣ metas.

Cada función devuelve (texto HTML, filas de botones). Los números salen de resumen.py; los datos avanzados
siguen en «📊 Más datos» (las pantallas de antes, sin cambios). Nada de aquí consulta al banco.
"""
import html
from datetime import date, timedelta

import analisis
import ciclo
import config
import consultas
import deudas
import metas
import proyeccion as pr
import reparto
import resumen
from formato import MESES, MESES_CORTOS, barra, euros, euros_cortos, fecha_corta

RAYA = "━━━━━━━━━━━━━━━━"


def e(texto):
    return html.escape(str(texto))


def mes(d):
    return f"{MESES_CORTOS[d.month - 1]} {d.year}"


def cuando(item):
    """«26 oct», «26 oct ⚠️» (sin marcar) o «con el cobro» de un pago pendiente."""
    deuda = item["deuda"]
    if len(item["periodo"]) == 10 or deuda["tipo"] == "cobro" or deudas.al_cobro_desde(deuda["id"], item["periodo"]):
        texto = "con el cobro" if not item["atrasada"] else f"del cobro del {fecha_corta(item['vence'])}"
    else:
        texto = fecha_corta(item["vence"])
    return texto + (" ⚠️" if item["atrasada"] else "")


def numero_cuota(deuda, despues=0):
    if deuda["tipo"] != "plazos":
        return ""
    numero, total = deudas.numero_cuota(deuda)
    return f" ({numero + despues}/{total})"


def lista_pagos(items, maximo=8):
    lineas = [f"   • {e(i['deuda']['nombre'])} — {euros(i['importe'])}{numero_cuota(i['deuda'])} · {cuando(i)}"
              for i in items[:maximo]]
    if len(items) > maximo:
        lineas.append(f"   • … y {len(items) - maximo} más")
    return lineas


def lista_con_cobro(con_cobro, antes, maximo=8):
    lineas = []
    for d, importe in con_cobro[:maximo]:
        despues = len([i for i in antes if i["deuda"]["id"] == d["id"]])
        tipo = " · fijo" if resumen.es_fijo(d) else ""
        lineas.append(f"   • {e(d['nombre'])} — {euros(importe)}{numero_cuota(d, despues)}{tipo}")
    if len(con_cobro) > maximo:
        lineas.append(f"   • … y {len(con_cobro) - maximo} más")
    return lineas


# =====================================================================
# 🏠 Inicio
# =====================================================================

def inicio():
    a = resumen.ahora()
    if not a:
        return ("🏠 <b>Tu dinero hoy</b>\n\nAún no tengo tus saldos: se descargan en la actualización diaria "
                f"({config.valor('HORA_SALDO_DIARIO')}). También puedes forzarla en ☰ Más › 🔄 Actualizar ahora.",
                [[("☰ Más", "v:mas")]])
    hoy = config.ahora().date()
    dias = a["dias"]
    lineas = [f"🏠 <b>Tu dinero hoy</b> · {fecha_corta(hoy)}",
              f"<i>Cobras ~{fecha_corta(a['proximo'])} (en {dias} día{'s' if dias != 1 else ''}) · "
              f"{analisis.texto_actualizado().lower()}</i>", "",
              f"💰 En el banco: <b>{euros(a['banco'])}</b>"]
    if a["pagos"]:
        lineas.append(f"1️⃣ Pagos antes del cobro: <b>−{euros(a['total_pagos'])}</b>")
        lineas += lista_pagos(a["pagos"], 5)
    else:
        lineas.append("1️⃣ Pagos antes del cobro: <b>ninguno</b> ✅")
    if a["en_metas"] > 0.004:
        lineas.append(f"🎯 Ya guardado en tus metas: −{euros(a['en_metas'])}")
    if a["a_mover"] > 0.004:
        lineas.append(f"3️⃣ Por mover a metas este ciclo: −{euros(a['a_mover'])}")
    lineas.append(RAYA)
    libre, minimo = a["libre"], a["libre_minimo"]
    icono = "🔴" if libre < -0.004 else ("🟡" if libre < minimo - 0.004 else "🟢")
    lineas.append(f"2️⃣ <b>Tu libre: {euros(libre)}</b> {icono}")
    if libre < -0.004:
        lineas.append(f"   Te faltan <b>{euros(-libre)}</b> para llegar al cobro.")
    elif libre < minimo - 0.004:
        lineas.append(f"   Por debajo de los {euros_cortos(minimo)} que quieres tener.")
    if a["deben"] > 0.004:
        lineas.append(f"   🤝 Si te pagan los {euros_cortos(a['deben'])} que te deben: {euros(libre + a['deben'])}")
    if a["recortado"] > 0.004:
        lineas.append(f"\n3️⃣ Metas: {euros(a['recortado'])} de este ciclo <b>no se mueven</b> por ahora: "
                      "tus pagos y tu libre van primero.")
    if a["con_cobro"]:
        total = sum(i for _, i in a["con_cobro"])
        lineas.append(f"\n💶 Con el cobro del {fecha_corta(a['proximo'])} pagarás <b>{euros(total)}</b> "
                      f"({len(a['con_cobro'])} pago{'s' if len(a['con_cobro']) != 1 else ''}).")
    filas = []
    if a["pagos"]:
        filas.append([("✅ / 💶 Pagos de antes del cobro", "v:pagos")])
    if a["a_mover"] > 0.004:
        filas.append([("🎯 Marcar dinero movido", "mt:lista")])
    if ciclo.cobro_esperado_hoy():
        filas.append([("💶 Registrar cobro", "cobro:nuevo")])
    filas.append([("📊 Gráfico", "v:g:inicio"), ("📊 Más datos", "v:datos")])
    return "\n".join(lineas), filas


def pagos():
    """Lista de los pagos de antes del cobro, cada uno con ✅ (ya pagado) y 💶 (con el cobro)."""
    items = deudas.pendientes()
    if not items:
        return "✅ No tienes pagos pendientes antes del cobro.", [[("⬅️ Inicio", "v:inicio")]]
    lineas = [f"1️⃣ <b>Pagos antes del cobro: {euros(sum(i['importe'] for i in items))}</b>", ""]
    lineas += lista_pagos(items, 12)
    lineas += ["", "<i>✅ si ya lo pagaste · 💶 si lo pagas con el cobro (deja de restarse ahora). "
                   "Nada se da por pagado.</i>"]
    filas = [[(f"✅ {i['deuda']['nombre'][:16]}", f"dp:{i['deuda']['id']}:{i['periodo']}"),
              ("💶 Con el cobro", f"dcb:{i['deuda']['id']}:{i['periodo']}")] for i in items[:8]]
    return "\n".join(lineas), filas + [[("⬅️ Inicio", "v:inicio")]]


# =====================================================================
# 💳 Deudas
# =====================================================================

def deudas_pantalla():
    d = resumen.de_deudas()
    if not d["filas"] and not d["fijos"] and not d["deben_total"]:
        return ("💳 <b>Deudas</b>\n\nNo tienes nada apuntado. Pulsa «➕ Apuntar» para tus deudas, cuotas, gastos fijos, "
                "suscripciones o lo que te deben.", [[("➕ Apuntar", "d:nueva")]])
    lineas = [f"💳 <b>Lo que debes: {euros(d['total'])}</b>"]
    if d["fin"]:
        lineas.append(f"🏁 Terminas de pagar: <b>{MESES[d['fin'].month - 1]} {d['fin'].year}</b>")
    lineas.append("")
    if d["antes"]:
        lineas.append(f"1️⃣ <b>Antes del cobro ({fecha_corta(d['proximo'])}): "
                      f"{euros(sum(i['importe'] for i in d['antes']))}</b>")
        lineas += lista_pagos(d["antes"])
    else:
        lineas.append(f"1️⃣ Antes del cobro ({fecha_corta(d['proximo'])}): <b>nada</b> ✅")
    if d["con_cobro"]:
        lineas.append(f"💶 <b>Con el cobro del {fecha_corta(d['proximo'])}: "
                      f"{euros(sum(i for _, i in d['con_cobro']))}</b>")
        lineas += lista_con_cobro(d["con_cobro"], d["antes"])
    if d["filas"]:
        lineas += ["", "📋 <b>Tus deudas</b>"]
        for f in d["filas"]:
            deuda = f["deuda"]
            if deuda["tipo"] == "plazos":
                detalle = f"quedan {euros(f['queda'])} · {f['cuotas']} cuota{'s' if f['cuotas'] != 1 else ''}"
            elif deuda["tipo"] == "cobro":
                detalle = f"{euros(f['queda'])} · con el cobro"
            else:
                detalle = f"{euros(f['queda'])} · {fecha_corta(f['fin'])}" if f["fin"] else euros(f["queda"])
            fin = f" · hasta {mes(f['fin'])}" if f["fin"] and deuda["tipo"] == "plazos" else ""
            lineas.append(f"   • {e(deuda['nombre'])} — {detalle}{fin}")
    if d["fijos"]:
        nombres = ", ".join(e(x["nombre"]) for x in d["fijos"][:4]) + ("…" if len(d["fijos"]) > 4 else "")
        lineas.append(f"\n🔁 Fijos y suscripciones: <b>{euros(d['fijos_mes'])}</b> al mes <i>({nombres})</i>")
    if d["deben_total"] > 0.004:
        este = f" ({euros_cortos(d['deben_ciclo'])} este ciclo)" if d["deben_ciclo"] > 0.004 else ""
        lineas.append(f"🤝 Te deben <b>{euros(d['deben_total'])}</b>{este} · no cuenta hasta que te paguen")
    filas = [[("➕ Apuntar", "d:nueva"), ("✅ Marcar pagado", "d:pagar")]]
    lista = deudas.activas()
    for n in range(0, len(lista), 2):
        filas.append([(f"{'🤝' if deudas.me_deben(x) else deudas.TIPOS[x['tipo']].split(' ')[0]} {x['nombre'][:18]}",
                       f"d:ver:{x['id']}") for x in lista[n:n + 2]])
    filas.append([("📊 Gráfico", "v:g:deudas"), ("📊 Detalles", "ad:res")])
    return "\n".join(lineas), filas


def ficha_deuda(deuda):
    """Ficha corta: lo que queda, la próxima, cuándo terminas y si resta ahora de tu saldo."""
    te_deben = deudas.me_deben(deuda)
    tipo = deudas.TIPOS[deuda["tipo"]]
    icono, nombre_tipo = tipo.split(" ", 1)
    lineas = [f"{'🤝' if te_deben else icono} <b>{e(deuda['nombre'])}</b> · "
              f"{'te debe' if te_deben else nombre_tipo.lower()}"]
    proximo = deudas.proximo_pago(deuda)
    if deuda["tipo"] == "plazos":
        queda, cuotas = deudas.restante(deuda)
        lineas.append(f"Quedan <b>{euros(queda)}</b> de {euros(deuda['importe'])} · "
                      f"{cuotas} cuota{'s' if cuotas != 1 else ''} de {euros_cortos(deuda['cuota'])}")
    elif resumen.es_fijo(deuda):
        lineas.append(f"<b>{euros(deuda['importe'])}</b> · {analisis.cuando_se_paga(deuda)}")
    else:
        lineas.append(f"<b>{euros(deuda['importe'])}</b> · {analisis.cuando_se_paga(deuda)}")
    if proximo:
        if proximo[1] is None or (proximo[1] and deudas.al_cobro_desde(deuda["id"], proximo[1])):
            fecha = f"con tu cobro (~{fecha_corta(proximo[0])})"
        else:
            fecha = fecha_corta(proximo[0])
        lineas.append(f"Próximo {'cobro' if te_deben else 'pago'}: <b>{euros(proximo[2])}</b> · {fecha}"
                      + numero_cuota(deuda))
    fin = resumen.fin_de_deuda(deuda)
    if fin and deuda["tipo"] == "plazos":
        lineas.append(f"🏁 Terminas: {MESES[fin.month - 1]} {fin.year}")
    if not te_deben and deuda["tipo"] != "sin_fecha":
        lineas.append(analisis.texto_en_neto(deuda))
    return "\n".join(lineas)


# =====================================================================
# 🎯 Metas
# =====================================================================

def estado_llegada(llega, limite, especial=False):
    if llega is None:
        return "🔴 con lo que sobra no llega"
    if especial:
        return f"llegas {mes(llega)}"
    if llega <= limite:
        return f"✅ llegas {mes(llega)}"
    return f"⚠️ llegas {mes(llega)} (tu fecha: {mes(limite)})"


def metas_pantalla():
    m = resumen.de_metas()
    if not m["filas"]:
        texto = ("🎯 <b>Tus metas</b>\n\nAún no tienes metas. Reciben lo que sobra de cada cobro después de tus pagos "
                 "y tu libre. Crea una con «➕ Nueva» (por ejemplo «Viaje: 1.200 € para junio»).")
        return texto, [[("➕ Nueva", "g:nueva")]]
    minimo = m["libre_minimo"]
    lineas = ["🎯 <b>Tus metas</b>",
              f"<i>Reciben lo que sobra después de tus pagos y tu libre ({euros_cortos(minimo)}), "
              "en este orden:</i>", ""]
    nombres = {c["uid"]: consultas.nombre_cuenta(c) for c in consultas.cuentas()}
    for n, f in enumerate(m["filas"], 1):
        meta = f["meta"]
        icono = "🛟" if meta["especial"] == "colchon" else ""
        lineas.append(f"{n}. {icono}<b>{e(meta['nombre'])}</b> · {euros_cortos(f['ahorrado'])} / "
                      f"{euros_cortos(f['objetivo'])} ({f['fraccion']:.0%})".replace("%", " %"))
        lineas.append(f"   {barra(f['fraccion'], 10)} {estado_llegada(f['llega'], f['limite'], bool(meta['especial']))}")
    lineas += ["", "<b>Este ciclo</b>"]
    pendientes = [f for f in m["filas"] if f["plan"] > 0.004]
    hechas = [f for f in m["filas"] if f["hecho"] is not None or f["saltado"]]
    for f in pendientes:
        meta = f["meta"]
        destino = f" a «{e(nombres.get(meta['uid'], 'su cuenta'))}»" if meta["uid"] else ""
        if f["mover"] >= f["plan"] - 0.004:
            lineas.append(f"   → {e(meta['nombre'])}: mueve <b>{euros(f['plan'])}</b>{destino}")
        elif f["mover"] > 0.004:
            lineas.append(f"   → {e(meta['nombre'])}: mueve <b>{euros(f['mover'])}</b>{destino} "
                          f"<i>(eran {euros_cortos(f['plan'])}: no hay más sin tocar tu libre)</i>")
        else:
            lineas.append(f"   ⏸️ {e(meta['nombre'])}: {euros(f['plan'])} pendientes, <b>ahora no hay dinero</b> "
                          "(tus pagos y tu libre van primero)")
    for f in hechas:
        texto = "⏭️ este mes no" if f["saltado"] else f"✅ {euros(f['hecho'])} movidos"
        lineas.append(f"   {e(f['meta']['nombre'])}: {texto}")
    if not pendientes and not hechas:
        fijado = reparto.del_ciclo(ciclo.inicio().isoformat()) if m["reparto"] else None
        if fijado and fijado["a_metas"] <= 0.004:
            lineas.append("   Este ciclo no sobra nada para metas: tus pagos y tu libre van primero.")
        else:
            lineas.append("   Nada que mover ahora: lo de cada meta se calcula al registrar el cobro.")
    if m["conseguidas"]:
        lineas.append("\n🏆 Conseguidas: " + ", ".join(e(x["nombre"]) for x in m["conseguidas"]))
    filas = [[("➕ Nueva", "g:nueva"), ("⚖️ Prioridades", "pr:aju")]]
    if pendientes:
        filas.append([("🎯 Marcar dinero movido", "mt:lista")])
    filas += [[(f"{'🛟' if f['meta']['especial'] == 'colchon' else '🎯'} {f['meta']['nombre'][:20]}",
                f"g:ver:{f['meta']['id']}")] for f in m["filas"]]
    filas.append([("📊 Gráfico", "v:g:metas"), ("📊 Detalles", "pr:met")])
    return "\n".join(lineas), filas


def ficha_meta(meta):
    """Ficha corta de una meta: progreso, cuándo llegas y lo de este ciclo."""
    p = metas.progreso(meta)
    prox = resumen.proximos()
    llega = prox["llegadas"].get(meta["id"]) if prox else None
    orden = [m["id"] for m in reparto.orden(metas.activas())]
    puesto = f" · prioridad {orden.index(meta['id']) + 1}" if meta["id"] in orden else ""
    icono = "🛟" if meta["especial"] == "colchon" else "🎯"
    lineas = [f"{icono} <b>{e(meta['nombre'])}</b>{puesto}",
              f"{barra(p['fraccion'], 12)} {p['fraccion']:.0%}".replace("%", " %"),
              f"<b>{euros(p['ahorrado'])}</b> de {euros(p['objetivo'])} · faltan {euros(p['falta'])}"]
    if p["falta"] > 0.004:
        if meta["especial"] == "colchon":
            lineas.append(estado_llegada(llega, p["limite"], True).capitalize())
        else:
            lineas.append(f"Tu fecha: {mes(p['limite'])} · {estado_llegada(llega, p['limite'])}")
    espera = metas.en_espera(meta)
    if espera:  # sin reparto automático: aporta la cuota reducida de un tramo mientras otra meta va primero
        lineas.append(f"⏸️ Ahora: aporta menos {espera} (otra meta va primero)")
    fila = metas.estado_ciclo(meta)
    pendiente = metas.pendiente_ciclo(meta)
    if fila:
        lineas.append("Este ciclo: " + ("⏭️ este mes no" if fila["estado"] == "saltado" else
                                        f"✅ {euros(fila['importe'])} movidos"))
    elif pendiente > 0.004:
        a = resumen.ahora()
        parte = next((x for m, _, x in (a["metas"] if a else []) if m["id"] == meta["id"]), pendiente)
        if parte >= pendiente - 0.004:
            lineas.append(f"Este ciclo: mueve <b>{euros(pendiente)}</b>")
        else:
            lineas.append(f"Este ciclo: tocaban {euros(pendiente)}, pero ahora solo hay <b>{euros(parte)}</b> "
                          "sin tocar tu libre")
    return "\n".join(lineas)


# =====================================================================
# 📈 Próximos meses
# =====================================================================

def entero(v):
    return f"{round(v):,}".replace(",", ".").replace("-", "−")


def proximos_pantalla():
    prox = resumen.proximos()
    if not prox:
        return ("📈 <b>Próximos meses</b>\n\nPara calcularlo necesito tu salario: regístralo cuando cobres "
                "(☰ Más › 💶 Registrar cobro) o escribe uno estimado.", [[("💶 Escribir salario estimado", "pr:sal")]])
    icono, veredicto = resumen.veredicto(prox)
    filas_t = prox["filas"]
    cabecera = f"{'Cobro':<7}{'Entra':>6}{'Deuda':>6}{'Fijos':>6}{'Libre':>6}{'Metas':>6}"
    tabla = [cabecera, "─" * len(cabecera)]
    for f in filas_t:
        marca = " !" if f["estado"] == "🔴" else (" ·" if f["libre"] < prox["minimo"] - 0.5 else "")
        if not marca and prox["reparto"] and f["libre"] > prox["minimo"] + 0.5:
            marca = " +"  # tus metas ya están completas: lo que sobra queda libre
        tabla.append(f"{pr.mes_corto(f['fecha']):<7}{entero(f['entra']):>6}{entero(-f['deudas']):>6}"
                     f"{entero(-f['fijos']):>6}{entero(f['libre']):>6}{entero(f['metas']):>6}{marca}")
    lineas = [f"📈 <b>Próximos meses</b> · salario {euros(prox['salario'])} <i>({prox['origen']})</i>",
              f"{icono} <b>{veredicto[0].upper() + veredicto[1:]}.</b>", "",
              f"<pre>{chr(10).join(tabla)}</pre>"]
    notas = ["1️⃣ Deuda y fijos se pagan primero · 2️⃣ Libre = tu libre · 3️⃣ Metas = lo que sobra"]
    if prox["hueco"] > 0.004:
        notas.append(f"El cobro de {pr.mes_corto(filas_t[0]['fecha'])} cubre antes los {euros_cortos(prox['hueco'])} "
                     "que te faltan hasta el cobro")
    if any(" !" in t for t in tabla):
        notas.append("! no llega")
    if any(t.endswith(" +") for t in tabla):
        notas.append("+ más libre: tus metas ya están completas")
    lineas.append("<i>" + " · ".join(notas) + "</i>")
    lineas.append("")
    if prox["fin_deudas"]:
        lineas.append(f"🏁 Sin deudas: <b>{MESES[prox['fin_deudas'].month - 1]} {prox['fin_deudas'].year}</b>")
    llegadas = []
    for m in reparto.orden(metas.activas()):
        llega = prox["llegadas"].get(m["id"])
        limite = date.fromisoformat(m["fecha_limite"])
        if m["especial"] == "colchon":
            llegadas.append(f"{e(m['nombre'])}: {mes(llega) if llega else 'no llega'}")
        else:
            marca = "✅" if llega and llega <= limite else ("⚠️" if llega else "🔴")
            llegadas.append(f"{e(m['nombre'])}: {mes(llega) if llega else 'no llega'} {marca}")
    if llegadas:
        lineas.append("🎯 " + " · ".join(llegadas))
    if prox["deben_total"] > 0.004:
        lineas.append(f"🤝 Si te pagan lo que te deben (+{euros(prox['deben_total'])} en estos meses), irá a tus metas: "
                      "no está sumado arriba.")
    filas = [[("📊 Gráfico", "v:g:prox")]]
    if icono != "🟢":
        filas.append([("⚖️ Ver soluciones", "pr:aju")])
    filas.append([(f"💸 Tu libre: {euros_cortos(prox['minimo'])}", "pr:lib"), ("📅 Hasta…", "pr:hz")])
    filas.append([("📊 Más detalles", "pr:res")])
    return "\n".join(lineas), filas


# =====================================================================
# ☰ Más y 📊 Más datos
# =====================================================================

def mas():
    texto = ("☰ <b>Más</b>\nRecordatorios, ajustes y todos los datos avanzados.")
    filas = [[("⏰ Recordatorios", "m:rec"), ("⚙️ Ajustes", "m:ajustes")],
             [("📊 Más datos", "v:datos")],
             [("💶 Registrar cobro", "cobro:nuevo"), ("🧾 Movimientos", "m:movs")],
             [("📤 Exportar a Excel", "aj:exp"), ("🔄 Actualizar ahora", "aj:act")]]
    return texto, filas


def mas_datos():
    texto = ("📊 <b>Más datos</b>\nTodo lo avanzado de antes, con sus gráficos y explicaciones.")
    filas = [[("💰 Saldo por cuenta y saldo neto", "m:saldo")],
             [("🧭 Análisis completo", "ac:menu")],
             [("📊 Análisis del ciclo, presupuesto y categorías", "m:analisis")],
             [("📈 Proyección detallada", "pr:res")],
             [("💳 Análisis de deudas", "ad:res")],
             [("⬅️ Inicio", "v:inicio")]]
    return texto, filas


# =====================================================================
# 💶 ¡Cobrado! en tres pasos
# =====================================================================

def texto_cobrado(importe=None):
    """Plan del cobro: 1️⃣ pagos → 2️⃣ tu libre → 3️⃣ metas (lo que sobra). Nada se da por pagado ni movido."""
    p = analisis.plan_cobro(importe)
    r = reparto.del_ciclo(p["fecha"].isoformat()) if reparto.activo() else None
    nombres = {c["uid"]: consultas.nombre_cuenta(c) for c in consultas.cuentas()}
    pagos_ = p["atrasado"] + p["cuotas"] + p["fijos"]
    total_pagos = round(sum(i["importe"] for i in pagos_), 2)
    hueco = r["hueco"] if r else 0.0
    minimo = pr.libre_minimo()
    aportes = list(p["aportes"])
    if not r:  # sin reparto: las metas solo reciben lo que supere tu libre (v13: ceden primero)
        puedes = max(0.0, p["importe"] - total_pagos - minimo)
        orden = {m["id"]: n for n, m in enumerate(reparto.orden(metas.activas()))}
        recortados = []
        for meta, importe_meta in sorted(aportes, key=lambda x: orden.get(x[0]["id"], len(orden))):
            parte = round(min(importe_meta, puedes), 2)
            puedes -= parte
            recortados.append((meta, parte))
        aportes = [(m, x) for m, x in recortados if x > 0.004]
    a_metas = round(sum(x for _, x in aportes), 2)
    libre = round(p["importe"] - total_pagos - hueco - a_metas, 2)
    lineas = [f"💶 <b>¡Cobrado! {euros(p['importe'])}</b> · ciclo hasta el "
              f"{fecha_corta(ciclo.proximo_cobro() - timedelta(days=1))}", ""]
    lineas.append(f"1️⃣ <b>Pagos: −{euros(total_pagos + hueco)}</b>")
    lineas += lista_pagos(pagos_, 10)
    if hueco > 0.004:
        lineas.append(f"   • Lo que te faltaba antes del cobro — {euros(hueco)}")
    icono = "🔴" if libre < -0.004 else ("🟡" if libre < minimo - 0.004 else "")
    lineas.append(f"2️⃣ <b>Tu libre: {euros(libre)}</b> {icono}".rstrip())
    if libre < -0.004:
        lineas.append(f"   No llega: te faltan {euros(-libre)}. Puedes pasar un pago al siguiente cobro (💶) "
                      "o pagar otra cantidad (💸).")
    if aportes:
        lineas.append(f"3️⃣ <b>Metas: {euros(a_metas)}</b>")
        for meta, x in aportes:
            destino = f" a «{e(nombres.get(meta['uid'], 'su cuenta'))}»" if meta["uid"] else " (apártalo)"
            lineas.append(f"   → {e(meta['nombre'])} {euros(x)}{destino}")
    elif metas.activas():
        lineas.append("3️⃣ Metas: <b>0 €</b> este ciclo (no sobra nada después de pagos y tu libre)")
    elif r and r["sobra"] > 0.004:
        lineas.append(f"3️⃣ No tienes metas: los {euros(r['sobra'])} que sobran quedan libres. ¿Creamos una?")
    if p["cobrar"]:
        lineas.append(f"\n🤝 Si te pagan los {euros(sum(i['importe'] for i in p['cobrar']))} que te deben, "
                      "irán a tus metas.")
    try:  # una línea con la conclusión de 📈 Próximos meses (nunca impide enviar el plan)
        prox = resumen.proximos()
        if prox:
            icono_, veredicto = resumen.veredicto(prox)
            lineas.append(f"\n📈 Próximos meses: {icono_} {veredicto}.")
    except Exception:
        import logging
        logging.getLogger("detalle").exception("No se pudo calcular la conclusión de próximos meses")
    (h1, m1), (h2, m2) = config.franja_deudas()
    lineas.append(f"\n<i>Nada se da por hecho: marca lo que pagues y muevas. Lo demás te lo recuerdo cada día entre "
                  f"las {h1:02d}:{m1:02d} y las {h2:02d}:{m2:02d}.</i>")
    return "\n".join(lineas)
