"""📊 Análisis › 💳 Deudas: métricas, porcentajes, calendario y proyección de tus deudas.

Todo se calcula con lo apuntado y lo guardado; nunca se pregunta al banco.
Semáforo del % del salario comprometido: 🟢 < 30 %, 🟡 30–40 %, 🔴 > 40 % (referencia habitual).
"""
import html
import math
from collections import defaultdict
from datetime import date, timedelta

import analisis
import ciclo
import config
import datos
import deudas
from formato import MESES, MESES_CORTOS, barra, euros, euros_cortos, fecha_corta, sumar_meses

VERDE, AMARILLO = 0.30, 0.40


def e(texto):
    return html.escape(str(texto))


def hoy():
    return config.ahora().date()


def semaforo_compromiso(fraccion):
    return "🟢" if fraccion < VERDE else ("🟡" if fraccion <= AMARILLO else "🔴")


def mes_anio(d):
    return f"{MESES[d.month - 1]} {d.year}"


def salario_reciente():
    return datos.valor("SELECT importe FROM ingresos WHERE tipo = 'salario' ORDER BY fecha DESC, id DESC LIMIT 1")


def deuda_pendiente(deuda):
    """Dinero que falta de una deuda (los gastos fijos y suscripciones no son deuda)."""
    if deuda["tipo"] in ("fijo", "suscripcion"):
        return 0.0
    return deudas.restante(deuda)[0]


def compromiso_mensual():
    """(cuotas a plazos, gastos fijos, suscripciones) de lo que pagas cada mes."""
    plazos = fijos = subs = 0.0
    for deuda in deudas.activas("debo"):
        if deuda["tipo"] == "plazos":
            plazos += min(deuda["cuota"], deudas.restante(deuda)[0])
        elif deuda["tipo"] == "fijo":
            fijos += deuda["importe"]
        elif deuda["tipo"] == "suscripcion":
            subs += deuda["importe"]
    return round(plazos, 2), round(fijos, 2), round(subs, 2)


def puntualidad(sentido):
    """{nombre: (a tiempo, tarde, saltadas)} de las cuotas y pagos con día de pago."""
    resultado = defaultdict(lambda: [0, 0, 0])
    for deuda in datos.todos("SELECT * FROM deudas WHERE sentido = ? AND activa >= 0", sentido):
        for pago in deudas.pagos(deuda["id"]):
            if pago["periodo"] in (deudas.INICIAL,):
                continue
            if pago["periodo"] == "unico":
                if deuda["tipo"] != "fecha" or not deuda["fecha"]:
                    continue
                vence = date.fromisoformat(deuda["fecha"])
            else:
                vence = deudas.vencimiento(deuda, pago["periodo"])
            resultado[deuda["nombre"]][0 if date.fromisoformat(pago["fecha"]) <= vence else 1] += 1
        resultado[deuda["nombre"]][2] += len(deudas.saltos(deuda["id"]))
    return {k: tuple(v) for k, v in resultado.items() if sum(v)}


def pagado_en(anio, sentido):
    return datos.valor("SELECT COALESCE(SUM(p.importe), 0) FROM pagos p JOIN deudas d ON d.id = p.deuda_id "
                       "WHERE d.sentido = ? AND p.periodo != ? AND p.fecha >= ?", sentido, deudas.INICIAL, f"{anio}-01-01")


def meses_ahorrados_con_extra(deuda, extra=20):
    queda, cuotas = deudas.restante(deuda)
    return cuotas - math.ceil(queda / (deuda["cuota"] + extra) - 1e-9) if cuotas else 0


def proyeccion(meses=24):
    """[(primer día del mes, deuda pendiente al final de ese mes)] desde este mes hasta llegar a 0."""
    d = hoy()
    plan = []
    for deuda in deudas.activas("debo"):
        if deuda["tipo"] == "plazos":
            queda = deudas.restante(deuda)[0]
            proximo = deudas.proximo_pago(deuda)
            inicio = date(proximo[0].year, proximo[0].month, 1) if proximo else date(d.year, d.month, 1)
            plan.append(("plazos", queda, deuda["cuota"], inicio))
        elif deuda["tipo"] == "fecha":
            vence = date.fromisoformat(deuda["fecha"])
            plan.append(("unico", deuda["importe"], deuda["importe"], date(vence.year, vence.month, 1)))
        elif deuda["tipo"] == "cobro":
            vence = deudas.proximo_pago(deuda)[0]
            plan.append(("unico", deuda["importe"], deuda["importe"], date(vence.year, vence.month, 1)))
    serie = []
    mes = date(d.year, d.month, 1)
    for _ in range(meses):
        total = 0.0
        for tipo, queda, cuota, inicio in plan:
            pagos_hechos = 0 if mes < inicio else ((mes.year - inicio.year) * 12 + mes.month - inicio.month + 1)
            total += max(0.0, queda - cuota * pagos_hechos)
        serie.append((mes, round(total, 2)))
        if total <= 0.004:
            break
        mes = sumar_meses(mes, 1, 1)
    return serie


