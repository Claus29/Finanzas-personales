"""Gráficos de las pantallas sencillas (v13), bajo demanda con «📊 Gráfico». Tema oscuro, como 📈 Proyección.

Cada gráfico es una tarjeta con título, subtítulo, la cifra clave, etiquetas directas y un pie con la fuente,
el periodo y los supuestos. Datos de resumen.py (los mismos que el texto de la pantalla).

Colores por función (validados con el validador de la guía de visualización, modo oscuro, superficie
#1a1a19, en este orden de apilado): fijos violeta #9085e9 · deudas naranja #d95926 · tu libre azul #3987e5 ·
metas aqua #199e70. Lo que te deben va sin relleno (contorno discontinuo). Rojo/verde/ámbar solo como estado,
siempre con texto. Las metas entre sí (gráfico de evolución) usan el orden categórico azul · naranja · aqua ·
amarillo, como mucho 4 (el resto se nombra en el pie). Sin emojis en los gráficos.
"""
import textwrap
from datetime import date

from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Patch

import graficos_oscuro as go
from graficos_oscuro import (AMARILLO, AQUA, AZUL, EJE, FUENTE, NARANJA, REJILLA, ROJO, TENUE, TINTA, TINTA_2,
                             VERDE, AVISO, euros, mes)

VIOLETA = "#9085e9"
FIJOS, DEUDAS, LIBRE, METAS = VIOLETA, NARANJA, AZUL, AQUA
NEUTRO = "#6b6a65"  # totales (lo que hay en el banco)
SERIES_METAS = (AZUL, NARANJA, AQUA, AMARILLO)


def _pie(fecha_datos, supuestos):
    """Pie de la tarjeta: fuente y supuestos, en líneas que caben en el ancho (2 como mucho para los supuestos)."""
    fuente = (f"Fuente: saldos de N26 (Enable Banking), datos del {fecha_datos:%d/%m/%Y}" if fecha_datos
              else "Fuente: tus datos del bot")
    lineas = textwrap.wrap(f"Supuestos: {supuestos}", 128)
    return "\n".join([f"{fuente} · deudas y metas apuntadas en el bot"] + lineas)


def _texto(eje, x, y, texto, color=TINTA, tam=8.5, negrita=False, **kw):
    return eje.text(x, y, texto, color=color, fontsize=tam, fontweight="bold" if negrita else "normal",
                    family=FUENTE, **kw)


def _contorno(eje, x, y0, ancho, alto, color=TINTA_2):
    """Barra sin relleno (contorno discontinuo): dinero que aún no es tuyo (lo que te deben)."""
    eje.add_patch(FancyBboxPatch((x - ancho / 2, y0), ancho, alto, boxstyle="round,pad=0,rounding_size=0.02",
                                 facecolor="none", edgecolor=color, linewidth=1.1, linestyle=(0, (3, 2)), zorder=4))


def _fecha(texto):
    return date.fromisoformat(texto) if texto else None


# =====================================================================
# 🏠 Inicio: cascada de hoy hasta el cobro
# =====================================================================

