"""Cálculo único de las pantallas sencillas (v13): tu dinero en el orden de prioridad del usuario.

1️⃣ Pagos (inamovibles): deudas, cuotas, gastos fijos y suscripciones de antes del próximo cobro.
2️⃣ Tu libre: lo que quieres tener cada cobro (LIBRE_MINIMO). Va antes que las metas.
3️⃣ Metas: solo lo que sobra. Si a mitad de ciclo falta dinero, las metas ceden primero: lo que falte por
   mover a metas se recorta (de la última prioridad a la primera) para no tocar tu libre.

Lo que te deben nunca se suma: se muestra aparte («si te pagan…»).
Este módulo solo calcula (sin textos de Telegram): lo usan vistas.py y graficos_resumen.py.
"""
from datetime import date

import analisis
import ciclo
import colchon
import config
import deudas
import metas
import proyeccion as pr
import reparto

FIJOS = ("fijo", "suscripcion")
COBROS_PROXIMOS = 12


def hoy():
    return config.ahora().date()


def es_fijo(deuda):
    return deuda["tipo"] in FIJOS


# ---------- Hoy: hasta el próximo cobro ----------

def ahora():
    """Dinero de hoy hasta el próximo cobro, en orden: pagos → tu libre → metas. None sin saldos del banco."""
    s = analisis.saldo_actual()
    if not s:
        return None
    pagos = deudas.pendientes()
    total_pagos = round(sum(i["importe"] for i in pagos), 2)
    en_metas = colchon.dinero_en_metas()
    libre_minimo = pr.libre_minimo()
    disponible = round(s["total"] - total_pagos - en_metas, 2)  # lo que queda tras pagar (antes de metas)
    planificado = [(m, metas.pendiente_ciclo(m)) for m in reparto.orden(metas.activas())]
    planificado = [(m, x) for m, x in planificado if x > 0.004]
    # Las metas solo reciben lo que esté por encima de tu libre (decisión 2A).
    puedes = max(0.0, disponible - libre_minimo)
    mover = []
    for meta, importe in planificado:  # por orden de prioridad: la última es la primera en ceder
        parte = round(min(importe, puedes), 2)
        puedes -= parte
        mover.append((meta, importe, parte))
    a_mover = round(sum(x for _, _, x in mover), 2)
    cobrar = deudas.por_cobrar()
    proximo = ciclo.proximo_cobro()
    return {"banco": s["total"], "cuentas": s["cuentas"], "fecha_datos": s["fecha"],
            "pagos": pagos, "total_pagos": total_pagos,
            "en_metas": en_metas, "disponible": disponible, "libre_minimo": libre_minimo,
            "metas": mover, "planificado": round(sum(x for _, x in planificado), 2), "a_mover": a_mover,
            "recortado": round(sum(x for _, x in planificado) - a_mover, 2),
            "libre": round(disponible - a_mover, 2),
            "deben": round(sum(i["importe"] for i in cobrar), 2), "cobrar": cobrar,
            "proximo": proximo, "dias": ciclo.dias_hasta_cobro(),
            "con_cobro": deudas.comprometido_proximo_cobro()}


# ---------- Deudas ----------

def fin_de_deuda(deuda):
    """Fecha estimada del último pago de una deuda (None para gastos fijos y suscripciones)."""
    if es_fijo(deuda) or deudas.me_deben(deuda):
        return None
    if deuda["tipo"] == "plazos":
        return deudas.fecha_fin(deuda)
    proximo = deudas.proximo_pago(deuda)
    return proximo[0] if proximo else None


def de_deudas():
    """Lo que debes: total de deudas reales (sin fijos), cuándo terminas, fijos al mes y lo que te deben."""
    debo = deudas.activas("debo")
    reales = [d for d in debo if not es_fijo(d)]
    filas = []
    for d in reales:
        queda, cuotas = deudas.restante(d)
        if queda <= 0.004:
            continue
        numero, total_cuotas = deudas.numero_cuota(d) if d["tipo"] == "plazos" else (None, None)
        filas.append({"deuda": d, "queda": queda, "cuotas": cuotas, "numero": numero, "total_cuotas": total_cuotas,
                      "pagado": deudas.pagado_total(d) if d["tipo"] == "plazos" else 0.0,
                      "importe": d["importe"], "fin": fin_de_deuda(d), "proximo": deudas.proximo_pago(d)})
    fijos = [d for d in debo if es_fijo(d)]
    fines = [f["fin"] for f in filas if f["fin"]]
    me_deben = deudas.activas("me_deben")
    return {"filas": sorted(filas, key=lambda f: (f["fin"] or date.max, -f["queda"])),
            "total": round(sum(f["queda"] for f in filas), 2), "fin": max(fines) if fines else None,
            "fijos": fijos, "fijos_mes": round(sum(deudas.cuota(d) for d in fijos), 2),
            "antes": deudas.pendientes(), "con_cobro": deudas.comprometido_proximo_cobro(),
            "proximo": ciclo.proximo_cobro(),
            "deben_total": round(sum(deudas.restante(d)[0] for d in me_deben), 2),
            "deben_ciclo": round(sum(i["importe"] for i in deudas.por_cobrar()), 2)}


