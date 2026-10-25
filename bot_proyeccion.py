"""Interfaz de Telegram de 📈 Proyección (botón del teclado).

Pantallas (botones «pr:»): resumen, mes a mes, calendario, metas, ajustar y ¿y si…?; hasta qué mes
(PROYECCION_HASTA) y salario estimado (SALARIO_ESTIMADO). Propuestas para que sea sostenible:
«prp:X» las enseña, «pra:X» las aplica (con deshacer) y «pri» las ignora. Simulador por meta: «prs:».
«prq:ID» prioriza una meta; «pro:» elige varias prioritarias en orden. Libre mínimo por cobro: «pr:lib».
Pasos escritos: «proy_hasta», «proy_salario» y «proy_libre». Nunca consulta al banco.
"""
import asyncio
from datetime import date

import analisis
import config
import datos
import deudas
import graficos_oscuro as go
import metas
import proyeccion as pr
import reparto
from formato import euros, euros_cortos, fecha_corta, leer_importe, leer_mes, sumar_meses

PREFIJOS = {"pr", "prp", "pra", "pri", "prs", "prq", "pro"}
PASO = 20  # € que suma o resta el simulador por meta


def _b():
    import bot
    return bot


def e(texto):
    return analisis.e(texto)


def hoy():
    return config.ahora().date()


def entero(v):
    """Euros enteros para las tablas («1.234», «−56»)."""
    texto = f"{abs(round(v)):,}".replace(",", ".")
    return ("−" if v < -0.5 else "") + texto


def pie(p):
    return f"Salario {go.euros(p['salario'])} ({p['origen']}) · proyección del {fecha_corta(hoy())} {hoy().year} · Bot Finanzas"


def botones_menu(actual="res"):
    nombres = [("res", "📌 Resumen"), ("mes", "📅 Mes a mes"), ("cal", "🗓️ Calendario"), ("met", "🎯 Metas"),
               ("aju", "⚖️ Ajustar"), ("esc", "🧪 ¿Y si…?")]
    opciones = [(t, f"pr:{c}") for c, t in nombres if c != actual]
    filas = [opciones[i:i + 3] for i in range(0, len(opciones), 3)]
    filas.append([(f"📆 Hasta: {pr.aviso_horizonte()}", "pr:hz"), ("💶 Salario", "pr:sal"),
                  (f"💸 Libre: {euros_cortos(pr.libre_minimo())}", "pr:lib")])
    filas.append([(f"🔀 Reparto automático: {'sí' if reparto.activo() else 'no'}", "pr:rep")])
    return filas


def rango_metas(p, meta_id):
    """(mínimo, máximo, media) de lo que recibe una meta en los cobros en que aún le falta."""
    valores = [c["por_meta"].get(meta_id, (0.0, False))[0] for c in p["ciclos"]]
    con_dinero = [v for v in valores if v > 0.004]
    if not con_dinero:
        return 0.0, 0.0, 0.0
    return min(con_dinero), max(con_dinero), sum(con_dinero) / len(con_dinero)


def texto_rango(minimo, maximo):
    return euros_cortos(round(minimo)) if abs(maximo - minimo) < 1 else f"de {euros_cortos(round(minimo))} a {euros_cortos(round(maximo))}"


def botones_prioridad(p, maximo=4):
    """Un botón «🥇 Nombre» por meta sin conseguir (prioriza esa y las demás esperan)."""
    lista = [m for m in p["metas"] if m["id"] in pr.aportes_primer_cobro(p)][:maximo]
    botones = [(f"🥇 {m['nombre'][:16]}", f"prq:{m['id']}") for m in lista]
    return [botones[i:i + 2] for i in range(0, len(botones), 2)]


def sin_salario():
    return ("📈 <b>Proyección</b>\n\nPara proyectar necesito tu salario: regístralo cuando cobres "
            "(💰 Saldo › 💶 Registrar cobro) o escribe uno estimado.", [], [[("💶 Escribir salario estimado", "pr:sal")]])


def texto_antes_del_cobro():
    """«Antes de tu cobro tienes que pagar …»: los pagos de este ciclo que restan de tu saldo neto."""
    items = deudas.pendientes()
    if not items:
        return None
    detalle = ", ".join(f"{e(i['deuda']['nombre'])} {euros_cortos(i['importe'])}" for i in items)
    return f"🧾 Antes del cobro tienes que pagar {euros(sum(i['importe'] for i in items))}: <i>{detalle[:120]}</i>"


def lineas_cobro(c, p=None):
    t = c["totales"]
    lineas = [f"💶 Entra {euros(c['salario'])}" + (f" + te devuelven {euros(t['deben'])}" if t["deben"] else "")]
    if c.get("hueco"):
        lineas.append(f"🧾 Primero cubre lo que te faltaba para los pagos de antes del cobro: {euros(c['hueco'])} "
                      "<i>(se queda en tu cuenta para pagarlos)</i>")
    for clave, icono, nombre in (("fijos", "🏠", "Gastos fijos"), ("subs", "📺", "Suscripciones"),
                                 ("cuotas", "💳", "Cuotas de deudas"), ("unicos", "🧾", "Pagos únicos")):
        if t[clave]:
            detalle = ", ".join(f"{e(d['nombre'])} {euros_cortos(i)}" for d, i, cl in c["items"] if cl == clave)
            lineas.append(f"{icono} {nombre}: −{euros(t[clave])}  <i>{detalle[:90]}</i>")
    if t["metas"]:
        detalle = ", ".join(f"{e(m['nombre'])} {euros_cortos(i)}" for m, i, _ in c["aportes"])
        lineas.append(f"🎯 Metas: −{euros(t['metas'])}  <i>{detalle[:90]}</i>")
    dias = (c["fin"] - c["fecha"]).days
    if p and p["reparto"]:
        # Tu libre siempre aparte; lo que sobra (solo si ya no quedan metas por completar) en otra línea.
        tuyo = round(c["libre"] - c.get("hueco", 0.0), 2)
        extra = round(tuyo - p["minimo"], 2)
        if extra > 0.5:
            lineas.append(f"= <b>💸 Tu libre: {euros(p['minimo'])}</b>")
            lineas.append(f"➕ <b>Te sobran {euros(extra)} más</b>: tus metas ya están completas, así que no van a metas")
        else:
            lineas.append(f"= <b>{'💸' if tuyo >= 0 else '🔴'} Tu libre: {euros(tuyo)}</b>"
                          + (f" <i>(querías {euros(p['minimo'])})</i>" if extra < -0.5 else ""))
        return lineas
    lineas.append(f"= <b>{'💸' if c['libre'] >= 0 else '🔴'} Libre: {euros(c['libre'])}</b>"
                  + (f"  (≈ {euros_cortos(c['por_dia'])}/día durante {dias} días)" if c["libre"] > 0 else ""))
    return lineas


