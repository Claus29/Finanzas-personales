"""Textos del bot: saldo, saldo neto, análisis del ciclo, categorías, semana, deudas y metas.

Todo se calcula al momento con lo guardado en la última actualización: nunca se pregunta al banco.
Los mensajes son HTML de Telegram y cortos (unas 10 líneas), con barras y semáforos.
"""
import html
import logging
from datetime import date, timedelta

import ciclo
import config
import consultas
import datos
import deudas
import metas
import movimientos
from formato import MESES, barra, euros, euros_cortos, fecha_corta, semaforo
from movimientos import CATEGORIAS


def hoy():
    return config.ahora().date()


def e(texto):
    return html.escape(str(texto))


# ---------- Saldo ----------

def saldo_actual():
    """{"total", "cuentas": [(cuenta, importe)], "fecha"} con el último saldo de cada cuenta, o None."""
    cuentas = consultas.cuentas()
    filas = []
    fecha = None
    for cuenta in cuentas:
        fila = datos.uno("SELECT importe, fecha FROM saldos WHERE uid = ? ORDER BY fecha DESC LIMIT 1", cuenta["uid"])
        if fila:
            filas.append((cuenta, fila["importe"]))
            fecha = max(fecha or fila["fecha"], fila["fecha"])
    if not filas:
        return None
    return {"total": round(sum(i for _, i in filas), 2), "cuentas": filas, "fecha": fecha}


def texto_actualizado():
    from actualizacion import momento_ultima
    momento = momento_ultima()
    if not momento:
        return "Aún sin datos del banco"
    dia = momento.date()
    cuando = "hoy" if dia == hoy() else ("ayer" if dia == hoy() - timedelta(days=1) else f"el {dia:%d/%m}")
    return f"Actualizado {cuando} a las {momento:%H:%M}"


def dinero_libre(neto, d=None):
    """Saldo neto − dinero que ya está en las cuentas de tus metas − lo que falta apartar este ciclo."""
    import colchon
    reservar = sum(metas.pendiente_ciclo(m, d) for m in metas.activas())
    return round(neto - colchon.dinero_en_metas() - reservar, 2)


def puedes_gastar(neto, d=None):
    """(€ al día, días hasta el cobro) con el dinero libre (sin el de las metas)."""
    d = d or hoy()
    dias = ciclo.dias_hasta_cobro(d)
    return max(0.0, round(dinero_libre(neto, d) / dias, 2)), dias


def texto_saldo():
    s = saldo_actual()
    if not s:
        return ("💰 <b>Aún no tengo tus saldos.</b>\nSe descargan en la actualización diaria "
                f"({config.valor('HORA_SALDO_DIARIO')}). También puedes forzarla en ⚙️ Ajustes.")
    lineas = [f"💰 <b>Tu saldo: {euros(s['total'])}</b>", f"<i>{texto_actualizado()}</i>", ""]
    for n, (cuenta, importe) in enumerate(s["cuentas"]):
        rama = "└" if n == len(s["cuentas"]) - 1 else "├"
        lineas.append(f"{rama} {e(consultas.nombre_cuenta(cuenta))}: <b>{euros(importe)}</b>")
    neto, _ = deudas.neto(s["total"])
    diario, dias = puedes_gastar(neto)
    lineas += ["", f"🧮 Saldo neto: <b>{euros(neto)}</b>",
               f"💡 Puedes gastar ~<b>{euros_cortos(diario)}/día</b> durante {dias} días (hasta el cobro)"]
    return "\n".join(lineas)