def inicio(a):
    """Cascada: banco → pagos antes del cobro → ya en metas → por mover a metas = tu libre (+ si te pagan)."""
    pasos = [("En el banco", a["banco"], "total", NEUTRO)]
    if a["total_pagos"] > 0.004:
        pasos.append(("Pagos antes\ndel cobro", -a["total_pagos"], "resta", DEUDAS))
    if a["en_metas"] > 0.004:
        pasos.append(("Ya en tus\nmetas", -a["en_metas"], "resta", METAS))
    if a["a_mover"] > 0.004:
        pasos.append(("Por mover\na metas", -a["a_mover"], "resta", METAS))
    pasos.append(("Tu libre", a["libre"], "total", LIBRE))
    libre, minimo = a["libre"], a["libre_minimo"]
    if libre < -0.004:
        estado = (ROJO, f"Te faltan {euros(-libre)}")
    elif libre < minimo - 0.004:
        estado = (AVISO, f"Por debajo de tus {euros(minimo)}")
    else:
        estado = (VERDE, "Llegas con tu libre")
    dias = a["dias"]
    figura, ejes = go._tarjeta(5.6, "Tu dinero hasta el cobro",
                               f"Del saldo de hoy a tu libre, en orden: pagos, metas y lo que queda · cobro ~{a['proximo']:%d/%m}"
                               f" ({dias} día{'s' if dias != 1 else ''})",
                               euros(libre), "tu libre ahora", estado,
                               _pie(_fecha(a["fecha_datos"]),
                                    "los pagos son los que vencen antes del próximo cobro y no has marcado; "
                                    "las metas solo reciben lo que pase de tu libre; lo que te deben no se suma"))
    eje = ejes(abajo_pulgadas=1.3, arriba_pulgadas=1.5, izq=0.1, der=0.05)
    n = len(pasos) + (1 if a["deben"] > 0.004 else 0)
    nivel, puntos = 0.0, []
    for nombre, valor, clase, color in pasos:
        if clase == "total":
            puntos.append((nombre, min(0.0, valor), max(0.0, valor), valor, color, clase))
            nivel = valor
        else:
            puntos.append((nombre, nivel + valor, nivel, valor, color, clase))
            nivel += valor
    techo = max([p[2] for p in puntos] + [minimo, libre + a["deben"], 1.0])
    suelo = min([p[1] for p in puntos] + [0.0])
    margen = (techo - suelo) * 0.16
    eje.set_xlim(-0.6, n - 0.4)
    eje.set_ylim(suelo - margen * (0.6 if suelo < 0 else 0), techo + margen)
    ancho = 0.56
    for i, (nombre, abajo, arriba, valor, color, clase) in enumerate(puntos):
        alto = arriba - abajo
        if alto > 0.004:
            go._barra(eje, i, abajo, ancho, alto, ROJO if (clase == "total" and valor < 0) else color, radio_px=4,
                      hueco_px=0)
        etiqueta = euros(valor, signo=clase == "resta") if clase == "resta" else euros(valor)
        y = arriba + margen * 0.12 if valor >= 0 or clase == "resta" else abajo - margen * 0.12
        _texto(eje, i, y, etiqueta, TINTA if clase == "total" else TINTA_2, 9.5 if clase == "total" else 8.5,
               clase == "total", ha="center", va="bottom" if (valor >= 0 or clase == "resta") else "top")
        if i < len(puntos) - 1:  # conector del nivel con la barra siguiente
            nivel_fin = abajo if clase == "resta" else valor
            eje.plot([i + ancho / 2, i + 1 - ancho / 2], [nivel_fin, nivel_fin], color=EJE, linewidth=1, zorder=2)
    if a["deben"] > 0.004:
        i = len(puntos)
        base = max(libre, 0.0) if libre >= 0 else libre
        _contorno(eje, i, base, ancho, a["deben"])
        _texto(eje, i, base + a["deben"] + margen * 0.12, f"+{euros(a['deben'])}", TINTA_2, 8.5, ha="center", va="bottom")
    if minimo > 0.004:
        eje.axhline(minimo, color=TENUE, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
        _texto(eje, n - 0.42, minimo, f"tu libre deseado {euros(minimo)}", TENUE, 7.5, ha="right", va="bottom")
    eje.axhline(0, color=EJE, linewidth=1, zorder=1)
    go._rejilla_y(eje)
    etiquetas = [p[0] for p in puntos] + (["Si te pagan\n(no cuenta)"] if a["deben"] > 0.004 else [])
    eje.set_xticks(range(n))
    eje.set_xticklabels(etiquetas, color=TINTA_2, fontsize=8, family=FUENTE)
    eje.spines["bottom"].set_visible(False)
    return go._png(figura)


def pagos(a):
    """Cada pago de antes del cobro y con el cobro, por importe, con su tipo y su fecha."""
    filas = [(i["deuda"]["nombre"], i["importe"], i["deuda"]["tipo"] in ("fijo", "suscripcion"),
              f"{'sin marcar · ' if i['atrasada'] else ''}{i['vence']:%d/%m}", "antes") for i in a["pagos"]]
    filas += [(d["nombre"], importe, d["tipo"] in ("fijo", "suscripcion"), "con el cobro", "cobro")
              for d, importe in a["con_cobro"]]
    if not filas:
        return None
    filas = filas[:14]
    alto = max(3.6, 2.2 + 0.36 * len(filas))
    antes = sum(x[1] for x in filas if x[4] == "antes")
    cobro = sum(x[1] for x in filas if x[4] == "cobro")
    figura, ejes = go._tarjeta(alto, "Tus pagos de este ciclo y del próximo cobro",
                               f"Antes del cobro: {euros(antes)} (restan ya de tu libre) · con el cobro del "
                               f"{a['proximo']:%d/%m}: {euros(cobro)}",
                               euros(antes + cobro), "en total", None,
                               _pie(_fecha(a["fecha_datos"]), "importes de cada cuota o pago; nada se da por pagado "
                                                              "hasta que lo marcas"))
    eje = ejes(abajo_pulgadas=1.0, arriba_pulgadas=1.55, izq=0.3, der=0.25)
    maximo = max(x[1] for x in filas)
    eje.set_xlim(0, maximo * 1.02)
    eje.set_ylim(len(filas) - 0.4, -0.6)
    separador = next((n for n, x in enumerate(filas) if x[4] == "cobro"), None)
    for y, (nombre, importe, fijo, cuando, grupo) in enumerate(filas):
        go._barra(eje, 0, y, 0.56, importe, FIJOS if fijo else DEUDAS, horizontal=True, radio_px=4)
        _texto(eje, maximo * 1.04, y, f"{euros(importe)}  ·  {cuando}", TINTA if grupo == "antes" else TINTA_2, 8.5,
               va="center", clip_on=False)
    if separador:
        eje.axhline(separador - 0.5, color=EJE, linewidth=1)
    eje.set_yticks(range(len(filas)))
    eje.set_yticklabels([x[0][:24] for x in filas], color=TINTA, fontsize=8.5, family=FUENTE)
    eje.xaxis.set_visible(False)
    eje.spines["bottom"].set_visible(False)
    go._leyenda(eje, [Patch(color=DEUDAS, label="Deuda o pago"), Patch(color=FIJOS, label="Gasto fijo o suscripción")],
                y=1.04)
    return go._png(figura)


# =====================================================================
# 💳 Deudas
# =====================================================================

def deudas(d, prox, fecha_datos):
    imagenes = []
    filas = d["filas"][:10]
    if filas:
        alto = max(3.6, 2.3 + 0.52 * len(filas))
        pagado_total = sum(f["pagado"] for f in filas)
        figura, ejes = go._tarjeta(alto, "Lo que debes, deuda a deuda",
                                   f"{len(d['filas'])} deuda{'s' if len(d['filas']) != 1 else ''} · "
                                   + (f"terminas en {mes(d['fin'])}" if d["fin"] else "sin fecha de fin")
                                   + " · gris: ya pagado",
                                   euros(d["total"]), "pendiente en total", None,
                                   _pie(fecha_datos, "fin estimado con la cuota actual y sin saltos; los gastos fijos "
                                                     "y suscripciones no son deuda (van aparte)"))
        eje = ejes(abajo_pulgadas=1.0, arriba_pulgadas=1.45, izq=0.27, der=0.27)
        maximo = max(f["queda"] + f["pagado"] for f in filas)
        eje.set_xlim(0, maximo * 1.02)
        eje.set_ylim(len(filas) - 0.4, -0.6)
        for y, f in enumerate(filas):
            if f["pagado"] > 0.5:
                go._barra(eje, 0, y, 0.5, f["pagado"], NEUTRO, horizontal=True, radio_px=4)
            go._barra(eje, f["pagado"], y, 0.5, f["queda"], DEUDAS, horizontal=True, radio_px=4)
            total = f["queda"] + f["pagado"]
            porcentaje = f"{f['pagado'] / total:.0%} pagado".replace("%", " %") if total else ""
            _texto(eje, maximo * 1.04, y - 0.13, f"quedan {euros(f['queda'])}", TINTA, 8.8, True, va="center",
                   clip_on=False)
            detalle = []
            if f["cuotas"]:
                detalle.append(f"{f['cuotas']} cuota{'s' if f['cuotas'] != 1 else ''}")
            if f["fin"]:
                detalle.append(f"fin {mes(f['fin'])}")
            if porcentaje and f["pagado"] > 0.5:
                detalle.append(porcentaje)
            _texto(eje, maximo * 1.04, y + 0.2, " · ".join(detalle), TENUE, 7.6, va="center", clip_on=False)
        eje.set_yticks(range(len(filas)))
        eje.set_yticklabels([f["deuda"]["nombre"][:24] for f in filas], color=TINTA, fontsize=9, family=FUENTE)
        eje.xaxis.set_visible(False)
        eje.spines["bottom"].set_visible(False)
        if pagado_total > 0.5:
            go._leyenda(eje, [Patch(color=NEUTRO, label="Ya pagado"), Patch(color=DEUDAS, label="Pendiente")], y=1.03)
        imagenes.append(go._png(figura))
    if prox:
        imagenes.append(pagos_por_cobro(prox, d, fecha_datos))
    return imagenes


def pagos_por_cobro(prox, d, fecha_datos):
    """Cuánto pagas en cada cobro (deudas + fijos) y qué parte del salario se llevan."""
    filas = prox["filas"]
    n = len(filas)
    salario = prox["salario"]
    primero = filas[0]
    sin_deudas = next((f["fecha"] for f in filas if f["deudas"] <= 0.004), None)
    k_fin = next((i for i, f in enumerate(filas) if f["fecha"] == sin_deudas), 0)
    figura, ejes = go._tarjeta(5.2, "Lo que pagas en cada cobro",
                               "Deudas y gastos fijos de cada cobro y su peso sobre el salario"
                               + (f" · último pago de deudas en {mes(filas[k_fin - 1]['fecha'])}"
                                  if sin_deudas and k_fin else ""),
                               euros(primero["deudas"] + primero["fijos"]), f"en el cobro de {mes(primero['fecha'])}",
                               None,
                               _pie(fecha_datos, f"salario {euros(salario)} en cada cobro ({prox['origen']}); "
                                                 "cuotas según el plan actual"))
    eje = ejes(abajo_pulgadas=1.05, arriba_pulgadas=1.5)
    tope = max(max(f["deudas"] + f["fijos"] for f in filas), 1) * 1.25
    eje.set_xlim(-0.6, n - 0.4)
    eje.set_ylim(0, tope)
    for i, f in enumerate(filas):
        if f["fijos"] > 0.5:
            go._barra(eje, i, 0, 0.62, f["fijos"], FIJOS, radio_px=4)
        if f["deudas"] > 0.5:
            go._barra(eje, i, f["fijos"], 0.62, f["deudas"], DEUDAS, radio_px=4)
        total = f["deudas"] + f["fijos"]
        _texto(eje, i, total + tope * 0.02, euros(total), TINTA, 7.6, True, ha="center", va="bottom")
        if salario:
            _texto(eje, i, total + tope * 0.075, f"{total / salario:.0%}".replace("%", " %"), TENUE, 7, ha="center",
                   va="bottom")
    if sin_deudas:
        k = next(i for i, f in enumerate(filas) if f["fecha"] == sin_deudas)
        if k > 0:
            eje.axvline(k - 0.5, color=TENUE, linewidth=1, linestyle=(0, (4, 3)))
            _texto(eje, k - 0.45, tope * 0.97, "sin deudas", TINTA_2, 7.8, va="top")
    go._rejilla_y(eje)
    paso = 1 if n <= 12 else 2
    eje.set_xticks(range(0, n, paso))
    eje.set_xticklabels([mes(filas[i]["fecha"]) for i in range(0, n, paso)], color=TINTA_2, fontsize=8)
    go._leyenda(eje, [Patch(color=FIJOS, label="Gastos fijos y suscripciones"), Patch(color=DEUDAS, label="Deudas"),
                      Line2D([0], [0], color="none", label="(% = parte del salario)")])
    return go._png(figura)


# =====================================================================
# 🎯 Metas
# =====================================================================

def metas(m, prox, fecha_datos):
    imagenes = []
    filas = m["filas"][:8]
    if not filas:
        return imagenes
    alto = max(3.6, 2.3 + 0.6 * len(filas))
    ahorrado = sum(f["ahorrado"] for f in filas)
    objetivo = sum(f["objetivo"] for f in filas)
    tarde = [f for f in filas if f["llega"] is None or (f["llega"] > f["limite"] and not f["meta"]["especial"])]
    estado = (VERDE, "Todas llegan a tiempo") if not tarde else (AVISO, f"{len(tarde)} llega(n) tarde")
    figura, ejes = go._tarjeta(alto, "Tus metas: cuánto llevas y cuándo llegas",
                               "En orden de prioridad · llegada estimada con lo que sobra de cada cobro",
                               f"{ahorrado / objetivo:.0%}".replace("%", " %") if objetivo else "0 %",
                               f"{euros(ahorrado)} de {euros(objetivo)}", estado,
                               _pie(fecha_datos, f"reciben lo que sobra tras pagos y tu libre ({euros(m['libre_minimo'])}); "
                                                 "sin contar lo que te deben"))
    eje = ejes(abajo_pulgadas=1.0, arriba_pulgadas=1.45, izq=0.25, der=0.3)
    eje.set_xlim(0, 1.0)
    eje.set_ylim(len(filas) - 0.4, -0.6)
    for y, f in enumerate(filas):
        go._barra(eje, 0, y, 0.42, 1.0, REJILLA, horizontal=True, radio_px=4, hueco_px=0, zorder=2)
        if f["fraccion"] > 0.002:
            go._barra(eje, 0, y, 0.42, min(1.0, f["fraccion"]), METAS, horizontal=True, radio_px=4, hueco_px=0)
        _texto(eje, 1.03, y - 0.14, f"{euros(f['ahorrado'])} / {euros(f['objetivo'])}  ({f['fraccion']:.0%})"
               .replace("%)", " %)"), TINTA, 8.6, True, va="center", clip_on=False)
        if f["llega"] is None:
            texto, color = "con lo que sobra no llega", ROJO
        elif f["meta"]["especial"]:
            texto, color = f"llegas {mes(f['llega'])}", TENUE
        elif f["llega"] <= f["limite"]:
            texto, color = f"llegas {mes(f['llega'])} · a tiempo ({mes(f['limite'])})", TENUE
        else:
            texto, color = f"llegas {mes(f['llega'])} · tu fecha {mes(f['limite'])}", AVISO
        _texto(eje, 1.03, y + 0.2, texto, color, 7.6, va="center", clip_on=False)
    eje.set_yticks(range(len(filas)))
    eje.set_yticklabels([f"{n + 1}. {f['meta']['nombre'][:22]}" for n, f in enumerate(filas)], color=TINTA, fontsize=9,
                        family=FUENTE)
    eje.xaxis.set_visible(False)
    eje.spines["bottom"].set_visible(False)
    imagenes.append(go._png(figura))
    if prox:
        evolucion = evolucion_metas(m, prox, fecha_datos)
        if evolucion:
            imagenes.append(evolucion)
    return imagenes


def evolucion_metas(m, prox, fecha_datos):
    """Lo ahorrado en cada meta cobro a cobro (simulación), con su objetivo y el mes en que llega."""
    import proyeccion as pr
    lista = [f for f in m["filas"] if f["falta"] > 0.004][:4]
    if not lista:
        return None
    llegadas = [f["llega"] for f in lista if f["llega"]]
    cobros = len(prox["filas"])
    if llegadas:
        cobros = min(36, max(cobros, 1 + sum(1 for x in prox["p"]["fechas"] if x <= max(llegadas)),
                             (max(llegadas).year - prox["filas"][0]["fecha"].year) * 12
                             + max(llegadas).month - prox["filas"][0]["fecha"].month + 2))
    p = pr.simular(contar_deben=False, cobros=cobros)
    if not p:
        return None
    fechas = [c["fecha"] for c in p["ciclos"]]
    figura, ejes = go._tarjeta(5.4, "Cómo crece cada meta",
                               f"Ahorrado acumulado en cada cobro hasta {mes(fechas[-1])} · línea discontinua: objetivo",
                               None, "", None,
                               _pie(fecha_datos, "simulación con tu salario, tus pagos y tu libre; las metas reciben "
                                                 "lo que sobra en su orden de prioridad")
                               + ("" if len(m["filas"]) <= 4 else f" · se muestran 4 de {len(m['filas'])} metas"))
    eje = ejes(abajo_pulgadas=1.05, arriba_pulgadas=1.5, der=0.2)
    x = list(range(len(fechas) + 1))
    maximo = 0.0
    for n, f in enumerate(lista):
        color = SERIES_METAS[n]
        valores = [f["ahorrado"]]
        for c in p["ciclos"]:
            valores.append(valores[-1] + c["por_meta"].get(f["meta"]["id"], (0.0, False))[0])
        valores = [min(v, f["objetivo"]) for v in valores]
        maximo = max(maximo, f["objetivo"])
        eje.plot(x, valores, color=color, linewidth=2, solid_capstyle="round", zorder=4)
        eje.axhline(f["objetivo"], color=color, linewidth=0.9, linestyle=(0, (4, 3)), alpha=0.7, zorder=2)
        llega = next((i for i, v in enumerate(valores) if v >= f["objetivo"] - 0.01), None)
        if llega is not None and llega > 0:
            eje.plot([llega], [valores[llega]], marker="o", markersize=7, color=color, markeredgecolor=go.SUPERFICIE,
                     markeredgewidth=2, zorder=5)
            _texto(eje, llega, valores[llega] * 1.03, mes(fechas[llega - 1]), TINTA_2, 7.6, ha="center", va="bottom")
        _texto(eje, x[-1] + 0.3, valores[-1], f["meta"]["nombre"][:16], TINTA, 8, va="center", clip_on=False)
    eje.set_xlim(0, x[-1])
    eje.set_ylim(0, maximo * 1.15)
    go._rejilla_y(eje)
    paso = max(1, len(fechas) // 8)
    eje.set_xticks([0] + list(range(1, len(fechas) + 1, paso)))
    eje.set_xticklabels(["hoy"] + [mes(fechas[i - 1]) for i in range(1, len(fechas) + 1, paso)], color=TINTA_2,
                        fontsize=8)
    go._leyenda(eje, [Line2D([0], [0], color=SERIES_METAS[n], linewidth=2, label=f["meta"]["nombre"][:20])
                      for n, f in enumerate(lista)])
    return go._png(figura)


# =====================================================================
# 📈 Próximos meses
# =====================================================================

def proximos(prox, fecha_datos):
    return [reparto_cobros(prox, fecha_datos), trayectoria(prox, fecha_datos)]


def reparto_cobros(prox, fecha_datos):
    """Cada cobro apilado en orden de prioridad: fijos, deudas, tu libre y metas (lo que sobra)."""
    filas = prox["filas"]
    n = len(filas)
    salario = prox["salario"]
    hueco = filas[0]["hueco"]
    figura, ejes = go._tarjeta(5.8, "En qué se va cada cobro",
                               "Orden: 1 pagos (fijos y deudas) · 2 tu libre · 3 metas con lo que sobra",
                               euros(sum(f["metas"] for f in filas)), f"a metas en {n} cobros", None,
                               _pie(fecha_datos, f"salario {euros(salario)} ({prox['origen']}); sin gastos del día a día; "
                                                 "lo que te deben va aparte (contorno) y no se suma"
                                    + (f"; las deudas de {mes(filas[0]['fecha'])} incluyen {euros(hueco)} que te "
                                       "faltaban antes del cobro" if hueco > 0.5 else "")))
    eje = ejes(abajo_pulgadas=1.05, arriba_pulgadas=1.55)
    tope = max(max(f["fijos"] + f["deudas"] + f["hueco"] + max(0, f["libre"]) + f["metas"] + f["deben"] for f in filas),
               salario) * 1.12
    eje.set_xlim(-0.6, n - 0.4)
    eje.set_ylim(0, tope)
    ancho = 0.62
    for i, f in enumerate(filas):
        base = 0.0
        for valor, color in ((f["fijos"], FIJOS), (f["deudas"] + f["hueco"], DEUDAS), (max(0.0, f["libre"]), LIBRE),
                             (f["metas"], METAS)):
            if valor > 0.5:
                go._barra(eje, i, base, ancho, valor, color, radio_px=4)
            base += valor
        if f["deben"] > 0.5:
            _contorno(eje, i, base + tope * 0.004, ancho, f["deben"])
        eje.plot([i - ancho / 2 - 0.07, i + ancho / 2 + 0.07], [salario] * 2, color=TINTA, linewidth=1.2, zorder=6)
        if f["metas"] > 0.5:
            _texto(eje, i, base + (f["deben"] if f["deben"] > 0.5 else 0) + tope * 0.02, euros(f["metas"]), TINTA, 7.4,
                   True, ha="center", va="bottom")
        if f["libre"] + f["hueco"] < -0.004 or f["estado"] == "🔴":
            _texto(eje, i, tope * 0.98, "no llega", ROJO, 7.2, True, ha="center", va="top")
    go._rejilla_y(eje)
    paso = 1 if n <= 12 else 2
    eje.set_xticks(range(0, n, paso))
    eje.set_xticklabels([mes(filas[i]["fecha"]) for i in range(0, n, paso)], color=TINTA_2, fontsize=8)
    elementos = [Patch(color=FIJOS, label="Fijos"), Patch(color=DEUDAS, label="Deudas"), Patch(color=LIBRE, label="Tu libre"),
                 Patch(color=METAS, label="Metas"), Line2D([0], [0], color=TINTA, linewidth=1.2, label="Salario")]
    if any(f["deben"] > 0.5 for f in filas):
        elementos.append(Patch(facecolor="none", edgecolor=TINTA_2, linestyle="--", label="Si te pagan"))
    go._leyenda(eje, elementos, ncol=6)
    return go._png(figura)


def trayectoria(prox, fecha_datos):
    """Deuda pendiente (baja) y dinero en metas (sube) cobro a cobro, en euros: cuándo se cruzan."""
    filas = prox["filas"]
    import resumen
    d = resumen.de_deudas()
    antes = sum(i["importe"] for i in d["antes"] if i["deuda"]["tipo"] not in ("fijo", "suscripcion"))
    deuda = [d["total"]]
    queda = d["total"] - antes
    for f in filas:
        queda = max(0.0, queda - f["deudas"])
        deuda.append(queda)
    ahorro = [sum(x["ahorrado"] for x in resumen.de_metas()["filas"])] + [f["en_metas"] for f in filas]
    x = list(range(len(filas) + 1))
    cruce = next((i for i in x if ahorro[i] >= deuda[i] and deuda[i] < deuda[0]), None)
    figura, ejes = go._tarjeta(5.2, "Tu deuda baja, tus metas suben",
                               "Deuda pendiente y dinero en tus metas después de cada cobro (euros)",
                               euros(ahorro[-1]), f"en metas en {mes(filas[-1]['fecha'])}", None,
                               _pie(fecha_datos, "mismo plan que la tabla de Próximos meses; la deuda no incluye gastos "
                                                 "fijos ni suscripciones"))
    eje = ejes(abajo_pulgadas=1.05, arriba_pulgadas=1.5, der=0.2)
    tope = max(max(deuda), max(ahorro), 1) * 1.15
    eje.fill_between(x, deuda, color=DEUDAS, alpha=0.12, linewidth=0)
    eje.fill_between(x, ahorro, color=METAS, alpha=0.12, linewidth=0)
    eje.plot(x, deuda, color=DEUDAS, linewidth=2, solid_capstyle="round", zorder=4)
    eje.plot(x, ahorro, color=METAS, linewidth=2, solid_capstyle="round", zorder=4)
    finales = [(deuda[-1], DEUDAS, "Deuda"), (ahorro[-1], METAS, "En metas")]
    for valor, color, nombre in finales:
        eje.plot([x[-1]], [valor], marker="o", markersize=7, color=color, markeredgecolor=go.SUPERFICIE,
                 markeredgewidth=2, zorder=5, clip_on=False)
    separados = abs(finales[0][0] - finales[1][0]) > tope * 0.12
    for n, (valor, color, nombre) in enumerate(finales):
        y = valor if separados else (min(f[0] for f in finales) + tope * (0.1 if n else 0.0))
        _texto(eje, x[-1] + 0.3, max(y, tope * 0.06), f"{nombre}: {euros(valor)}", TINTA, 8, va="center",
               clip_on=False)
    _texto(eje, 0.12, deuda[0], f"debes {euros(deuda[0])}", TINTA_2, 7.8, ha="left", va="bottom")
    sin_deuda = next((i for i in x if deuda[i] <= 0.004 and i > 0), None)
    if sin_deuda:
        eje.plot([sin_deuda], [0], marker="o", markersize=7, color=DEUDAS, markeredgecolor=go.SUPERFICIE,
                 markeredgewidth=2, zorder=5)
        _texto(eje, sin_deuda, tope * 0.06, f"sin deudas\n{mes(filas[sin_deuda - 1]['fecha'])}", TINTA_2, 7.6,
               ha="center", va="bottom")
    if cruce:
        eje.plot([cruce], [ahorro[cruce]], marker="o", markersize=6, color=TINTA_2, markeredgecolor=go.SUPERFICIE,
                 markeredgewidth=2, zorder=6)
        eje.plot([cruce, cruce], [ahorro[cruce], ahorro[cruce] + tope * 0.24], color=EJE, linewidth=1, zorder=3)
        _texto(eje, cruce, ahorro[cruce] + tope * 0.25, "tus metas superan a tu deuda", TINTA_2, 7.4,
               ha="left", va="bottom")
    eje.set_xlim(0, x[-1])
    eje.set_ylim(0, tope)
    go._rejilla_y(eje)
    paso = max(1, len(filas) // 8)
    eje.set_xticks([0] + list(range(1, len(filas) + 1, paso)))
    eje.set_xticklabels(["hoy"] + [mes(filas[i - 1]["fecha"]) for i in range(1, len(filas) + 1, paso)],
                        color=TINTA_2, fontsize=8)
    go._leyenda(eje, [Line2D([0], [0], color=DEUDAS, linewidth=2, label="Deuda pendiente"),
                      Line2D([0], [0], color=METAS, linewidth=2, label="Dinero en tus metas")])
    return go._png(figura)