# =====================================================================
# Pantallas (se calculan en un hilo: devuelven texto, imágenes y botones)
# =====================================================================

def resumen():
    p = pr.simular()
    if not p:
        return sin_salario()
    ciclos = p["ciclos"]
    icono, veredicto = pr.veredicto(p)
    primero = ciclos[0]
    lineas = [f"📈 <b>Proyección</b> · {len(ciclos)} cobros, hasta {pr.mes_largo(ciclos[-1]['fecha'])}",
              f"💶 Salario: <b>{euros(p['salario'])}</b> <i>({p['origen']})</i>",
              (f"🔀 <b>Reparto automático</b>: tu libre es <b>{euros(p['minimo'])}</b> en cada cobro y todo lo demás va a "
               f"tus metas <i>({reparto.MODOS[reparto.modo()][2:].lower()})</i>" if p["reparto"] else
               f"💸 Libre que quieres en cada cobro: <b>{euros(p['minimo'])}</b>"
               + (" <i>(todo el salario a pagos y metas)</i>" if not p["minimo"] else "")), "",
              f"{icono} <b>{veredicto}</b>", "",
              f"<b>Hasta el próximo cobro ({fecha_corta(primero['fecha'])})</b>",
              *([texto_antes_del_cobro()] if texto_antes_del_cobro() else []),
              f"💰 Dinero libre hoy (ya descontado): {euros(p['libre_hoy'])}"
              + (f" + te deben {euros(p['deben_hoy'])} este ciclo" if p["deben_hoy"] else ""),
              f"= Llegas al cobro con <b>{euros(p['puente'])}</b> libres", "",
              f"<b>Próximo cobro · {fecha_corta(primero['fecha'])}</b>"]
    lineas += lineas_cobro(primero, p)
    libre_total = sum(c["libre"] for c in ciclos)
    pagos = sum(c["pagos"] for c in ciclos)
    a_metas = sum(c["totales"]["metas"] for c in ciclos)
    devuelven = sum(c["totales"]["deben"] for c in ciclos)
    comprometido = (primero["pagos"] + primero["totales"]["metas"]) / primero["salario"] if primero["salario"] else 0
    lineas += ["", f"📊 <b>En {len(ciclos)} cobros</b>",
               f"• Libre en total: <b>{euros(libre_total)}</b> · de media {euros(libre_total / len(ciclos))} por cobro",
               f"• Cobro más justo: {pr.mes_largo(p['peor']['fecha'])} ({euros(p['peor']['libre'])})",
               f"• Acabas con <b>{euros(p['final'])}</b> libres"
               + (f" y {euros(ciclos[-1]['en_metas'])} en tus metas" if ciclos[-1]["en_metas"] else ""),
               f"• Pagarás {euros(pagos)} en fijos, suscripciones y deudas, y apartarás {euros(a_metas)} para metas"]
    if devuelven:
        lineas.append(f"• Te devolverán {euros(devuelven)} (cuenta en la proyección)")
    lineas.append(f"• Comprometido en el próximo cobro: {comprometido:.0%} del salario (pagos + metas)".replace("%", " %"))
    if p["reparto"]:
        a_cada = [c["totales"]["metas"] for c in ciclos if c["totales"]["metas"] > 0.004]
        if a_cada:
            lineas.append(f"• A tus metas va {texto_rango(min(a_cada), max(a_cada))} por cobro (lo que sobra cada mes)")
    else:
        lineas.append(f"• Para metas puedes destinar hasta <b>{euros(p['maximo_metas'])}</b> por cobro dejando tu libre "
                      f"mínimo (ahora apartas {euros(primero['totales']['metas'])})")
    fines = pr.fin_metas()
    if any(not x["especial"] and fines.get(x["id"]) is None for x in p["metas"]):
        lineas.append("• ⚠️ Alguna meta no llega nunca con la aportación actual: mira 🎯 Metas")
    filas = botones_menu("res")
    if deudas.pendientes():
        filas = [[("🧾 Pagos de antes del cobro (✅ / 💶)", "m:neto")]] + filas
    if not p["cumple"] and not pr.ignorada(p):
        lineas += ["", "⚖️ <b>Así no te queda lo que quieres.</b> Elige qué meta priorizar (las demás esperan y después "
                       "recuperan o se aplazan) o mira todas las propuestas."]
        filas = botones_prioridad(p) + [[("⚖️ Ver propuestas", "pr:aju"), ("🙈 Ignorar", "pri")]] + filas
    if p["reparto"]:
        lineas += ["", "💡 <i>Qué significa: tu libre es fijo y es tuyo; todo lo que sobra después de pagar va a tus metas, "
                       "así que reciben más los meses con menos pagos. Si algún cobro no llega ni a tu libre, sale en "
                       "amarillo o rojo.</i>"]
    else:
        lineas += ["", "💡 <i>Qué significa: «libre» es lo que te queda de cada cobro después de pagar todo y apartar lo "
                       "de tus metas (no se resta lo que gastas en el día a día). Si algún cobro sale en rojo, la "
                       "configuración actual no es sostenible.</i>"]
    imagenes = [go.cobro(primero, pie(p)), go.reparto(p, pie(p))]
    return "\n".join(lineas), imagenes, filas