def texto_neto():
    s = saldo_actual()
    if not s:
        return texto_saldo()
    inicio, proximo = ciclo.inicio(), ciclo.proximo_cobro()
    neto, items = deudas.neto(s["total"])
    lineas = [f"🧮 <b>Saldo neto</b> (ciclo {fecha_corta(inicio)} – {fecha_corta(proximo - timedelta(days=1))})", "",
              f"Saldo total ({texto_actualizado().lower()})", f"   {euros(s['total'])}"]
    if items:
        lineas.append(f"− Pendiente de pagar este ciclo: {euros(sum(i['importe'] for i in items))}")
        for i in items:
            deuda = i["deuda"]
            if deuda["tipo"] == "plazos":
                numero, total_cuotas = deudas.numero_cuota(deuda)
                detalle = f"cuota {numero}/{total_cuotas}" + (f", {i['juntas']} juntas" if i.get("juntas", 1) > 1 else "")
            else:
                detalle = deudas.TIPOS[deuda["tipo"]].split(" ", 1)[1].lower()
            aviso = " ⚠️ atrasado" if i["atrasada"] else f" · {fecha_corta(i['vence'])}"
            lineas.append(f"   • {e(deuda['nombre'])} ({detalle}{aviso}): {euros(i['importe'])}")
    else:
        lineas.append("− Nada pendiente de pagar este ciclo ✅")
    lineas.append(f"= <b>Saldo neto: {euros(neto)}</b>")
    comprometido = deudas.comprometido_proximo_cobro()
    if comprometido:
        lineas.append(f"\n⏭️ Comprometido del próximo cobro: {euros(sum(i for _, i in comprometido))} "
                      f"({', '.join(e(d['nombre']) for d, _ in comprometido)})")
    import colchon
    en_metas = colchon.dinero_en_metas()
    if en_metas:
        lineas.append(f"🎯 En las cuentas de tus metas: {euros(en_metas)} (no es dinero libre)")
    reservar = sum(metas.pendiente_ciclo(m) for m in metas.activas())
    if reservar:
        lineas.append(f"🎯 Te falta apartar este ciclo para tus metas: {euros(reservar)}")
    cobrar = deudas.por_cobrar()
    if cobrar:
        total = sum(i["importe"] for i in cobrar)
        lineas.append(f"🤝 Este ciclo te tienen que pagar {euros(total)} (no se suma): "
                      f"si te pagan, tu neto sería {euros(neto + total)}")
    otros = sum(deudas.restante(d)[0] for d in deudas.activas("me_deben")) - sum(i["importe"] for i in cobrar)
    if otros > 0.004:
        lineas.append(f"🤝 Más adelante te deben otros {euros(otros)}")
    diario, dias = puedes_gastar(neto)
    lineas.append(f"\n💡 Puedes gastar ~<b>{euros_cortos(diario)}/día</b> durante {dias} días")
    return "\n".join(lineas)


# ---------- Análisis del ciclo ----------

def gastos_ciclo(inicio, fin):
    """(gastos, ingresos, ¿con movimientos?) entre inicio (incluido) y fin (excluido)."""
    hay = datos.valor("SELECT COUNT(*) FROM movimientos WHERE fecha >= ?", (inicio - timedelta(days=3)).isoformat())
    if hay:
        gastos, ingresos = movimientos.gastos_e_ingresos(inicio, fin)
        return gastos, ingresos, True
    # Sin movimientos: saldo al empezar + ingresos registrados − saldo actual.
    ingresos = datos.valor("SELECT COALESCE(SUM(importe), 0) FROM ingresos WHERE fecha >= ? AND fecha < ?",
                           inicio.isoformat(), fin.isoformat())
    antes = total_en(inicio)
    ahora = saldo_actual()
    if antes is None or not ahora:
        return 0.0, ingresos, False
    return max(0.0, round(antes + ingresos - ahora["total"], 2)), ingresos, False


def total_en(d):
    """Suma de saldos guardados en la fecha más cercana a `d` (en o después)."""
    fecha = datos.valor("SELECT MIN(fecha) FROM saldos WHERE fecha >= ?", d.isoformat())
    if not fecha:
        return None
    return datos.valor("SELECT SUM(importe) FROM saldos WHERE fecha = ?", fecha)


def datos_ciclo(d=None):
    d = d or hoy()
    inicio, proximo = ciclo.inicio(d), ciclo.proximo_cobro(d)
    transcurridos = max(1, (d - inicio).days + 1)
    duracion = max(transcurridos, (proximo - inicio).days)
    gastos, ingresos, con_movimientos = gastos_ciclo(inicio, d + timedelta(days=1))
    medio = gastos / transcurridos
    # Para proyectar se usa el gasto «normal»: sin compras puntuales grandes ni pagos ya apuntados.
    puntuales = 0.0
    if con_movimientos:
        umbral = movimientos.umbral_gasto_grande()
        pagados = {round(p["importe"], 2) for p in datos.todos("SELECT importe FROM pagos WHERE fecha >= ?",
                                                                 inicio.isoformat())}
        for m in movimientos.entre(inicio, d + timedelta(days=1)):
            if m["importe"] < 0 and (-m["importe"] >= umbral or round(-m["importe"], 2) in pagados):
                puntuales += -m["importe"]
    normal = max(0.0, gastos - puntuales) / transcurridos
    proyeccion = gastos + normal * max(0, duracion - transcurridos)
    anterior = ciclo.inicio_anterior(d)
    gastos_antes, _, _ = gastos_ciclo(anterior, min(inicio, anterior + timedelta(days=transcurridos)))
    return {"inicio": inicio, "proximo": proximo, "transcurridos": transcurridos, "duracion": duracion,
            "gastos": gastos, "ingresos": ingresos, "medio": medio, "normal": normal, "proyeccion": proyeccion,
            "gastos_anterior": gastos_antes, "con_movimientos": con_movimientos}


