"""Interfaz de Telegram de 📈 Proyección (botón del teclado).

Pantallas (botones «pr:»): resumen, mes a mes, calendario, metas, ajustar y ¿y si…?; hasta qué mes
(PROYECCION_HASTA) y salario estimado (SALARIO_ESTIMADO). Propuestas para que sea sostenible:
«prp:X» las enseña, «pra:X» las aplica (con deshacer) y «pri» las ignora. Simulador por meta: «prs:».
Pasos escritos: «proy_hasta» y «proy_salario». Nunca consulta al banco.
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
from formato import euros, euros_cortos, fecha_corta, leer_importe, leer_mes, sumar_meses

PREFIJOS = {"pr", "prp", "pra", "pri", "prs"}
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
    filas.append([(f"📆 Hasta: {pr.aviso_horizonte()}", "pr:hz"), ("💶 Salario", "pr:sal")])
    return filas


def sin_salario():
    return ("📈 <b>Proyección</b>\n\nPara proyectar necesito tu salario: regístralo cuando cobres "
            "(💰 Saldo › 💶 Registrar cobro) o escribe uno estimado.", [], [[("💶 Escribir salario estimado", "pr:sal")]])


def lineas_cobro(c):
    t = c["totales"]
    lineas = [f"💶 Entra {euros(c['salario'])}" + (f" + te devuelven {euros(t['deben'])}" if t["deben"] else "")]
    for clave, icono, nombre in (("fijos", "🏠", "Gastos fijos"), ("subs", "📺", "Suscripciones"),
                                 ("cuotas", "💳", "Cuotas de deudas"), ("unicos", "🧾", "Pagos únicos")):
        if t[clave]:
            detalle = ", ".join(f"{e(d['nombre'])} {euros_cortos(i)}" for d, i, cl in c["items"] if cl == clave)
            lineas.append(f"{icono} {nombre}: −{euros(t[clave])}  <i>{detalle[:90]}</i>")
    if t["metas"]:
        detalle = ", ".join(f"{e(m['nombre'])} {euros_cortos(i)}" for m, i, _ in c["aportes"])
        lineas.append(f"🎯 Metas: −{euros(t['metas'])}  <i>{detalle[:90]}</i>")
    dias = (c["fin"] - c["fecha"]).days
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
              f"💶 Salario: <b>{euros(p['salario'])}</b> <i>({p['origen']})</i>", "",
              f"{icono} <b>{veredicto}</b>", "",
              f"<b>Hasta el próximo cobro ({fecha_corta(primero['fecha'])})</b>",
              f"💰 Dinero libre hoy: {euros(p['libre_hoy'])}"
              + (f" + te deben {euros(p['deben_hoy'])} este ciclo" if p["deben_hoy"] else ""),
              f"= Llegas al cobro con <b>{euros(p['puente'])}</b> libres", "",
              f"<b>Próximo cobro · {fecha_corta(primero['fecha'])}</b>"]
    lineas += lineas_cobro(primero)
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
    lineas.append(f"• Para metas puedes destinar hasta <b>{euros(p['maximo_metas'])}</b> por cobro sin quedarte en rojo "
                  f"(ahora apartas {euros(primero['totales']['metas'])})")
    fines = pr.fin_metas()
    if any(not x["especial"] and fines.get(x["id"]) is None for x in p["metas"]):
        lineas.append("• ⚠️ Alguna meta no llega nunca con la aportación actual: mira 🎯 Metas")
    filas = botones_menu("res")
    if not p["sostenible"] and not pr.ignorada(p):
        lineas += ["", "⚖️ <b>Tengo propuestas para que sea sostenible.</b> Míralas en «⚖️ Ajustar» (o ignóralas)."]
        filas.insert(0, [("⚖️ Ver propuestas", "pr:aju"), ("🙈 Ignorar", "pri")])
    lineas += ["", "💡 <i>Qué significa: «libre» es lo que te queda de cada cobro después de pagar todo y apartar lo de "
                   "tus metas (no se resta lo que gastas en el día a día). Si algún cobro sale en rojo, la configuración "
                   "actual no es sostenible.</i>"]
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
        filas_tabla.append(f"{pr.mes_corto(c['fecha']):<7}"
                           + (f"{entero(c['salario'] + c['totales']['deben']):>6}" if varia else "")
                           + f"{entero(-c['pagos']):>6}{entero(-c['totales']['metas']):>6}{entero(c['libre']):>7}"
                           f"{entero(c['acumulado']):>8}{marca}")
    pagos = sum(c["pagos"] for c in ciclos)
    a_metas = sum(c["totales"]["metas"] for c in ciclos)
    lineas = [f"📅 <b>Mes a mes</b> · salario {euros(p['salario'])}" + ("" if varia else " cada cobro"),
              f"<pre>{chr(10).join(filas_tabla)}</pre>",
              "<i>Pagos = fijos, suscripciones, cuotas y pagos únicos · Acum. = dinero libre acumulado"
              + (" · Entra = salario + lo que te devuelven" if varia else "") + " · ! no llega · · justo</i>", "",
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
        icono = {"deuda": "🔓", "meta": "🏁", "deben": "🤝", "unico": "🧾"}[tipo]
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


def pantalla_metas():
    p = pr.simular()
    if not p:
        return sin_salario()
    if not p["metas"]:
        return ("🎯 <b>Metas en la proyección</b>\n\nNo tienes metas activas: todo lo libre es tuyo. "
                f"Podrías destinar hasta {euros(p['maximo_metas'])} por cobro a metas sin quedarte en rojo.",
                [], botones_menu("met"))
    base = pr.aportes_primer_cobro(p)
    fines = pr.fin_metas()
    lineas = ["🎯 <b>Metas en la proyección</b>", ""]
    filas_grafico = []
    for m in p["metas"]:
        aporte = base.get(m["id"], 0.0)
        fin = fines.get(m["id"])
        limite = None if m["especial"] else date.fromisoformat(m["fecha_limite"])
        modo = f"fija de {euros_cortos(m['aporte_fijo'])}" if m["aporte_modo"] == "fija" and m["aporte_fijo"] else "la necesaria"
        lineas.append(f"{'🛟' if m['especial'] else '🎯'} <b>{e(m['nombre'])}</b> · {euros(aporte)} por cobro "
                      f"({aporte / p['salario']:.0%} del salario) · {modo}".replace("%", " %"))
        if fin:
            tarde = limite and fin > limite
            lineas.append(f"   {'🔴 llegas tarde' if tarde else '✅ llegas'} en {pr.mes_largo(fin)}"
                          + (f" (límite {pr.mes_largo(limite)})" if limite else ""))
        else:
            lineas.append("   🔴 con esta aportación no llegas")
        filas_grafico.append((m["nombre"], aporte, fin, limite))
    total = sum(base.values())
    lineas += ["", f"Total: <b>{euros(total)}</b> por cobro · puedes destinar hasta {euros(p['maximo_metas'])} "
                   "sin quedarte en rojo"]
    if total:
        mayor = max(p["metas"], key=lambda m: base.get(m["id"], 0))
        lineas.append(f"La que más pesa: {e(mayor['nombre'])} ({base.get(mayor['id'], 0) / total:.0%} de lo que apartas)"
                      .replace("%", " %"))
    lineas += ["", "💡 <i>Qué significa: lo que aparta cada meta en el próximo cobro y cuándo la consigues si sigues así. "
                   "Para cambiarlo, usa «⚖️ Ajustar».</i>"]
    return "\n".join(lineas), [go.metas(filas_grafico, p["salario"], pie(p))], botones_menu("met")


def ajustar(sim):
    """Propuestas automáticas y simulador por meta (sim: {meta_id: {"delta": €, "meses": n}})."""
    p = pr.simular()
    if not p:
        return sin_salario()
    icono, veredicto = pr.veredicto(p)
    lineas = ["⚖️ <b>Ajustar tus metas</b>", f"Ahora: {icono} {veredicto}", ""]
    filas = []
    propuestas = pr.propuestas(p)
    if propuestas:
        lineas.append("<b>Propuestas</b> (puedes aplicarlas o ignorarlas):")
        for x in propuestas:
            r = x["resultado"]
            lineas.append(f"{x['titulo']}: {x['explicacion']} → cobro más justo {euros(r['peor']['libre'])}, "
                          f"acabas con {euros(r['final'])}")
            filas.append([(f"Ver: {x['titulo']}", f"prp:{x['clave']}")])
        if not p["sostenible"]:
            filas.append([("🙈 Ignorar propuestas", "pri")])
    elif p["metas"]:
        lineas.append("✅ No hace falta ajustar nada.")
    imagenes = []
    if p["metas"]:
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
    lineas += ["", "💡 <i>Qué significa: si algún cobro sale en rojo, recortar aportaciones o alargar fechas lo arregla; "
                   "si te sobra, puedes acelerar tus metas.</i>"]
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


def propuesta(clave):
    p = pr.simular()
    x = next((x for x in pr.propuestas(p) if x["clave"] == clave), None) if p else None
    if not x:
        return "⚖️ Esa propuesta ya no aplica (algo ha cambiado).", [], botones_menu("aju")
    r = x["resultado"]
    icono, veredicto = pr.veredicto(r)
    lineas = [f"{x['titulo']}", f"<i>{x['explicacion']}</i>", "", "<b>Cambios en tus metas</b>"]
    fines_antes, fines_despues = pr.fin_metas(), pr.fin_metas(x["cambios"])
    base = pr.aportes_primer_cobro(p)
    nuevo = pr.aportes_primer_cobro(r)
    for meta_id, cfg in x["cambios"].items():
        m = metas.obtener(meta_id)
        partes = []
        if "aporte_fijo" in cfg:
            partes.append(f"{euros_cortos(base.get(meta_id, 0))} → <b>{euros_cortos(nuevo.get(meta_id, cfg['aporte_fijo']))}</b> por cobro")
        if "fecha_limite" in cfg:
            partes.append(f"fecha {pr.mes_corto(date.fromisoformat(m['fecha_limite']))} → "
                          f"<b>{pr.mes_corto(date.fromisoformat(cfg['fecha_limite']))}</b>")
        antes = pr.mes_corto(fines_antes[meta_id]) if fines_antes.get(meta_id) else "nunca"
        despues = pr.mes_corto(fines_despues[meta_id]) if fines_despues.get(meta_id) else "nunca"
        lineas.append(f"• {e(m['nombre'])}: {' · '.join(partes)} (llegas en {despues}, antes {antes})")
    lineas += ["", f"<b>Resultado:</b> {icono} {veredicto}",
               f"Cobro más justo: {euros(p['peor']['libre'])} → <b>{euros(r['peor']['libre'])}</b>",
               f"Dinero libre al final: {euros(p['final'])} → <b>{euros(r['final'])}</b>",
               "", "<i>Si la aplicas, se cambian tus metas (se puede deshacer en 10 minutos).</i>"]
    filas = [[("✅ Aplicar", f"pra:{clave}"), ("🙈 Ignorar", "pri")], [("⬅️ Ajustar", "pr:aju")]]
    imagen = go.comparacion([("Ahora", p), (x["titulo"][2:].strip(), r)], pie(p), "Antes y después", x["explicacion"])
    return "\n".join(lineas), [imagen], filas


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
             "hz": horizonte, "sal": salario}


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
        if opcion in ("hz", "sal") and len(partes) > 2:
            context.user_data.pop("espera", None)  # eligió con un botón: ya no espera texto
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
    if clave == "pra":
        p = await asyncio.to_thread(pr.simular)
        x = next((x for x in await asyncio.to_thread(pr.propuestas, p) if x["clave"] == partes[1]), None)
        if not x:
            return "Esa propuesta ya no aplica"
        accion = pr.aplicar(x["cambios"], f"Propuesta «{x['titulo'][2:].strip()}»")
        await b.enviar(context, f"✅ Aplicado: {e(x['titulo'])}. Tus metas ya piden las nuevas cantidades.",
                       b.con_deshacer(accion, [[("📈 Ver proyección", "pr:res")]]))
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