def mes_a_mes():
    p = pr.simular()
    if not p:
        return sin_salario()
    ciclos = p["ciclos"]
    varia = any(c["totales"]["deben"] for c in ciclos)
    cabecera = f"{'Cobro':<7}" + (f"{'Entra':>6}" if varia else "") + f"{'Pagos':>6}{'Metas':>6}{'Libre':>7}{'Acum.':>8}"
    filas_tabla = [cabecera, "─" * len(cabecera)]
    filas_tabla.append(f"{'hoy':<7}" + (" " * 6 if varia else "") + f"{'':>6}{'':>6}{'':>7}{entero(p['puente']):>8}")
    for c in ciclos:
        marca = " !" if c["estado"] == "🔴" else (" ·" if c["estado"] == "🟡" else "")
        if not marca and p["reparto"] and c["libre"] - c["hueco"] > p["minimo"] + 0.5:
            marca = " +"  # tus metas ya están completas: lo que sobra queda libre
        filas_tabla.append(f"{pr.mes_corto(c['fecha']):<7}"
                           + (f"{entero(c['salario'] + c['totales']['deben']):>6}" if varia else "")
                           + f"{entero(-c['pagos']):>6}{entero(-c['totales']['metas']):>6}{entero(c['libre']):>7}"
                           f"{entero(c['acumulado']):>8}{marca}")
    pagos = sum(c["pagos"] for c in ciclos)
    a_metas = sum(c["totales"]["metas"] for c in ciclos)
    lineas = [f"📅 <b>Mes a mes</b> · salario {euros(p['salario'])}" + ("" if varia else " cada cobro"),
              f"<pre>{chr(10).join(filas_tabla)}</pre>",
              "<i>Pagos = fijos, suscripciones, cuotas y pagos únicos · Acum. = dinero libre acumulado"
              + (" · Entra = salario + lo que te devuelven" if varia else "") + " · ! no llega · · justo"
              + (" · + más que tu libre porque tus metas ya están completas" if p["reparto"] else "")
              + (f" · el 1.er cobro incluye {euros_cortos(ciclos[0]['hueco'])} para los pagos de antes del cobro"
                 if ciclos[0]["hueco"] else "") + "</i>", "",
              f"🧾 Pagarás en total {euros(pagos)} · 🎯 apartarás {euros(a_metas)}",
              f"💸 Te quedarán libres {euros(sum(c['libre'] for c in ciclos))} → acabas con <b>{euros(p['final'])}</b>"]
    rojos = p["rojos"]
    if rojos:
        lineas.append(f"🔴 No llega en {len(rojos)} cobro{'s' if len(rojos) > 1 else ''}: "
                      + ", ".join(pr.mes_corto(c["fecha"]) for c in rojos[:6]))
    lineas += ["", "💡 <i>Qué significa: cada fila es un cobro. «Libre» es lo que te sobra de ese cobro y «Acum.» lo que "
                   "irías juntando desde hoy si no gastaras nada más.</i>"]
    return "\n".join(lineas), [go.acumulado(p, pie(p), hoy())], botones_menu("mes")


def calendario():
    p = pr.simular()
    if not p:
        return sin_salario()
    lineas = ["🗓️ <b>Calendario</b>: lo que cambia en tus cobros", ""]
    mes_actual = None
    for fecha, _, tipo, texto, _ in p["eventos"]:
        etiqueta = pr.mes_largo(fecha)
        if etiqueta != mes_actual:
            lineas.append(f"<b>{etiqueta.capitalize()}</b>")
            mes_actual = etiqueta
        icono = {"deuda": "🔓", "meta": "🏁", "deben": "🤝", "unico": "🧾", "tramo": "🔁", "todas": "🏆"}[tipo]
        lineas.append(f"   {icono} {e(texto)}")
    if not p["eventos"]:
        lineas.append("No hay cambios en este periodo: cada cobro se reparte igual.")
    debo = [d for d in deudas.activas("debo") if d["tipo"] == "plazos"]
    fines = [deudas.fecha_fin(d) for d in debo if deudas.fecha_fin(d)]
    if fines:
        lineas += ["", f"💳 Sin deudas a plazos en <b>{pr.mes_largo(max(fines))}</b>"]
    if p["sin_fecha"]:
        lineas.append("🤝 Sin fecha (no se cuentan): " + ", ".join(f"{e(d['nombre'])} {euros_cortos(d['importe'])}"
                                                                  for d in p["sin_fecha"]))
    lineas += ["", "💡 <i>Qué significa: cuando terminas una deuda o consigues una meta, ese dinero queda libre en los "
                   "cobros siguientes.</i>"]
    filas_grafico = []
    for d in deudas.activas():
        if d["tipo"] == "plazos":
            filas_grafico.append((d["nombre"], "deben" if deudas.me_deben(d) else "deuda", deudas.fecha_fin(d), None))
    fin_metas = pr.fin_metas()
    for m in metas.activas():
        limite = None if m["especial"] else date.fromisoformat(m["fecha_limite"])
        filas_grafico.append((m["nombre"], "meta", fin_metas.get(m["id"]), limite))
    imagenes = [go.calendario(filas_grafico, pie(p), hoy(), p["ciclos"][-1]["fecha"])] if filas_grafico else []
    return "\n".join(lineas), imagenes, botones_menu("cal")


def fases(p, meta_id):
    """(cuota en espera o None, cuota después o None, primer cobro después) de una meta en la proyección p."""
    espera = despues = cuando = None
    for c in p["ciclos"]:
        importe, en_tramo = c["por_meta"].get(meta_id, (0.0, False))
        if en_tramo and espera is None:
            espera = importe
        elif not en_tramo and espera is not None and importe > 0:
            despues, cuando = importe, c["fecha"]
            break
    return espera, despues, cuando