def texto_ciclo():
    c = datos_ciclo()
    lineas = [f"📆 <b>Ciclo actual</b> ({fecha_corta(c['inicio'])} – {fecha_corta(c['proximo'] - timedelta(days=1))})",
              f"Día {c['transcurridos']} de ~{c['duracion']} · faltan {ciclo.dias_hasta_cobro()} días para el cobro", "",
              f"💶 Ingresos: <b>{euros(c['ingresos'])}</b>",
              f"💸 Gastado: <b>{euros(c['gastos'])}</b>  (~{euros_cortos(c['medio'])}/día)"]
    if c["transcurridos"] >= 3:
        lineas.append(f"🔮 A tu ritmo normal, al final del ciclo: ~{euros_cortos(c['proyeccion'])}")
    if c["ingresos"] > 0:
        ahorro = (c["ingresos"] - c["gastos"]) / c["ingresos"]
        lineas.append(f"🐷 Tasa de ahorro: <b>{ahorro:.0%}</b>")
    if c["gastos_anterior"] > 0:
        cambio = (c["gastos"] - c["gastos_anterior"]) / c["gastos_anterior"]
        flecha = "🔺" if cambio > 0.02 else ("🔻" if cambio < -0.02 else "➖")
        lineas.append(f"{flecha} {abs(cambio):.0%} {'más' if cambio > 0 else 'menos'} que el ciclo anterior a estas alturas")
    presupuesto = config.importe("PRESUPUESTO_CICLO")
    if presupuesto:
        usado = c["gastos"] / presupuesto
        lineas += ["", f"{semaforo(usado)} Presupuesto: {barra(usado, 10)} {usado:.0%} de {euros_cortos(presupuesto)}"]
    top = movimientos.por_categoria(c["inicio"], hoy() + timedelta(days=1))[:3] if c["con_movimientos"] else []
    if top:
        lineas += ["", "Donde más gastas: " + " · ".join(f"{CATEGORIAS.get(cat, cat)} {euros_cortos(t)}" for cat, t in top)]
    if not c["con_movimientos"]:
        lineas.append("\n<i>Calculado con la diferencia de saldo: se afinará con los movimientos.</i>")
    return "\n".join(lineas)


def texto_presupuesto():
    presupuesto = config.importe("PRESUPUESTO_CICLO")
    c = datos_ciclo()
    if not presupuesto:
        return ("🎯 <b>Presupuesto del ciclo</b>\n\nAún no has puesto un límite de gasto por ciclo.\n"
                f"Llevas gastado {euros(c['gastos'])} en este ciclo.\nPulsa «✏️ Cambiar» para ponerlo.")
    usado = c["gastos"] / presupuesto
    queda = presupuesto - c["gastos"]
    dias = ciclo.dias_hasta_cobro()
    lineas = ["🎯 <b>Presupuesto del ciclo</b>", "",
              f"{semaforo(usado)} {barra(usado)} {usado:.0%}",
              f"Gastado {euros(c['gastos'])} de {euros(presupuesto)}"]
    if queda >= 0:
        lineas.append(f"Te quedan <b>{euros(queda)}</b> → ~{euros_cortos(queda / dias)}/día durante {dias} días")
    else:
        lineas.append(f"🔴 Te has pasado <b>{euros(-queda)}</b>")
    if c["transcurridos"] >= 3 and c["proyeccion"] > presupuesto and queda >= 0:
        lineas.append(f"⚠️ A este ritmo acabarías el ciclo en {euros(c['proyeccion'])}")
    return "\n".join(lineas)


def texto_categorias(dias=None):
    if not movimientos.hay_movimientos():
        return "🧩 <b>Categorías</b>\n\nAún no hay movimientos. Se descargan en la actualización diaria."
    if dias:
        desde, titulo = hoy() - timedelta(days=dias - 1), f"últimos {dias} días"
    else:
        desde, titulo = ciclo.inicio(), "este ciclo"
    lista = movimientos.por_categoria(desde, hoy() + timedelta(days=1))
    if not lista:
        return f"🧩 <b>Gastos por categoría</b> ({titulo})\n\nSin gastos todavía."
    total = sum(t for _, t in lista)
    lineas = [f"🧩 <b>Gastos por categoría</b> ({titulo})", f"Total: <b>{euros(total)}</b>", ""]
    for cat, t in lista[:8]:
        lineas.append(f"{CATEGORIAS.get(cat, cat)}\n{barra(t / lista[0][1], 10)} {euros_cortos(t)} ({t / total:.0%})")
    if len(lista) > 8:
        resto = sum(t for _, t in lista[8:])
        lineas.append(f"Resto: {euros_cortos(resto)}")
    return "\n".join(lineas)


