"""Textos del bot: saldo, saldo neto, análisis del ciclo, categorías, semana, deudas y metas.

Todo se calcula al momento con lo guardado en la última actualización: nunca se pregunta al banco.
Los mensajes son HTML de Telegram y cortos (unas 10 líneas), con barras y semáforos.
"""
import html
from datetime import date, timedelta

import ciclo
import config
import consultas
import datos
import deudas
import metas
import movimientos
from formato import barra, euros, euros_cortos, fecha_corta, semaforo
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


def puedes_gastar(neto, d=None):
    """(€ al día, días hasta el cobro) descontando lo que falta apartar para las metas."""
    d = d or hoy()
    dias = ciclo.dias_hasta_cobro(d)
    reservar = sum(metas.pendiente_ciclo(m, d) for m in metas.activas() if not m["uid"])
    return max(0.0, round((neto - reservar) / dias, 2)), dias


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
                numero = deudas.periodos(deuda).index(i["periodo"]) + 1
                detalle = f"cuota {numero}/{deuda['cuotas_total']}"
            else:
                detalle = deudas.TIPOS[deuda["tipo"]].split(" ", 1)[1].lower()
            aviso = " ⚠️ atrasado" if i["atrasada"] else f" · {fecha_corta(i['vence'])}"
            lineas.append(f"   • {e(deuda['nombre'])} ({detalle}{aviso}): {euros(i['importe'])}")
    else:
        lineas.append("− Nada pendiente de pagar este ciclo ✅")
    lineas.append(f"= <b>Saldo neto: {euros(neto)}</b>")
    comprometido = deudas.comprometido_proximo_cobro()
    if comprometido:
        lineas.append(f"\n⏭️ Comprometido del próximo cobro: {euros(sum(d['importe'] for d in comprometido))} "
                      f"({', '.join(e(d['nombre']) for d in comprometido)})")
    reservar = sum(metas.pendiente_ciclo(m) for m in metas.activas() if not m["uid"])
    if reservar:
        lineas.append(f"🎯 Para tus metas conviene apartar este ciclo: {euros(reservar)}")
    me_deben = [d for d in deudas.activas() if d["tipo"] == "me_deben"]
    if me_deben:
        lineas.append(f"🤝 Te deben: {euros(sum(d['importe'] for d in me_deben))} (no se suma)")
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


def texto_suscripciones():
    if not movimientos.hay_movimientos():
        return "🔁 <b>Suscripciones</b>\n\nAún no hay movimientos para detectarlas."
    lista = movimientos.suscripciones(hoy())
    if not lista:
        return "🔁 <b>Suscripciones</b>\n\nNo he detectado cargos que se repitan cada mes."
    total = sum(s["importe"] for s in lista)
    lineas = ["🔁 <b>Pagos que se repiten cada mes</b>", ""]
    lineas += [f"• {e(s['nombre'])}: {euros(s['importe'])}/mes" for s in lista[:10]]
    lineas += ["", f"Total: <b>{euros(total)}/mes</b> ({euros_cortos(total * 12)} al año)",
               "💡 ¿Usas todas? Cancelar una que no usas es ahorro seguro."]
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

def linea_deuda(deuda):
    falta, cuotas = deudas.restante(deuda)
    proximo = deudas.proximo_pago(deuda)
    if deuda["tipo"] == "me_deben":
        return f"🤝 {e(deuda['nombre'])}: te debe {euros(falta)}"
    if deuda["tipo"] == "plazos":
        texto = f"🔁 {e(deuda['nombre'])}: {euros(deuda['cuota'])}/mes · quedan {cuotas} ({euros_cortos(falta)})"
    elif deuda["tipo"] == "fijo":
        texto = f"🏠 {e(deuda['nombre'])}: {euros(deuda['importe'])}/mes"
    elif deuda["tipo"] == "cobro":
        texto = f"💶 {e(deuda['nombre'])}: {euros(falta)} al cobrar"
    else:
        texto = f"📅 {e(deuda['nombre'])}: {euros(falta)}"
    if proximo and deuda["tipo"] != "cobro":
        texto += f" · próximo {fecha_corta(proximo[0])}"
    return texto