def texto_hasta(cambios_o_meta, fines):
    hasta = cambios_o_meta.get("tramo_hasta", "") if isinstance(cambios_o_meta, dict) else cambios_o_meta["tramo_hasta"]
    if hasta.startswith("meta:"):
        otra = metas.obtener(int(hasta[5:]))
        fin = fines.get(int(hasta[5:]))
        return (f"hasta conseguir «{e(otra['nombre'])}»" if otra else "hasta tu prioritaria") + \
            (f" (≈ {pr.mes_corto(fin)})" if fin else "")
    if hasta.startswith("fecha:"):
        return f"hasta el cobro de {pr.mes_corto(date.fromisoformat(hasta[6:]))}"
    return ""


def pantalla_metas():
    p = pr.simular()
    if not p:
        return sin_salario()
    if not p["metas"]:
        return ("🎯 <b>Metas en la proyección</b>\n\nNo tienes metas activas: todo lo libre es tuyo. "
                f"Podrías destinar hasta {euros(p['maximo_metas'])} por cobro a metas dejando tu libre mínimo.",
                [], botones_menu("met"))
    base = pr.aportes_primer_cobro(p)
    fines = pr.fin_metas()
    lineas = ["🎯 <b>Metas en la proyección</b>", ""]
    filas_grafico = []
    for m in sorted(p["metas"], key=lambda m: (m["prioridad"] == 0, m["prioridad"], m["fecha_limite"])):
        aporte = base.get(m["id"], 0.0)
        fin = fines.get(m["id"])
        limite = None if m["especial"] else date.fromisoformat(m["fecha_limite"])
        modo = f"fija de {euros_cortos(m['aporte_fijo'])}" if m["aporte_modo"] == "fija" and m["aporte_fijo"] else "la necesaria"
        icono = "🛟" if m["especial"] else ("🥇" if m["prioridad"] else "🎯")
        if p["reparto"]:
            minimo, maximo, media = rango_metas(p, m["id"])
            lineas.append(f"{icono} <b>{e(m['nombre'])}</b>" + (f" · prioridad {m['prioridad']}" if m["prioridad"] else "")
                          + f" · recibe {texto_rango(minimo, maximo)} por cobro (de media {euros_cortos(round(media))})")
        else:
            lineas.append(f"{icono} <b>{e(m['nombre'])}</b>" + (f" · prioridad {m['prioridad']}" if m["prioridad"] else "")
                          + f" · {euros(aporte)} por cobro ({aporte / p['salario']:.0%} del salario) · {modo}".replace("%", " %"))
        espera, despues, cuando = fases(p, m["id"])
        if not p["reparto"] and m["tramo_aporte"] >= 0 and espera is not None:
            tras = ("sube para llegar a su fecha" if m["tramo_despues"] == "recuperar" else "vuelve a su cuota (aplazada)")
            lineas.append(f"   ⏸️ {euros_cortos(espera)} {texto_hasta(m, fines)}; después {tras}"
                          + (f": {euros_cortos(despues)} desde {pr.mes_corto(cuando)}" if despues else ""))
        if fin:
            tarde = limite and fin > limite
            lineas.append(f"   {'🔴 llegas tarde' if tarde else '✅ llegas'} en {pr.mes_largo(fin)}"
                          + (f" (límite {pr.mes_largo(limite)})" if limite else ""))
        else:
            lineas.append("   🔴 con esta aportación no llegas")
        filas_grafico.append((m["nombre"], aporte, fin, limite))
    total = sum(base.values())
    if p["reparto"]:
        lineas += ["", f"🔀 Reparto: {reparto.MODOS[reparto.modo()]}. En el próximo cobro: <b>{euros(total)}</b>"]
    else:
        lineas += ["", f"Total: <b>{euros(total)}</b> por cobro · puedes destinar hasta {euros(p['maximo_metas'])} "
                       "dejando tu libre mínimo"]
    if total:
        mayor = max(p["metas"], key=lambda m: base.get(m["id"], 0))
        lineas.append(f"La que más pesa: {e(mayor['nombre'])} ({base.get(mayor['id'], 0) / total:.0%} de lo que apartas)"
                      .replace("%", " %"))
    lineas += ["", "💡 <i>Qué significa: lo que aparta cada meta en el próximo cobro y cuándo la consigues si sigues así. "
                   "Para cambiarlo, prioriza una meta o usa «⚖️ Ajustar».</i>"]
    return "\n".join(lineas), [go.metas(filas_grafico, p["salario"], pie(p))], botones_prioridad(p) + botones_menu("met")


def linea_variante(v, recomendada):
    estrella = "⭐ " if recomendada else ""
    if not v["posible"]:
        return f"{estrella}{v['nombre']}: ✖️ no es posible ({e(v['motivo'][0].lower() + v['motivo'][1:]) if v['motivo'] else 'no cumple'})"
    r = v["resultado"]
    return (f"{estrella}{v['nombre']}{' (recomendada)' if recomendada else ''}: cobro más justo {euros(r['peor']['libre'])} "
            f"· acabas con {euros(r['final'])}")