def texto_semana(d=None):
    d = d or hoy()
    if not movimientos.hay_movimientos():
        return "📅 <b>Tu semana</b>\n\nAún no hay movimientos para analizar."
    fin = d + timedelta(days=1)
    esta, _ = movimientos.gastos_e_ingresos(fin - timedelta(days=7), fin)
    pasada, _ = movimientos.gastos_e_ingresos(fin - timedelta(days=14), fin - timedelta(days=7))
    lineas = ["📅 <b>Tus últimos 7 días</b>", "", f"💸 Gastado: <b>{euros(esta)}</b>  (~{euros_cortos(esta / 7)}/día)"]
    if pasada > 0:
        cambio = (esta - pasada) / pasada
        lineas.append(f"{'🔺' if cambio > 0 else '🔻'} {abs(cambio):.0%} {'más' if cambio > 0 else 'menos'} que la semana anterior")
    top = movimientos.por_categoria(fin - timedelta(days=7), fin)[:3]
    if top:
        lineas.append("Top: " + " · ".join(f"{CATEGORIAS.get(c, c)} {euros_cortos(t)}" for c, t in top))
    por_dia = {}
    for m in movimientos.entre(fin - timedelta(days=7), fin):
        if m["importe"] < 0:
            por_dia[m["fecha"]] = por_dia.get(m["fecha"], 0) + -m["importe"]
    if por_dia:
        dia, total = max(por_dia.items(), key=lambda x: x[1])
        from formato import DIAS_SEMANA
        lineas.append(f"Día de más gasto: {DIAS_SEMANA[date.fromisoformat(dia).weekday()]} ({euros_cortos(total)})")
    presupuesto = config.importe("PRESUPUESTO_CICLO")
    if presupuesto:
        usado = datos_ciclo(d)["gastos"] / presupuesto
        lineas.append(f"\n🎯 Presupuesto del ciclo: {semaforo(usado)} {usado:.0%} usado")
    return "\n".join(lineas)


def serie_saldo(dias=30):
    """[(fecha, saldo total al final del día)] de los últimos `dias` días.

    Con movimientos se reconstruye hacia atrás desde el último saldo guardado; sin ellos, se usan
    los saldos guardados de cada día.
    """
    s = saldo_actual()
    if not s:
        return []
    ancla = date.fromisoformat(s["fecha"])  # el saldo de las 00:00 de este día = final del día anterior
    fin = ancla - timedelta(days=1)
    if movimientos.hay_movimientos():
        movs = datos.todos("SELECT fecha, importe FROM movimientos WHERE fecha > ? AND fecha <= ?",
                           (fin - timedelta(days=dias)).isoformat(), fin.isoformat())
        serie = []
        for n in range(dias - 1, -1, -1):
            dia = fin - timedelta(days=n)
            posteriores = sum(m["importe"] for m in movs if m["fecha"] > dia.isoformat())
            serie.append((dia, round(s["total"] - posteriores, 2)))
        return serie
    filas = datos.todos("SELECT fecha, SUM(importe) AS total FROM saldos WHERE fecha > ? GROUP BY fecha ORDER BY fecha",
                        (ancla - timedelta(days=dias)).isoformat())
    return [(date.fromisoformat(f["fecha"]) - timedelta(days=1), round(f["total"], 2)) for f in filas]


def texto_evolucion(dias=30):
    serie = serie_saldo(dias)
    if len(serie) < 2:
        return "📈 <b>Evolución del saldo</b>\n\nAún no hay suficientes datos. Se irá completando con los días."
    minimo = min(serie, key=lambda x: x[1])
    maximo = max(serie, key=lambda x: x[1])
    cambio = serie[-1][1] - serie[0][1]
    return "\n".join([f"📈 <b>Evolución del saldo</b> (últimos {dias} días)", "",
                      f"Ahora: <b>{euros(serie[-1][1])}</b>  ({euros(cambio, signo=True)} en {dias} días)",
                      f"⬆️ Máximo: {euros(maximo[1])} ({fecha_corta(maximo[0])})",
                      f"⬇️ Mínimo: {euros(minimo[1])} ({fecha_corta(minimo[0])})"])


def suscripciones_sin_apuntar():
    """Cargos mensuales detectados en el banco que aún no están apuntados como suscripción o fijo."""
    if not movimientos.hay_movimientos():
        return []
    apuntadas = {movimientos.normalizar(d["nombre"]) for d in deudas.activas("debo") if d["tipo"] in ("fijo", "suscripcion")}
    resultado = []
    for s in movimientos.suscripciones(hoy()):
        nombre = movimientos.normalizar(s["nombre"])
        if not any(a and (a in nombre or nombre in a) for a in apuntadas):
            resultado.append(s)
    return resultado[:8]