def texto_analisis():
    debo, deben = deudas.activas("debo"), deudas.activas("me_deben")
    if not debo and not deben:
        return "💳 <b>Análisis de deudas</b>\n\nAún no tienes deudas ni pagos apuntados."
    total_debo = round(sum(deuda_pendiente(x) for x in debo), 2)
    total_deben = round(sum(deudas.restante(x)[0] for x in deben), 2)
    con_deuda = [x for x in debo if deuda_pendiente(x) > 0]
    lineas = ["💳 <b>Análisis de deudas</b>", "",
              f"💸 Debes: <b>{euros(total_debo)}</b> ({len(con_deuda)} deuda{'s' if len(con_deuda) != 1 else ''})",
              f"🤝 Te deben: <b>{euros(total_deben)}</b> ({len(deben)})",
              f"⚖️ Balance de deudas: <b>{euros(total_deben - total_debo, signo=True)}</b>"]

    plazos, fijos, subs = compromiso_mensual()
    mensual = plazos + fijos + subs
    salario = salario_reciente()
    lineas += ["", f"📆 <b>Cada mes comprometes {euros(mensual)}</b>",
               f"   cuotas {euros_cortos(plazos)} · gastos fijos {euros_cortos(fijos)} · suscripciones {euros_cortos(subs)}"]
    if salario:
        fraccion = mensual / salario
        lineas.append(f"{semaforo_compromiso(fraccion)} Es el <b>{fraccion:.0%}</b> de tu salario "
                      f"(recomendado por debajo del 30 %)")
        if plazos:
            lineas.append(f"   Solo en cuotas de deudas: {plazos / salario:.0%} del salario")
        libre = salario - mensual
        lineas.append(f"💶 Te quedan libres {euros(libre)} de cada salario")
    if fijos + subs:
        lineas.append(f"🗓️ Gastos fijos y suscripciones al año: {euros(round((fijos + subs) * 12, 2))}")

    con_plazos = [x for x in debo if x["tipo"] == "plazos"]
    if con_plazos:
        total = sum(x["importe"] for x in con_plazos)
        pagado = sum(deudas.pagado_total(x) for x in con_plazos)
        lineas += ["", f"📉 Deudas a plazos: {barra(pagado / total if total else 1, 10)} {pagado / total:.0%} pagado "
                       f"({euros_cortos(pagado)} de {euros_cortos(total)})"]
        fines = [(deudas.fecha_fin(x), x) for x in con_plazos if deudas.fecha_fin(x)]
        if fines:
            ultimo, _ = max(fines, key=lambda f: f[0])
            meses = max(0, (ultimo.year - hoy().year) * 12 + ultimo.month - hoy().month)
            lineas.append(f"🏁 Libre de deudas a plazos en <b>{mes_anio(ultimo)}</b> ({meses} meses)")
            primero, deuda = min(fines, key=lambda f: f[0])
            lineas.append(f"🔓 En {mes_anio(primero)} terminas «{e(deuda['nombre'])}»: liberas "
                          f"{euros_cortos(deuda['cuota'])}/mes")
    saldo = analisis.saldo_actual()
    if total_debo and saldo:
        cobertura = min(1.0, saldo["total"] / total_debo)
        lineas.append(f"💰 Con tu saldo actual cubrirías el {cobertura:.0%} de lo que debes")
    if total_debo and salario:
        lineas.append(f"⏱️ Lo que debes equivale a {total_debo / salario:.1f} salarios".replace(".", ","))

    anio = hoy().year
    pagado_anio, cobrado_anio = pagado_en(anio, "debo"), pagado_en(anio, "me_deben")
    if pagado_anio or cobrado_anio:
        lineas += ["", f"🧾 En {anio}: has pagado {euros(pagado_anio)} en deudas y pagos, y te han devuelto "
                       f"{euros(cobrado_anio)}"]

    tuyos = puntualidad("debo")
    if tuyos:
        a_tiempo = sum(v[0] for v in tuyos.values())
        tarde = sum(v[1] for v in tuyos.values())
        saltadas = sum(v[2] for v in tuyos.values())
        total_p = a_tiempo + tarde
        if total_p:
            lineas += ["", f"⏰ Tu puntualidad: <b>{a_tiempo / total_p:.0%}</b> a tiempo ({a_tiempo} de {total_p})"
                           + (f" · {saltadas} cuota(s) sin pagar en su mes" if saltadas else "")]
    aplazadas = sum(x["aplazamientos"] for x in debo)
    if aplazadas:
        lineas.append(f"📅 Has aplazado pagos {aplazadas} vez/veces")
    suyos = puntualidad("me_deben")
    if suyos:
        lineas += ["", "🤝 <b>Quién te paga a tiempo</b>"]
        for nombre, (bien, mal, saltadas) in sorted(suyos.items(), key=lambda x: -(x[1][0] / max(1, sum(x[1])))):
            total_p = bien + mal + saltadas
            icono = "🟢" if bien / total_p >= 0.9 else ("🟡" if bien / total_p >= 0.6 else "🔴")
            lineas.append(f"{icono} {e(nombre)}: {bien}/{total_p} a tiempo" + (f" · {saltadas} sin pagar" if saltadas else ""))

    if con_plazos:
        orden = sorted(con_plazos, key=lambda x: deudas.restante(x)[0])
        lineas += ["", "💡 <b>Consejos</b>"]
        pequena = orden[0]
        ahorro = meses_ahorrados_con_extra(pequena)
        if ahorro > 0:
            lineas.append(f"• Pagando 20 € más al mes a «{e(pequena['nombre'])}» terminas {ahorro} mes(es) antes.")
        if len(orden) > 1:
            lineas.append("• Orden recomendado (primero la más pequeña, para quitártelas antes): "
                          + " → ".join(e(x["nombre"]) for x in orden))
    if salario and mensual / salario > AMARILLO:
        lineas.append("• Tus pagos fijos superan el 40 % del salario: evita nuevas deudas hasta terminar alguna.")
    return "\n".join(lineas)