def ajustar(sim):
    """Prioridades, propuestas con sus variantes y simulador por meta (sim: {meta_id: {"delta": €, "meses": n}})."""
    p = pr.simular()
    if not p:
        return sin_salario()
    icono, veredicto = pr.veredicto(p)
    lineas = ["⚖️ <b>Ajustar tus metas</b>", f"Ahora: {icono} {veredicto}",
              f"💸 Libre que quieres en cada cobro: {euros(p['minimo'])} <i>(cámbialo abajo)</i>"]
    if p["reparto"]:
        lineas.append(f"🔀 Reparto automático: {reparto.MODOS[reparto.modo()]}")
    lineas.append("")
    filas = []
    prioritarias = [m for m in p["metas"] if m["prioridad"]]
    en_espera = [m for m in p["metas"] if m["tramo_aporte"] >= 0 and not p["reparto"]]
    if prioritarias or en_espera:
        fines = pr.fin_metas()
        lineas.append("🥇 <b>Prioridades</b>: " + ", ".join(f"{m['prioridad']}.ª {e(m['nombre'])}"
                                                            for m in sorted(prioritarias, key=lambda m: m["prioridad"])))
        for m in en_espera:
            lineas.append(f"   ⏸️ {e(m['nombre'])}: {euros_cortos(m['tramo_aporte'])} {texto_hasta(m, fines)}, "
                          f"después {'recupera' if m['tramo_despues'] == 'recuperar' else 'se aplaza'}")
    if p["metas"]:
        lineas.append("<b>Elige qué meta priorizar</b> (las demás esperan) o varias en orden con «🔢»:")
        filas += botones_prioridad(p, 6) + [[("🔢 Ordenar varias prioritarias", "pro:ini")]]
    propuestas = pr.propuestas(p)
    if propuestas:
        lineas += ["", "<b>Propuestas</b> (puedes aplicarlas o ignorarlas):"]
        for x in propuestas:
            lineas.append(f"{x['titulo']}")
            lineas += [f"   {linea_variante(v, v['codigo'] == x['recomendada'] and len(x['variantes']) > 1)}"
                       for v in x["variantes"]]
            filas.append([(f"Ver: {x['titulo']}", f"prp:{x['clave']}")])
        if not p["cumple"]:
            filas.append([("🙈 Ignorar propuestas", "pri")])
    elif p["metas"]:
        lineas += ["", "✅ No hace falta ajustar nada."]
    imagenes = []
    if p["reparto"]:
        filas += [[(f"{'✅ ' if reparto.modo() == clave else ''}{texto}", f"pr:rep:m:{clave}")]
                  for clave, texto in (("necesario", "🧮 Necesario + prioridad"), ("cascada", "🥇 En cascada"))]
    if p["metas"] and not p["reparto"]:
        lineas += ["", "<b>Simulador</b>: cambia la aportación o la fecha de una meta y mira el resultado "
                       "(no se guarda nada hasta que pulses «Aplicar»)."]
        cambios = cambios_simulados(sim)
        for m in p["metas"]:
            s = sim.get(str(m["id"]), {})
            marca = ""
            if s.get("delta"):
                marca += f" {'+' if s['delta'] > 0 else ''}{s['delta']} €"
            if s.get("meses"):
                marca += f" +{s['meses']} meses"
            filas.append([(f"{m['nombre'][:14]}{marca}", "nada"), (f"−{PASO}", f"prs:{m['id']}:-"),
                          (f"+{PASO}", f"prs:{m['id']}:+")] + ([] if m["especial"] else [("📅+3", f"prs:{m['id']}:f")]))
        if cambios:
            r = pr.simular(cambios)
            icono_r, veredicto_r = pr.veredicto(r)
            lineas += ["", f"<b>Con tus cambios:</b> {icono_r} {veredicto_r}",
                       f"Acabas con {euros(r['final'])} ({euros(r['final'] - p['final'], signo=True)})"]
            fines_antes, fines_despues = pr.fin_metas(), pr.fin_metas(cambios)
            for m in p["metas"]:
                if fines_antes.get(m["id"]) != fines_despues.get(m["id"]):
                    antes = pr.mes_corto(fines_antes[m["id"]]) if fines_antes.get(m["id"]) else "nunca"
                    despues = pr.mes_corto(fines_despues[m["id"]]) if fines_despues.get(m["id"]) else "nunca"
                    lineas.append(f"   {e(m['nombre'])}: llegas en {despues} (antes {antes})")
            filas.append([("✅ Aplicar cambios", "prs:ok"), ("↩️ Quitar", "prs:x")])
            imagenes.append(go.comparacion([("Ahora", p), ("Con tus cambios", r)], pie(p), "Antes y después",
                                           "Lo libre en cada cobro con tus cambios"))
    if p["reparto"]:
        lineas += ["", "💡 <i>Qué significa: con el reparto automático, lo que sobra de cada cobro va a tus metas en el "
                       "orden de tus prioridades. Priorizar una meta hace que reciba antes; si alguna no llega a su fecha, "
                       "puedes priorizarla o mover su fecha.</i>"]
    else:
        lineas += ["", "💡 <i>Qué significa: priorizar una meta hace que las demás aporten menos (o nada) mientras tanto; "
                       "cuando la consigues, las demás recuperan (suben para llegar a su fecha) o se aplazan (vuelven a "
                       "su cuota y llegan más tarde). Tú eliges; el bot recomienda la que te deja tu libre mínimo.</i>"]
    return "\n".join(lineas), imagenes, filas + botones_menu("aju")


def cambios_simulados(sim):
    """Convierte el simulador ({id: {delta, meses}}) en cambios para proyeccion.simular."""
    p = pr.simular()
    base = pr.aportes_primer_cobro(p) if p else {}
    cambios = {}
    for meta_id, s in sim.items():
        meta = metas.obtener(int(meta_id))
        if not meta or meta["activa"] != metas.ACTIVA:
            continue
        cfg = {}
        if s.get("delta"):
            cfg["aporte_modo"] = "fija"
            cfg["aporte_fijo"] = max(pr.MINIMO, round(base.get(meta["id"], 0) + s["delta"]))
        if s.get("meses"):
            cfg["fecha_limite"] = sumar_meses(date.fromisoformat(meta["fecha_limite"]), s["meses"], 28).isoformat()
        if cfg:
            cambios[meta["id"]] = cfg
    return cambios