def texto_suscripciones():
    apuntadas = [d for d in deudas.activas("debo") if d["tipo"] == "suscripcion"]
    detectadas = suscripciones_sin_apuntar()
    lineas = ["🔁 <b>Suscripciones</b>", ""]
    if apuntadas:
        total = sum(d["importe"] for d in apuntadas)
        lineas.append("📺 <b>Apuntadas</b> (con recordatorio el día de cobro):")
        lineas += [f"• {e(d['nombre'])}: {euros(d['importe'])}/mes · día {d['dia']}" for d in apuntadas]
        lineas += [f"Total: <b>{euros(total)}/mes</b> ({euros_cortos(total * 12)} al año)", ""]
    if detectadas:
        lineas.append("🔍 <b>Detectadas en tu banco</b> (pulsa para apuntarlas con su día de cobro):")
        lineas += [f"• {e(s['nombre'])}: ~{euros(s['importe'])}/mes (último cargo {s['ultimo'][8:10]}/{s['ultimo'][5:7]})"
                   for s in detectadas]
        lineas.append("")
    if not apuntadas and not detectadas:
        lineas.append("No tienes suscripciones apuntadas ni he detectado cargos que se repitan cada mes.")
        lineas.append("Puedes apuntarlas en 💳 Deudas › ➕ Nueva › 📺 Suscripción.")
    else:
        lineas.append("💡 ¿Usas todas? Cancelar una que no usas es ahorro seguro.")
    return "\n".join(lineas)


def texto_movimientos(cantidad=10):
    lista = movimientos.ultimos(cantidad)
    if not lista:
        return "🧾 <b>Últimos movimientos</b>\n\nAún no hay movimientos."
    lineas = ["🧾 <b>Últimos movimientos</b>", ""]
    for m in lista:
        nombre = m["contraparte"] or m["descripcion"] or "—"
        icono = CATEGORIAS.get(m["categoria"], "💶").split(" ")[0] if m["importe"] < 0 else "💶"
        lineas.append(f"{m['fecha'][8:10]}/{m['fecha'][5:7]} {icono} {e(nombre[:28])}: <b>{euros(m['importe'], signo=True)}</b>")
    return "\n".join(lineas)


# ---------- Deudas y metas ----------

def cuando_se_paga(deuda):
    if deuda["tipo"] in ("fijo", "suscripcion", "plazos"):
        m = deudas.modo(deuda)
        return {"dia": f"día {deuda['dia']}", "cobro": "al cobrar", "sin": "sin día fijo"}.get(m, "")
    if deuda["tipo"] == "cobro":
        return "pago único al cobrar"
    if deuda["tipo"] == "sin_fecha":
        return "sin día de pago"
    return f"día de pago {fecha_corta(date.fromisoformat(deuda['fecha']))}"


def linea_deuda(deuda):
    icono = deudas.TIPOS[deuda["tipo"]].split(" ")[0]
    nombre = e(deuda["nombre"])
    if deuda["tipo"] == "plazos":
        queda, cuotas = deudas.restante(deuda)
        return (f"{icono} {nombre}: quedan {euros(queda)} · {cuotas} cuota{'s' if cuotas != 1 else ''} de "
                f"{euros_cortos(deuda['cuota'])} · {cuando_se_paga(deuda)}")
    if deuda["tipo"] in ("fijo", "suscripcion"):
        periodo_txt = " cada cobro" if deudas.modo(deuda) == "cobro" else "/mes"
        return f"{icono} {nombre}: {euros(deuda['importe'])}{periodo_txt} · {cuando_se_paga(deuda)}"
    return f"{icono} {nombre}: {euros(deuda['importe'])} · {cuando_se_paga(deuda)}"


def texto_deudas():
    debo, deben = deudas.activas("debo"), deudas.activas("me_deben")
    if not debo and not deben:
        return ("💳 <b>Deudas y pagos</b>\n\nNo tienes nada apuntado.\n"
                "Pulsa «➕ Nueva» para apuntar lo que debes (deudas, plazos, gastos fijos, suscripciones) "
                "o lo que te deben.")
    lineas = ["💳 <b>Deudas y pagos</b>"]
    if debo:
        pendientes = deudas.pendientes()
        lineas += ["", "💸 <b>LO QUE DEBES</b>"] + [linea_deuda(d) for d in debo]
        lineas.append(f"Este ciclo te toca pagar: <b>{euros(sum(i['importe'] for i in pendientes))}</b>")
        total = sum(deudas.restante(d)[0] for d in debo if d["tipo"] not in ("fijo", "suscripcion"))
        if total:
            lineas.append(f"Deuda pendiente (sin gastos fijos ni suscripciones): {euros(total)}")
        atrasadas = [i for i in pendientes if i["atrasada"]]
        if atrasadas:
            lineas.append(f"⚠️ {len(atrasadas)} pago(s) sin confirmar: márcalos si ya los hiciste.")
    if deben:
        lineas += ["", "🤝 <b>LO QUE TE DEBEN</b>"] + [linea_deuda(d) for d in deben]
        lineas.append(f"Total que te deben: <b>{euros(sum(deudas.restante(d)[0] for d in deben))}</b>")
        if [d for d in deben if d["tipo"] == "sin_fecha"]:
            lineas.append("💡 Ponles día de pago y te recordaré que te tienen que pagar.")
    return "\n".join(lineas)