# ---------- Próximos meses ----------

def proximos(cobros=None):
    """Cada cobro: entra, deudas, fijos, tu libre y metas (lo que te deben NO se suma: va aparte, decisión 4A).
    None si aún no hay salario. Las fechas de llegada de las metas salen de la misma simulación."""
    p = pr.simular(contar_deben=False, cobros=cobros)
    if not p:
        return None
    por_ciclo, _, _ = pr.calendario_deudas(p["fechas"])
    filas = []
    for c in p["ciclos"]:
        t = c["totales"]
        deben = round(sum(i for _, i, cl in por_ciclo[c["k"]] if cl == "deben"), 2)
        filas.append({"fecha": c["fecha"], "entra": c["salario"], "deudas": round(t["cuotas"] + t["unicos"], 2),
                      "fijos": round(t["fijos"] + t["subs"], 2), "hueco": c["hueco"],
                      "libre": round(c["libre"] - c["hueco"], 2), "metas": t["metas"], "deben": deben,
                      "acumulado": c["acumulado"], "estado": c["estado"], "aportes": c["aportes"],
                      "en_metas": c["en_metas"]})
    largo = pr.simular(contar_deben=False, cobros=120)
    llegadas = {e[4]: e[0] for e in largo["eventos"] if e[2] == "meta"} if largo else {}
    ya = {m["id"] for m in metas.activas() if metas.ahorrado(m) >= m["objetivo"] - 0.004}
    return {"p": p, "filas": filas, "salario": p["salario"], "origen": p["origen"], "minimo": p["minimo"],
            "reparto": p["reparto"], "puente": p["puente"], "hueco": p["hueco"],
            "llegadas": {m["id"]: (hoy() if m["id"] in ya else llegadas.get(m["id"])) for m in metas.activas()},
            "fin_deudas": de_deudas()["fin"], "deben_total": round(sum(f["deben"] for f in filas), 2)}


def veredicto(prox):
    """(estado, texto) en una frase: 🔴 algún cobro no llega, 🟡 tu libre baja de lo que quieres, 🟢 todo cuadra."""
    filas = prox["filas"]
    rojo = next((f for f in filas if f["libre"] + f["hueco"] < -0.004 or f["acumulado"] < -0.004), None)
    if prox["hueco"] > 0.004:
        return "🔴", f"hasta el próximo cobro te faltan {prox['hueco']:.2f} €".replace(".", ",")
    if rojo:
        falta = -min(rojo["libre"], rojo["acumulado"])
        return "🔴", f"en {pr.mes_largo(rojo['fecha'])} no llegas: te faltan {falta:.2f} €".replace(".", ",")
    amarillo = next((f for f in filas if f["libre"] < prox["minimo"] - 0.5), None)
    if amarillo:
        return "🟡", (f"en {pr.mes_largo(amarillo['fecha'])} tu libre baja a {amarillo['libre']:.2f} € "
                      f"(quieres {prox['minimo']:.2f} €)").replace(".", ",")
    return "🟢", "todo cuadra: pagas tus deudas y tienes tu libre en cada cobro"


# ---------- Metas ----------

def de_metas():
    """Metas en orden de prioridad, con progreso, lo de este ciclo y cuándo llegas (misma simulación que 📈)."""
    ahora_ = ahora()
    mover = {m["id"]: (plan, parte) for m, plan, parte in (ahora_["metas"] if ahora_ else [])}
    prox = proximos()
    llegadas = prox["llegadas"] if prox else {}
    filas = []
    for m in reparto.orden(metas.activas()):
        p = metas.progreso(m)
        fila_ciclo = metas.estado_ciclo(m)
        filas.append({"meta": m, "ahorrado": p["ahorrado"], "objetivo": p["objetivo"], "fraccion": p["fraccion"],
                      "falta": p["falta"], "limite": p["limite"], "llega": llegadas.get(m["id"]),
                      "plan": mover.get(m["id"], (0.0, 0.0))[0], "mover": mover.get(m["id"], (0.0, 0.0))[1],
                      "hecho": fila_ciclo["importe"] if fila_ciclo and fila_ciclo["estado"] != "saltado" else None,
                      "saltado": bool(fila_ciclo and fila_ciclo["estado"] == "saltado")})
    return {"filas": filas, "reparto": reparto.activo(), "modo": reparto.modo(),
            "libre_minimo": pr.libre_minimo(), "conseguidas": metas.completadas()[:3]}