def texto_calendario(dias=30):
    """Pagos y cobros de los próximos `dias` días (y lo atrasado), por fecha."""
    d = hoy()
    hasta = d + timedelta(days=dias)
    filas = []
    for deuda in deudas.activas():
        if deuda["tipo"] in deudas.MENSUALES:
            for item in deudas.cuotas_pendientes(deuda, hasta + timedelta(days=1)):
                filas.append((item["vence"], deuda, item["importe"]))
            if deudas.modo(deuda) == "cobro":
                proximo = deudas.proximo_pago(deuda)
                if proximo and proximo[1] is None and proximo[0] <= hasta:
                    filas.append((proximo[0], deuda, proximo[2]))
        else:
            proximo = deudas.proximo_pago(deuda)
            if proximo and proximo[0] <= hasta:
                filas.append((proximo[0], deuda, proximo[2]))
    if not filas:
        return f"📅 <b>Próximos {dias} días</b>\n\nNo tienes pagos ni cobros previstos."
    filas.sort(key=lambda f: f[0])
    lineas = [f"📅 <b>Próximos {dias} días</b>", ""]
    for vence, deuda, importe in filas:
        signo = "🤝 +" if deudas.me_deben(deuda) else "💸 −"
        cuando = "⚠️ atrasado" if vence < d else ("hoy" if vence == d else fecha_corta(vence))
        al_cobrar = " (al cobrar)" if deuda["tipo"] == "cobro" or deudas.modo(deuda) == "cobro" else ""
        lineas.append(f"{cuando}{al_cobrar}: {signo}{euros(importe)} {e(deuda['nombre'])}")
    salen = sum(i for v, x, i in filas if not deudas.me_deben(x))
    entran = sum(i for v, x, i in filas if deudas.me_deben(x))
    lineas += ["", f"Salen {euros(salen)} · te deben pagar {euros(entran)}"]
    if ciclo.proximo_cobro() <= hasta:
        lineas.append(f"💶 Próximo cobro estimado: {fecha_corta(ciclo.proximo_cobro())}")
    return "\n".join(lineas)


def etiquetas_meses(serie):
    return [f"{MESES_CORTOS[m.month - 1]} {str(m.year)[2:]}" for m, _ in serie]