def texto_deuda(deuda):
    te_deben = deudas.me_deben(deuda)
    lineas = [f"{deudas.TIPOS[deuda['tipo']].split(' ')[0]} <b>{e(deuda['nombre'])}</b> · "
              f"{'lo que te deben' if te_deben else 'lo que debes'}",
              deudas.TIPOS[deuda["tipo"]].split(" ", 1)[1], ""]
    if deuda["tipo"] == "plazos":
        queda, cuotas = deudas.restante(deuda)
        pagado = deudas.pagado_total(deuda)
        fraccion = pagado / deuda["importe"] if deuda["importe"] else 1
        ultima = round(queda - deuda["cuota"] * (cuotas - 1), 2) if cuotas else 0
        verbo = "Te ha pagado" if te_deben else "Pagado"
        lineas += [f"{barra(fraccion)} {fraccion:.0%}  {verbo} {euros(pagado)} de {euros(deuda['importe'])}",
                   f"Quedan <b>{euros(queda)}</b> · {cuotas} cuota{'s' if cuotas != 1 else ''}"
                   + (f" (la última {euros(ultima)})" if cuotas > 1 and abs(ultima - deuda["cuota"]) > 0.004 else ""),
                   f"Cuota: {euros(deuda['cuota'])} · {cuando_se_paga(deuda)}"]
        fin = deudas.fecha_fin(deuda)
        if fin:
            lineas.append(f"Termina: {MESES[fin.month - 1]} {fin.year} (estimado)")
        lineas.append(f"Si una cuota no se paga en su mes: {deudas.SI_NO_PAGA[deuda['si_no_paga']]}")
    elif deuda["tipo"] in ("fijo", "suscripcion"):
        lineas.append(f"{euros(deuda['importe'])} · {cuando_se_paga(deuda)}")
    else:
        lineas.append(f"Importe: <b>{euros(deuda['importe'])}</b> · {cuando_se_paga(deuda)}")
    proximo = deudas.proximo_pago(deuda)
    if proximo and deuda["tipo"] in deudas.MENSUALES:
        cuando = "en tu próximo cobro" if proximo[1] is None else fecha_corta(proximo[0])
        lineas.append(f"Próximo pago: {cuando} ({euros(proximo[2])})")
    if proximo or deuda["tipo"] in ("fecha", "plazos"):
        (h1, m1), (h2, m2) = config.franja_deudas()
        lineas.append(f"🔔 Recordatorios entre las {h1:02d}:{m1:02d} y las {h2:02d}:{m2:02d} hasta que lo confirmes")
    if deuda["aplazamientos"]:
        lineas.append(f"📅 Aplazada {deuda['aplazamientos']} vez/veces")
    historial = [p for p in deudas.pagos(deuda["id"]) if p["periodo"] != deudas.INICIAL][-4:]
    if historial:
        lineas.append(f"Últimos {'cobros' if te_deben else 'pagos'}: " + ", ".join(
            f"{p['fecha'][8:10]}/{p['fecha'][5:7]} {euros_cortos(p['importe'])}" for p in historial))
    saltadas = deudas.saltos(deuda["id"])
    if saltadas:
        lineas.append("Cuotas no pagadas: " + ", ".join(
            f"{deudas.nombre_periodo(p)} → {'pasada al mes siguiente' if d == 'pasar' else 'junto con la siguiente'}"
            for p, d in sorted(saltadas.items())))
    return "\n".join(lineas)


def linea_meta(meta):
    p = metas.progreso(meta)
    return (f"🎯 <b>{e(meta['nombre'])}</b>\n{barra(p['fraccion'])} {p['fraccion']:.0%}  "
            f"{euros_cortos(p['ahorrado'])} / {euros_cortos(p['objetivo'])}\n{p['estado']}")


def texto_metas():
    lista = metas.activas()
    if not lista:
        texto = "🎯 <b>Metas de ahorro</b>\n\nAún no tienes metas. Pulsa «➕ Nueva meta»: por ejemplo «Viaje a Japón: 2.000 € para agosto»."
    else:
        texto = "🎯 <b>Metas de ahorro</b>\n\n" + "\n\n".join(linea_meta(m) for m in lista)
    hechas = metas.completadas()[:3]
    if hechas:
        texto += "\n\n🏆 Conseguidas: " + ", ".join(e(m["nombre"]) for m in hechas)
    return texto