def describir_meta(p, v, meta_id, fines):
    """Una línea con lo que pasa con una meta en una variante: espera, después y cuándo llega."""
    meta = metas.obtener(meta_id)
    cfg = v["cambios"].get(meta_id, {})
    r = v["resultado"]
    fin = fines.get(meta_id)
    if r.get("reparto"):
        limite = date.fromisoformat(cfg.get("fecha_limite", meta["fecha_limite"]))
        antes = pr.fin_metas().get(meta_id)
        minimo, maximo, _ = rango_metas(r, meta_id)
        llega = f"llega en {pr.mes_corto(fin)}" if fin else "no llega en 10 años"
        if fin and not meta["especial"]:
            llega += " ✅ a tiempo" if fin <= limite else f" (su fecha: {pr.mes_corto(limite)})"
        if antes and fin and antes != fin:
            llega += f" · antes {pr.mes_corto(antes)}"
        return f"• {e(meta['nombre'])}: recibe {texto_rango(minimo, maximo)} por cobro → {llega}"
    limite = date.fromisoformat(meta["fecha_limite"])
    antes = pr.aportes_primer_cobro(p).get(meta_id, 0.0)
    espera, despues, cuando = fases(r, meta_id)
    llega = f"llega en {pr.mes_corto(fin)}" if fin else "no llega"
    if fin and not meta["especial"]:
        llega += " ✅ a tiempo" if fin <= limite else f" (antes {pr.mes_corto(limite)})"
    if espera is not None:
        tras = (f"después {euros_cortos(despues)} por cobro desde {pr.mes_corto(cuando)}" if despues
                else "la consigues antes de que acabe la espera")
        return f"• {e(meta['nombre'])}: {euros_cortos(espera)} por cobro {texto_hasta(cfg, fines)}; {tras} → {llega}"
    nuevo = pr.aportes_primer_cobro(r).get(meta_id, 0.0)
    return f"• {e(meta['nombre'])}: {euros_cortos(antes)} → {euros_cortos(nuevo)} por cobro → {llega}"


def propuesta(clave):
    p = pr.simular()
    x = pr.propuesta(p, clave) if p else None
    if not x:
        return ("⚖️ Esta propuesta no se puede calcular ahora (puede que ya no haga falta, o que algo haya cambiado).",
                [], botones_menu("aju"))
    lineas = [f"<b>{x['titulo']}</b>", f"<i>{x['explicacion']}</i>"]
    filas, comparar, lineas_grafico = [], [("Ahora", p)], []
    varias = len(x["variantes"]) > 1
    for n, v in enumerate(x["variantes"]):
        recomendada = varias and v["codigo"] == x["recomendada"]
        lineas += ["", f"<b>{'⭐ ' if recomendada else ''}{v['nombre']}{' (recomendada)' if recomendada else ''}</b>"]
        if not v["posible"]:
            lineas.append(f"✖️ No es posible: {e(v['motivo'])}" if v["motivo"] else "✖️ No es posible.")
            continue
        fines = pr.fin_metas(v["cambios"])
        antes, nuevo = pr.aportes_primer_cobro(p), pr.aportes_primer_cobro(v["resultado"])
        cambian = [i for i in v["cambios"] if i in antes and (abs(antes[i] - nuevo.get(i, 0.0)) >= 0.5
                   or v["cambios"][i].get("fecha_limite", metas.obtener(i)["fecha_limite"]) != metas.obtener(i)["fecha_limite"])]
        ids = list(dict.fromkeys(v["reducidas"] + cambian))
        if v["resultado"].get("reparto"):
            ids = [i for i in v["cambios"] if i in antes or i in nuevo]
        lineas += [describir_meta(p, v, i, fines) for i in ids]
        icono, veredicto = pr.veredicto(v["resultado"])
        lineas.append(f"{icono} {veredicto} · acabas con {euros(v['resultado']['final'])}")
        filas.append([(f"✅ Aplicar: {'⭐ ' if recomendada else ''}{v['nombre']}", f"pra:{clave}:{v['codigo']}")])
        comparar.append((v["corto"].capitalize(), v["resultado"]))
        if v["resultado"].get("reparto"):
            for color, meta_id in enumerate(ids[:2]):
                nombre_meta = metas.obtener(meta_id)["nombre"][:12]
                for estilo, proyeccion_, etiqueta in (("discontinua", p, "ahora"), ("continua", v["resultado"], "propuesta")):
                    lineas_grafico.append((f"{nombre_meta} · {etiqueta}", color, estilo,
                                           [c["por_meta"].get(meta_id, (0.0, False))[0] for c in proyeccion_["ciclos"]]))
        for color, meta_id in enumerate(v["reducidas"][:2] if not v["resultado"].get("reparto") else []):
            lineas_grafico.append((f"{metas.obtener(meta_id)['nombre'][:12]} · {v['corto']}", color,
                                   "continua" if n == 0 else "discontinua",
                                   [c["por_meta"].get(meta_id, (0.0, False))[0] for c in v["resultado"]["ciclos"]]))
    lineas += ["", "<i>Si la aplicas, se cambian tus metas (se puede deshacer en 10 minutos) y los recordatorios piden "
                   "la cuota de cada momento. O ignórala y lo dejo como está.</i>"]
    filas.append([("🙈 Ignorar", "pri"), ("⬅️ Ajustar", "pr:aju")])
    imagenes = []
    if len(comparar) > 1:
        imagenes.append(go.comparacion(comparar, pie(p), "Antes y después", "Lo libre en cada cobro con cada opción"))
    if lineas_grafico:
        imagenes.append(go.cuotas(lineas_grafico, [c["fecha"] for c in p["ciclos"]], pie(p),
                                  "Cuota de tus metas, cobro a cobro",
                                  "Lo que recibe cada meta de lo que sobra en cada cobro" if p["reparto"] else
                                  "Baja mientras espera; después sube (recuperar) o vuelve a la normal (aplazar)"))
    return "\n".join(lineas), imagenes, filas


def orden(ids):
    """Pantalla para elegir varias prioritarias en orden."""
    p = pr.simular()
    if not p:
        return sin_salario()
    candidatas = [m for m in p["metas"] if m["id"] in pr.aportes_primer_cobro(p)]
    elegidas = [metas.obtener(i) for i in ids if metas.obtener(i)]
    texto = ("🔢 <b>Prioridades en orden</b>\nPulsa tus metas de la más importante a la menos. Cada una espera a la "
             "anterior; las que no pulses esperan a la última.\n\n"
             + ("Orden: " + " → ".join(f"{n}.ª {e(m['nombre'])}" for n, m in enumerate(elegidas, 1)) if elegidas
                else "Aún no has elegido ninguna."))
    filas = [[(f"{len(elegidas) + 1}.ª: {m['nombre'][:20]}", f"pro:{m['id']}")] for m in candidatas if m["id"] not in ids]
    if elegidas:
        filas.append([("✅ Ver la propuesta", "pro:ok"), ("↩️ Empezar de nuevo", "pro:x")])
    filas.append([("⬅️ Ajustar", "pr:aju")])
    return texto, [], filas