def texto_deudas():
    lista = deudas.activas()
    if not lista:
        return ("💳 <b>Deudas y pagos</b>\n\nNo tienes nada apuntado.\n"
                "Pulsa «➕ Nueva» para añadir una deuda, un pago a plazos o un pago fijo (alquiler, gimnasio...).")
    pendientes = deudas.pendientes()
    debes = [d for d in lista if d["tipo"] != "me_deben"]
    total = sum(deudas.restante(d)[0] for d in debes if d["tipo"] != "fijo")
    lineas = ["💳 <b>Deudas y pagos</b>", ""]
    lineas += [linea_deuda(d) for d in lista]
    lineas += ["", f"Este ciclo te toca pagar: <b>{euros(sum(i['importe'] for i in pendientes))}</b>"]
    if total:
        lineas.append(f"Deuda total pendiente (sin fijos): {euros(total)}")
    atrasadas = [i for i in pendientes if i["atrasada"]]
    if atrasadas:
        lineas.append(f"⚠️ {len(atrasadas)} pago(s) atrasado(s): márcalos como pagados si ya los hiciste.")
    return "\n".join(lineas)


def texto_deuda(deuda):
    falta, cuotas = deudas.restante(deuda)
    lineas = [f"{deudas.TIPOS[deuda['tipo']].split(' ')[0]} <b>{e(deuda['nombre'])}</b>",
              deudas.TIPOS[deuda["tipo"]].split(" ", 1)[1], ""]
    if deuda["tipo"] == "plazos":
        pagadas = deuda["cuotas_total"] - cuotas
        lineas += [f"Cuota: {euros(deuda['cuota'])} el día {deuda['dia']}",
                   f"{barra(pagadas / deuda['cuotas_total'])} {pagadas}/{deuda['cuotas_total']} cuotas",
                   f"Falta: <b>{euros(falta)}</b> · terminas en {fecha_corta(deudas.fecha_fin(deuda))} "
                   f"{deudas.fecha_fin(deuda).year}"]
    elif deuda["tipo"] == "fijo":
        lineas.append(f"{euros(deuda['importe'])} cada mes, el día {deuda['dia']}")
    elif deuda["tipo"] == "fecha":
        lineas.append(f"Importe: <b>{euros(falta)}</b> · vence el {date.fromisoformat(deuda['fecha']):%d/%m/%Y}")
    elif deuda["tipo"] == "cobro":
        lineas.append(f"Importe: <b>{euros(falta)}</b> · se paga en cuanto cobres")
    else:
        lineas.append(f"Te debe: <b>{euros(falta)}</b>")
    proximo = deudas.proximo_pago(deuda)
    if proximo and deuda["tipo"] in ("plazos", "fijo"):
        lineas.append(f"Próximo pago: {fecha_corta(proximo[0])} ({euros(proximo[2])})")
    if deuda["aplazamientos"]:
        lineas.append(f"Aplazada {deuda['aplazamientos']} vez/veces")
    historial = deudas.pagos(deuda["id"])[-3:]
    if historial:
        lineas.append("Últimos pagos: " + ", ".join(f"{p['fecha'][8:10]}/{p['fecha'][5:7]} {euros_cortos(p['importe'])}"
                                                    for p in historial))
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
    p = metas.progreso(meta)
    seguimiento = "vinculada a tu cuenta" if meta["uid"] else "aportaciones manuales"
    cuenta = next((c for c in consultas.cuentas() if c["uid"] == meta["uid"]), None)
    if cuenta:
        seguimiento += f" «{e(consultas.nombre_cuenta(cuenta))}»"
    lineas = [f"🎯 <b>{e(meta['nombre'])}</b>", f"<i>{seguimiento}</i>", "",
              f"{barra(p['fraccion'], 15)} {p['fraccion']:.0%}",
              f"{euros(p['ahorrado'])} de {euros(p['objetivo'])}"]
    if p["falta"] > 0:
        lineas.append(f"Faltan {euros(p['falta'])} · {p['meses']} mes(es) → ahorra <b>{euros_cortos(p['mensual'])}/mes</b>")
        lineas.append(f"Fecha: {fecha_corta(p['limite'])} {p['limite'].year}")
    lineas.append(p["estado"])
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


def texto_al_cobrar():
    """Lo que toca hacer con el salario recién registrado."""
    items = deudas.pendientes()
    lineas = ["💶 <b>¡Cobrado!</b> Esto es lo que toca este ciclo:", ""]
    if items:
        lineas += [f"• {e(i['deuda']['nombre'])}: {euros(i['importe'])} ({fecha_corta(i['vence'])})" for i in items]
        lineas.append(f"Total a pagar: <b>{euros(sum(i['importe'] for i in items))}</b>")
    else:
        lineas.append("Nada pendiente de pagar ✅")
    reservas = [(m, metas.pendiente_ciclo(m)) for m in metas.activas()]
    reservas = [(m, r) for m, r in reservas if r > 0]
    if reservas:
        lineas += ["", "🎯 Para tus metas, aparta:"]
        lineas += [f"• {e(m['nombre'])}: {euros_cortos(r)}" for m, r in reservas]
    return "\n".join(lineas)