def texto_meta(meta):
    """Ficha de una meta: progreso, aportación de cada ciclo, recordatorio, ritmo real y fecha estimada."""
    p = metas.progreso(meta)
    seguimiento = "vinculada a tu cuenta" if meta["uid"] else "aportaciones manuales"
    cuenta = next((c for c in consultas.cuentas() if c["uid"] == meta["uid"]), None)
    if cuenta:
        seguimiento += f" «{e(consultas.nombre_cuenta(cuenta))}»"
    icono = "🛟" if meta["especial"] == "colchon" else "🎯"
    lineas = [f"{icono} <b>{e(meta['nombre'])}</b>", f"<i>{seguimiento}</i>", "",
              f"{barra(p['fraccion'], 15)} {p['fraccion']:.0%}",
              f"{euros(p['ahorrado'])} de {euros(p['objetivo'])}"]
    if p["falta"] > 0:
        lineas.append(f"Faltan {euros(p['falta'])} · {p['meses']} mes(es) → lo justo: <b>{euros_cortos(p['mensual'])}/mes</b>")
        if meta["especial"] != "colchon":
            lineas.append(f"Fecha: {fecha_corta(p['limite'])} {p['limite'].year}")
    lineas.append(p["estado"])
    if p["falta"] > 0 and meta["activa"] == metas.ACTIVA:
        modo = (f"✍️ fija de {euros_cortos(meta['aporte_fijo'])}" if meta["aporte_modo"] == "fija" and meta["aporte_fijo"]
                else "🧮 la necesaria para llegar a tiempo")
        if meta["prioridad"]:
            lineas.append(f"🥇 Prioridad {meta['prioridad']}")
        if meta["tramo_aporte"] >= 0:
            tras = ("después sube lo necesario para llegar a su fecha" if meta["tramo_despues"] == "recuperar"
                    else "después vuelve a su cuota normal (fecha aplazada)")
            espera = metas.describir_hasta(meta["tramo_hasta"])
            estado_tramo = "⏸️ Ahora" if metas.en_espera(meta) else "✅ Terminó la espera"
            lineas.append(f"{estado_tramo}: {euros_cortos(meta['tramo_aporte'])} por cobro {espera}; {tras}")
        lineas += ["", f"💶 Aportación de cada cobro: {modo}",
                   f"⏰ Te lo recuerdo {metas.describir_recordar(meta)}, cada día hasta que lo confirmes"]
        estado = metas.estado_ciclo(meta)
        if estado:
            lineas.append("✅ Este ciclo: " + ("no aportas (lo saltaste)" if estado["estado"] == "saltado"
                                               else f"{euros(estado['importe'])} confirmados"))
        else:
            lineas.append(f"⏳ Este ciclo: falta apartar <b>{euros(metas.aporte_previsto(meta))}</b>")
        ritmo = metas.ritmo_real(meta)
        estimada = metas.fecha_estimada(meta)
        lineas.append(f"📈 Ritmo real: {euros_cortos(ritmo)}/mes · "
                      + (f"llegarías en {MESES[estimada.month - 1]} {estimada.year}" if estimada
                         else "a este ritmo no llegas"))
    return "\n".join(lineas)


# ---------- Resúmenes automáticos ----------

def texto_resumen_ciclo_cerrado(inicio, fin):
    gastos, ingresos, _ = gastos_ciclo(inicio, fin)
    lineas = [f"📆 <b>Resumen del ciclo {fecha_corta(inicio)} – {fecha_corta(fin - timedelta(days=1))}</b>", "",
              f"💶 Ingresos: {euros(ingresos)}", f"💸 Gastos: {euros(gastos)}"]
    if ingresos:
        lineas.append(f"🐷 Ahorro: {euros(ingresos - gastos)} ({(ingresos - gastos) / ingresos:.0%})")
    top = movimientos.por_categoria(inicio, fin)[:3]
    if top:
        lineas.append("Top: " + " · ".join(f"{CATEGORIAS.get(c, c)} {euros_cortos(t)}" for c, t in top))
    return "\n".join(lineas)