def pantalla_reparto():
    activo = reparto.activo()
    minimo = pr.libre_minimo()
    texto = ("🔀 <b>Reparto automático</b>\n"
             f"Ahora: <b>{'activado' if activo else 'apagado'}</b>.\n\n"
             f"Con el reparto, en cada cobro: lo que entra − todos tus pagos − <b>tu libre ({euros(minimo)})</b> = lo que "
             "sobra, y <b>todo lo que sobra va a tus metas</b>. Si te faltaba dinero para los pagos de antes del cobro, primero se cubre eso.\n\n"
             "<b>¿Cómo se reparte entre tus metas?</b>\n"
             + "\n".join(f"{'✅' if activo and reparto.modo() == clave else '▫️'} {nombre}" for clave, nombre in reparto.MODOS.items())
             + "\n\n<i>Lo que te deben entra al reparto solo cuando confirmas que te han pagado. Las prioridades (🥇) "
               "las eliges en ⚖️ Ajustar.</i>")
    filas = [[("🧮 Necesario + prioridad", "pr:rep:m:necesario"), ("🥇 En cascada", "pr:rep:m:cascada")],
             [("⏸️ Apagar el reparto" if activo else "✅ Activar el reparto", "pr:rep:off" if activo else "pr:rep:on"),
              (f"💸 Tu libre: {euros_cortos(minimo)}", "pr:lib")],
             [("⬅️ Proyección", "pr:res")]]
    return texto, [], filas


def libre():
    minimo = pr.libre_minimo()
    texto = ("💸 <b>¿Cuánto dinero quieres que te quede libre en cada cobro?</b>\n"
             f"Ahora: {euros(minimo)}" + (" (todo el salario va a pagos y metas)" if not minimo else "") + ".\n"
             "Las propuestas ajustan tus metas para dejarte al menos esto. Elige o escribe una cantidad.")
    opciones = (0, 50, 100, 200, 300, 500)
    filas = [[(("✅ " if abs(minimo - n) < 0.01 else "") + (f"{n} €" if n else "0 € (todo)"), f"pr:lib:{n}")
              for n in opciones[i:i + 3]] for i in (0, 3)]
    return texto, [], filas + [[("⬅️ Proyección", "pr:res")]]


def pantalla_escenarios():
    p = pr.simular()
    if not p:
        return sin_salario()
    lista = pr.escenarios(p)
    lineas = ["🧪 <b>¿Y si…?</b> Cómo acabarías en cada caso", ""]
    for nombre, r in lista:
        icono = pr.veredicto(r)[0]
        diferencia = "" if r is p else f" ({euros(r['final'] - p['final'], signo=True)})"
        lineas.append(f"{icono} <b>{nombre}</b>: acabas con {euros(r['final'])}{diferencia} · cobro más justo "
                      f"{euros(r['peor']['libre'])}")
    lineas += ["", "💡 <i>Qué significa: compara tu configuración actual con otras situaciones. «Sin lo que te deben» "
                   "es lo que pasaría si no te devolvieran nada; «Sin aportar a metas», cuánto te cuestan tus metas.</i>"]
    return "\n".join(lineas), [go.escenarios(lista, pie(p))], botones_menu("esc")


def horizonte():
    final = pr.mes_final()
    texto = (f"📆 <b>¿Hasta qué mes proyecto?</b>\nAhora: {pr.aviso_horizonte()}.\n"
             "Elige uno o escríbelo (ej. <b>agosto 2027</b> o <b>08/2027</b>), hasta 36 cobros.")
    base = date(hoy().year, hoy().month, 1)
    opciones = [(sumar_meses(base, n, 1), n) for n in (6, 12, 18, 24, 36)]
    filas = [[(f"{pr.mes_corto(d)} ({n})", f"pr:hz:{d:%Y-%m}") for d, n in opciones[:3]],
             [(f"{pr.mes_corto(d)} ({n})", f"pr:hz:{d:%Y-%m}") for d, n in opciones[3:]],
             [("12 cobros (por defecto)", "pr:hz:0")] if final else [],
             [("⬅️ Proyección", "pr:res")]]
    return texto, [], [f for f in filas if f]


def salario():
    importe, origen = pr.salario_base()
    texto = ("💶 <b>Salario para la proyección</b>\n"
             + (f"Ahora uso {euros(importe)} ({origen}).\n" if importe else "Aún no tengo ninguno.\n")
             + "Escribe un salario estimado (ej. <b>1950</b>) o vuelve a usar el último que cobraste.")
    filas = [[("↩️ Usar el último cobrado", "pr:sal:auto")]] if pr.salario_estimado() else []
    return texto, [], filas + [[("⬅️ Proyección", "pr:res")]]


PANTALLAS = {"res": resumen, "mes": mes_a_mes, "cal": calendario, "met": pantalla_metas, "esc": pantalla_escenarios,
             "hz": horizonte, "sal": salario, "lib": libre, "rep": pantalla_reparto}


# =====================================================================
# Envío y botones
# =====================================================================

async def enviar(context, calcular, *args):
    """Calcula en un hilo, envía los gráficos y después el texto con los botones."""
    b = _b()
    texto, imagenes, filas = await asyncio.to_thread(calcular, *args)
    for imagen in imagenes:
        await context.bot.send_photo(b.estado["chat_id"], photo=imagen)
    await context.bot.send_message(b.estado["chat_id"], texto, parse_mode="HTML",
                                   reply_markup=b.teclado(filas) if filas else None)


async def pantalla(update, context, nuevo=True):
    """Botón «📈 Proyección» del teclado."""
    context.user_data.pop("proy_sim", None)
    await enviar(context, resumen)