def plan_cobro(importe=None, d=None):
    """Reparto del salario del ciclo: pagos, metas, colchón y lo que queda para gastar."""
    import colchon
    d = d or hoy()
    salario = ciclo.ultimo_salario(d)
    if importe is None:
        importe = salario["importe"] if salario else 0.0
    fecha_cobro = date.fromisoformat(salario["fecha"]) if salario else ciclo.inicio(d)
    pendientes = deudas.pendientes(d)
    atrasado = [i for i in pendientes if i["vence"] < fecha_cobro]
    del_ciclo = [i for i in pendientes if i["vence"] >= fecha_cobro]
    fijos = [i for i in del_ciclo if i["deuda"]["tipo"] in ("fijo", "suscripcion")]
    cuotas = [i for i in del_ciclo if i["deuda"]["tipo"] not in ("fijo", "suscripcion")]
    aportes = [(m, metas.pendiente_ciclo(m, d)) for m in metas.activas()]
    aportes = [(m, x) for m, x in aportes if x > 0]
    total = lambda lista: round(sum(i["importe"] for i in lista), 2)  # noqa: E731
    salidas = total(fijos) + total(cuotas) + total(atrasado) + sum(x for _, x in aportes)
    queda = round(importe - salidas, 2)
    dias = ciclo.dias_hasta_cobro(d)
    return {"importe": importe, "fecha": fecha_cobro, "fijos": fijos, "cuotas": cuotas, "atrasado": atrasado,
            "aportes": aportes, "queda": queda, "dias": dias, "por_dia": round(queda / dias, 2) if dias else queda,
            "cobrar": deudas.por_cobrar(d), "colchon": colchon.activo()}


def texto_al_cobrar(importe=None):
    """Plan completo del cobro. Nada se da por pagado ni por movido: cada cosa se recuerda hasta confirmarla."""
    p = plan_cobro(importe)
    nombres = {c["uid"]: consultas.nombre_cuenta(c) for c in consultas.cuentas()}
    lineas = [f"💶 <b>¡Cobrado! {euros(p['importe'])}</b> · plan del ciclo de {MESES[p['fecha'].month - 1]}", ""]

    def bloque(titulo, items):
        if items:
            lineas.append(f"{titulo}: <b>−{euros(sum(i['importe'] for i in items))}</b>")
            lineas.extend(f"   • {e(i['deuda']['nombre'])} {euros_cortos(i['importe'])} ({cuando(i)})" for i in items)

    def cuando(item):
        if item["deuda"]["tipo"] == "cobro" or deudas.modo(item["deuda"]) == "cobro":
            return "al cobrar"
        return fecha_corta(item["vence"])

    bloque("⚠️ Atrasado de antes", p["atrasado"])
    bloque("🏠 Gastos fijos y suscripciones", p["fijos"])
    bloque("💳 Cuotas y deudas", p["cuotas"])
    if p["aportes"]:
        lineas.append(f"🎯 Mover a tus metas: <b>−{euros(sum(x for _, x in p['aportes']))}</b>")
        for meta, importe in p["aportes"]:
            icono = "🛟" if meta["especial"] == "colchon" else "→"
            destino = f"a «{e(nombres.get(meta['uid'], 'su cuenta'))}»" if meta["uid"] else "(apartar)"
            lineas.append(f"   {icono} {e(meta['nombre'])} {euros_cortos(importe)} {destino}")
    lineas += ["──────────", f"💸 <b>Te quedan para gastar: {euros(p['queda'])}</b>"]
    if p["queda"] >= 0:
        lineas.append(f"   ≈ {euros_cortos(p['por_dia'])}/día durante {p['dias']} días")
        presupuesto = config.importe("PRESUPUESTO_CICLO")
        if presupuesto:
            icono = "🟢" if p["queda"] >= presupuesto else "🟡"
            lineas.append(f"   {icono} Tu presupuesto de gasto es {euros_cortos(presupuesto)}")
    else:
        lineas += [f"🔴 <b>No llega: te faltan {euros(-p['queda'])}.</b> Opciones:",
                   "   • Aplazar algún pago (📅 Aplazar en sus recordatorios).",
                   "   • Este mes no aportar a alguna meta (⏭️ Este mes no).",
                   "   • Pagar una cuota de otra cantidad (💸 Otra cantidad)."]
    if p["cobrar"]:
        lineas.append(f"\n🤝 Además te tienen que pagar {euros(sum(i['importe'] for i in p['cobrar']))} (no se cuenta).")
    try:
        import proyeccion
        resumen = proyeccion.resumen_corto()
        if resumen:
            lineas.append(f"\n{resumen}")
    except Exception:  # la proyección es un extra: nunca impide enviar el plan
        logging.getLogger("detalle").exception("No se pudo calcular la proyección del plan")
    (h1, m1), (h2, m2) = config.franja_deudas()
    lineas.append(f"\n<i>Nada se da por hecho: marca lo que ya hayas pagado y movido. Lo demás te lo recuerdo "
                  f"cada día entre las {h1:02d}:{m1:02d} y las {h2:02d}:{m2:02d} hasta que lo confirmes.</i>")
    return "\n".join(lineas)