async def boton(update, context, partes):  # noqa: C901  (enrutador de botones de proyección)
    b = _b()
    clave = partes[0]
    sim = context.user_data.setdefault("proy_sim", {})
    if clave == "pr":
        opcion = partes[1]
        if opcion in ("hz", "sal", "lib") and len(partes) > 2:
            context.user_data.pop("espera", None)  # eligió con un botón: ya no espera texto
        if opcion == "rep" and len(partes) > 2:
            if partes[2] == "m":
                config.guardar("REPARTO_MODO", partes[3])
                config.guardar("REPARTO_AUTO", "1")
            else:
                config.guardar("REPARTO_AUTO", "1" if partes[2] == "on" else "0")
            if reparto.activo():
                await asyncio.to_thread(reparto.fijar_ciclo_actual)
            await enviar(context, pantalla_reparto)
            return "Reparto " + ("activado" if reparto.activo() else "apagado")
        if opcion == "lib" and len(partes) > 2:
            config.guardar("LIBRE_MINIMO", partes[2])
            await enviar(context, resumen)
            return f"Libre mínimo: {partes[2]} €"
        if opcion == "lib":
            b.esperar(context, "proy_libre")
        if opcion == "hz" and len(partes) > 2:
            config.guardar("PROYECCION_HASTA", "" if partes[2] == "0" else partes[2])
            await enviar(context, resumen)
            return f"Proyección hasta {pr.aviso_horizonte()}"
        if opcion == "hz":
            b.esperar(context, "proy_hasta")
        if opcion == "sal" and len(partes) > 2:
            config.guardar("SALARIO_ESTIMADO", "0")
            await enviar(context, resumen)
            return "Uso el último salario cobrado"
        if opcion == "sal":
            b.esperar(context, "proy_salario")
        if opcion == "aju":
            await enviar(context, ajustar, dict(sim))
            return None
        await enviar(context, PANTALLAS.get(opcion, resumen))
        return None
    if clave == "prp":
        await enviar(context, propuesta, partes[1])
        return None
    if clave == "prq":
        await enviar(context, propuesta, f"Q{int(partes[1])}")
        return None
    if clave == "pro":
        orden_ids = context.user_data.setdefault("proy_orden", [])
        if partes[1] in ("ini", "x"):
            orden_ids.clear()
        elif partes[1] == "ok":
            if not orden_ids:
                return "Elige al menos una meta"
            await enviar(context, propuesta, "Q" + "-".join(map(str, orden_ids)))
            return None
        elif int(partes[1]) not in orden_ids:
            orden_ids.append(int(partes[1]))
        await enviar(context, orden, list(orden_ids))
        return None
    if clave == "pra":
        def calcular():
            p = pr.simular()
            x = pr.propuesta(p, partes[1]) if p else None
            return x, (pr.variante(x, partes[2] if len(partes) > 2 else None) if x else None)
        x, v = await asyncio.to_thread(calcular)
        if not x or not v or not v["posible"]:
            return "Esa propuesta ya no aplica"
        accion = pr.aplicar(v["cambios"], f"Propuesta «{x['titulo'][2:].strip()}» ({v['nombre'][2:].strip()})")
        await b.enviar(context, f"✅ Aplicado: {e(x['titulo'])} · {v['nombre']}.\nTus metas ya piden la cuota de cada "
                                "momento; cuando cambie de tramo te lo pediré con la nueva cantidad.",
                       b.con_deshacer(accion, [[("📈 Ver proyección", "pr:res"), ("🎯 Ver metas", "m:metas")]]))
        return "Aplicado"
    if clave == "pri":
        p = await asyncio.to_thread(pr.simular)
        if p:
            datos.marcar_enviado(f"proy_ignorar:{pr.firma(p)}")
        await b.mostrar(update, context, "🙈 Vale, lo dejo como está. No te lo vuelvo a proponer mientras no cambies "
                                         "tus metas, deudas o salario.", [[("📈 Ver proyección", "pr:res")]])
        return None
    if clave == "prs":
        if partes[1] == "x":
            sim.clear()
        elif partes[1] == "ok":
            cambios = cambios_simulados(sim)
            if not cambios:
                return "No hay cambios"
            accion = pr.aplicar(cambios, "Cambios del simulador")
            sim.clear()
            await b.enviar(context, "✅ Cambios aplicados a tus metas.", b.con_deshacer(accion, [[("📈 Ver proyección", "pr:res")]]))
            return "Aplicado"
        else:
            s = sim.setdefault(partes[1], {})
            if partes[2] == "+":
                s["delta"] = s.get("delta", 0) + PASO
            elif partes[2] == "-":
                s["delta"] = s.get("delta", 0) - PASO
            elif partes[2] == "f":
                s["meses"] = s.get("meses", 0) + 3
        await enviar(context, ajustar, dict(sim))
        return None
    return None


async def responder(update, context, espera, escrito):
    """Pasos escritos «proy_*». Devuelve True si los ha atendido."""
    b = _b()
    if espera["paso"] == "proy_hasta":
        final = leer_mes(escrito, hoy())
        if not final or (final.year - hoy().year) * 12 + final.month - hoy().month > 36:
            await b.repetir(update, "Escribe un mes de los próximos 3 años, por ejemplo <b>agosto 2027</b>.")
            return True
        context.user_data.pop("espera", None)
        config.guardar("PROYECCION_HASTA", f"{final:%Y-%m}")
        await enviar(context, resumen)
        return True
    if espera["paso"] == "proy_libre":
        importe = 0.0 if escrito.strip() == "0" else leer_importe(escrito)
        if importe is None:
            await b.repetir(update, "Escribe una cantidad, por ejemplo <b>150</b> (o 0).")
            return True
        context.user_data.pop("espera", None)
        config.guardar("LIBRE_MINIMO", round(importe, 2))
        await enviar(context, resumen)
        return True
    if espera["paso"] == "proy_salario":
        importe = leer_importe(escrito)
        if not importe or importe < 100:
            await b.repetir(update, "Escribe el salario, por ejemplo <b>1950</b>.")
            return True
        context.user_data.pop("espera", None)
        config.guardar("SALARIO_ESTIMADO", round(importe, 2))
        await enviar(context, resumen)
        return True
    return False
