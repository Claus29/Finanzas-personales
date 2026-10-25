"""Gráficos de 📈 Proyección en tema oscuro (PNG para Telegram).

Cada imagen es una «tarjeta»: cabecera (título, subtítulo y la cifra clave), el gráfico y un pie
con los datos usados. Barras con las puntas redondeadas y 2 px de separación, rejilla muy tenue,
etiquetas directas selectivas y leyenda cuando hay más de una serie.

Colores (validados con el validador de la guía de visualización, modo oscuro, superficie #1a1a19):
series en orden fijo azul · naranja · aqua · amarillo; el rojo de alerta va siempre con texto.
Las fuentes de los gráficos no tienen emojis: los textos se pasan sin ellos.
"""
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from formato import MESES_CORTOS  # noqa: E402

PLANO = "#0d0d0d"
SUPERFICIE = "#1a1a19"
TINTA = "#f0efec"
TINTA_2 = "#c3c2b7"
TENUE = "#898781"
REJILLA = "#2c2c2a"
EJE = "#383835"
AZUL, NARANJA, AQUA, AMARILLO = "#3987e5", "#d95926", "#199e70", "#c98500"
SERIES = (AZUL, NARANJA, AQUA, AMARILLO)
ROJO, VERDE, AVISO = "#d03b3b", "#0ca30c", "#fab219"
ANCHO, DPI = 8.0, 200


def _fuente():
    disponibles = {f.name for f in font_manager.fontManager.ttflist}
    return next((f for f in ("Segoe UI", "Inter", "Helvetica Neue", "Arial", "DejaVu Sans") if f in disponibles),
                "DejaVu Sans")


FUENTE = _fuente()


def euros(v, signo=False):
    texto = f"{abs(round(v)):,} €".replace(",", ".")
    if v < -0.5:
        return "−" + texto
    return ("+" if signo and v > 0.5 else "") + texto


def mes(d):
    return f"{MESES_CORTOS[d.month - 1]} {str(d.year)[2:]}"


# ---------- Tarjeta ----------

def _tarjeta(alto, titulo, subtitulo, cifra=None, etiqueta_cifra="", estado=None, pie=""):
    """Figura con la tarjeta, la cabecera y el pie. Devuelve (figura, función para crear ejes)."""
    figura = plt.figure(figsize=(ANCHO, alto), dpi=DPI)
    figura.patch.set_facecolor(PLANO)
    margen_x, margen_y = 0.025, 0.02 * 5 / alto
    figura.patches.append(FancyBboxPatch((margen_x, margen_y), 1 - 2 * margen_x, 1 - 2 * margen_y,
                                         boxstyle="round,pad=0,rounding_size=0.018", transform=figura.transFigure,
                                         facecolor=SUPERFICIE, edgecolor="#262624", linewidth=1, zorder=-10))
    pulgada = 1 / alto  # fracción de la altura de la figura que ocupa una pulgada
    arriba = 1 - margen_y - 0.30 * pulgada
    izquierda = 0.065
    figura.text(izquierda, arriba, titulo, color=TINTA, fontsize=15, fontweight="bold", va="top", family=FUENTE)
    figura.text(izquierda, arriba - 0.32 * pulgada, subtitulo, color=TINTA_2, fontsize=9.5, va="top", family=FUENTE)
    if cifra is not None:
        figura.text(1 - izquierda, arriba + 0.02 * pulgada, cifra, color=TINTA, fontsize=19, fontweight="bold",
                    va="top", ha="right", family=FUENTE)
        figura.text(1 - izquierda, arriba - 0.36 * pulgada, etiqueta_cifra, color=TENUE, fontsize=8.5,
                    va="top", ha="right", family=FUENTE)
    if estado:
        color, texto = estado
        figura.text(1 - izquierda, arriba - 0.56 * pulgada, "●", color=color, fontsize=9, va="top", ha="right",
                    family=FUENTE)
        figura.text(1 - izquierda - 0.022, arriba - 0.56 * pulgada, texto, color=TINTA_2, fontsize=8.5,
                    va="top", ha="right", family=FUENTE)
    if pie:
        figura.text(izquierda, margen_y + 0.16 * pulgada, pie, color=TENUE, fontsize=7.5, va="bottom", family=FUENTE)

    def ejes(abajo_pulgadas=0.75, arriba_pulgadas=1.35, izq=0.11, der=0.06):
        eje = figura.add_axes([izq, abajo_pulgadas * pulgada, 1 - izq - der,
                               1 - (abajo_pulgadas + arriba_pulgadas) * pulgada])
        eje.set_facecolor("none")
        for lado in ("top", "right", "left"):
            eje.spines[lado].set_visible(False)
        eje.spines["bottom"].set_color(EJE)
        eje.tick_params(colors=TENUE, labelsize=8.5, length=0, pad=6)
        for etiqueta in eje.get_xticklabels() + eje.get_yticklabels():
            etiqueta.set_family(FUENTE)
        return eje
    return figura, ejes


def _png(figura):
    salida = io.BytesIO()
    figura.savefig(salida, format="png", facecolor=PLANO, dpi=DPI)
    plt.close(figura)
    salida.seek(0)
    return salida


def _por_pixel(eje):
    """(unidades de x por píxel, unidades de y por píxel) del eje (con los límites ya fijados)."""
    caja = eje.get_window_extent()
    x0, x1 = eje.get_xlim()
    y0, y1 = eje.get_ylim()
    return abs(x1 - x0) / caja.width, abs(y1 - y0) / caja.height


def _barra(eje, x, y0, ancho, alto, color, radio_px=5, horizontal=False, hueco_px=2, zorder=3):
    """Barra con las esquinas redondeadas y un hueco de 2 px respecto a la siguiente (en datos)."""
    px_x, px_y = _por_pixel(eje)
    if horizontal:  # x = inicio en el eje x, y0 = centro en y; ancho = grosor en y; alto = largo en x
        hueco = hueco_px * px_x
        largo = max(0.0, alto - hueco)
        if largo <= 0:
            return
        caja = FancyBboxPatch((x + hueco / 2, y0 - ancho / 2), largo, ancho,
                              boxstyle=f"round,pad=0,rounding_size={min(radio_px * px_x, largo / 2, ancho / 2 * px_x / px_y)}",
                              mutation_aspect=px_y / px_x, facecolor=color, edgecolor="none", zorder=zorder)
    else:
        hueco = hueco_px * px_y
        alto_real = max(0.0, alto - hueco)
        if alto_real <= 0:
            return
        caja = FancyBboxPatch((x - ancho / 2, y0 + hueco / 2), ancho, alto_real,
                              boxstyle=f"round,pad=0,rounding_size={min(radio_px * px_x, ancho / 2)}",
                              mutation_aspect=px_y / px_x, facecolor=color, edgecolor="none", zorder=zorder)
    eje.add_patch(caja)


def _leyenda(eje, elementos, y=1.06):
    leyenda = eje.legend(handles=elementos, loc="lower left", bbox_to_anchor=(0, y), ncol=len(elementos),
                         frameon=False, fontsize=8.5, handlelength=0.9, handleheight=0.9, columnspacing=1.6,
                         borderaxespad=0, prop={"family": FUENTE, "size": 8.5})
    for texto in leyenda.get_texts():
        texto.set_color(TINTA_2)


def _rejilla_y(eje, formato=euros):
    eje.grid(axis="y", color=REJILLA, linewidth=0.8)
    eje.set_axisbelow(True)
    eje.yaxis.set_major_formatter(FuncFormatter(lambda v, _: formato(v)))
    eje.tick_params(axis="y", labelcolor=TENUE)


def _estado(p):
    if not p["sostenible"]:
        return ROJO, "No sostenible"
    if any(x["estado"] == "🟡" for x in p["ciclos"]):
        return AVISO, "Justo"
    return VERDE, "Sostenible"


# ---------- 1. Reparto de cada cobro ----------

def reparto(p, pie):
    ciclos = p["ciclos"]
    n = len(ciclos)
    alto = 5.6
    falta_alguno = any(c["libre"] < 0 for c in ciclos)
    figura, ejes = _tarjeta(alto, "Reparto de cada cobro",
                            "En qué se va cada salario y lo que te queda libre"
                            + (" · en rojo, lo que falta" if falta_alguno else ""),
                            euros(ciclos[0]["libre"]), f"libres en el cobro de {mes(ciclos[0]['fecha'])}",
                            _estado(p), pie)
    eje = ejes(abajo_pulgadas=0.85, arriba_pulgadas=1.45)
    partes = []
    for c in ciclos:
        t = c["totales"]
        partes.append([t["fijos"] + t["subs"], t["cuotas"] + t["unicos"], t["metas"], max(0.0, c["libre"])])
    entra = [c["salario"] + c["totales"]["deben"] for c in ciclos]
    tope = max(max(sum(x) for x in partes), max(entra)) * 1.12
    eje.set_xlim(-0.6, n - 0.4)
    eje.set_ylim(0, tope)
    ancho = 0.62 if n <= 12 else 0.7
    for i, segmentos in enumerate(partes):
        base = 0.0
        for valor, color in zip(segmentos, SERIES):
            if valor > 0.5:
                _barra(eje, i, base, ancho, valor, color, radio_px=4 if n <= 18 else 2)
            base += valor
        # Lo que entra ese cobro (salario + lo que te devuelven)
        eje.plot([i - ancho / 2 - 0.06, i + ancho / 2 + 0.06], [entra[i]] * 2, color=TINTA, linewidth=1.2,
                 solid_capstyle="round", zorder=5)
        libre = ciclos[i]["libre"]
        etiquetar = n <= 12 or i in (0, n - 1) or libre == min(c["libre"] for c in ciclos)
        if libre < 0:
            eje.text(i, max(base, entra[i]) + tope * 0.022, euros(libre), ha="center", va="bottom",
                     color=ROJO, fontsize=7.6 if n <= 10 else 6.8, fontweight="bold", family=FUENTE)
        elif etiquetar:
            eje.text(i, max(base, entra[i]) + tope * 0.022, euros(libre), ha="center", va="bottom", color=TINTA,
                     fontsize=7.6 if n <= 12 else 7, fontweight="bold", family=FUENTE)
    _rejilla_y(eje)
    paso = 1 if n <= 12 else (2 if n <= 24 else 3)
    eje.set_xticks(range(0, n, paso))
    eje.set_xticklabels([mes(ciclos[i]["fecha"]) for i in range(0, n, paso)], color=TINTA_2, fontsize=8)
    elementos = [Patch(color=AZUL, label="Fijos y suscripciones"), Patch(color=NARANJA, label="Cuotas y pagos"),
                 Patch(color=AQUA, label="Metas"), Patch(color=AMARILLO, label="Libre"),
                 Line2D([0], [0], color=TINTA, linewidth=1.2, label="Lo que entra")]
    _leyenda(eje, elementos)
    return _png(figura)


# ---------- 2. Dinero libre acumulado ----------

def acumulado(p, pie, hoy):
    ciclos = p["ciclos"]
    fechas = [hoy] + [c["fecha"] for c in ciclos]
    libre = [p["puente"]] + [c["acumulado"] for c in ciclos]
    en_metas = [ciclos[0]["en_metas"] - ciclos[0]["totales"]["metas"]] + [c["en_metas"] for c in ciclos]
    alto = 5.4
    figura, ejes = _tarjeta(alto, "Tu dinero, cobro a cobro",
                            "Dinero libre acumulado si pagas todo y apartas lo de tus metas",
                            euros(libre[-1], signo=False), f"libres en {mes(fechas[-1])}", _estado(p), pie)
    eje = ejes(abajo_pulgadas=0.85, arriba_pulgadas=1.55, izq=0.12, der=0.12)
    con_metas = any(v > 0.5 for v in en_metas)
    todos = libre + (en_metas if con_metas else [])
    abajo, arriba = min(0.0, min(todos)), max(todos)
    margen = (arriba - abajo) * 0.12 or 100
    eje.set_ylim(abajo - (margen if abajo < 0 else 0), arriba + margen)
    eje.set_xlim(fechas[0], fechas[-1])
    if abajo < 0:
        eje.axhspan(eje.get_ylim()[0], 0, color=ROJO, alpha=0.10, linewidth=0, zorder=0)
        eje.text(fechas[0], eje.get_ylim()[0], "  ! por debajo de 0: no llegarías", color=ROJO, fontsize=8,
                 va="bottom", family=FUENTE)
    eje.axhline(0, color=EJE, linewidth=1, zorder=1)
    eje.fill_between(fechas, [max(0.0, v) for v in libre], 0, color=AZUL, alpha=0.16, linewidth=0, zorder=2)
    eje.plot(fechas, libre, color=AZUL, linewidth=2.4, solid_capstyle="round", zorder=4, label="Dinero libre")
    eje.scatter(fechas[1:], libre[1:], s=16, color=AZUL, edgecolors=SUPERFICIE, linewidths=1.2, zorder=5)
    if con_metas:
        eje.plot(fechas, en_metas, color=AQUA, linewidth=2, solid_capstyle="round", zorder=4, label="En tus metas")
    # Hitos (máx. 5): rombo sobre la línea y texto corto, alternando arriba y abajo
    hitos = [e for e in p["eventos"] if e[2] in ("deuda", "meta")][:5]
    for n, (fecha, k, tipo, texto, _) in enumerate(hitos):
        y = libre[k]
        eje.scatter([fecha], [y], s=46, marker="D", color=TINTA if tipo == "deuda" else AQUA, edgecolors=SUPERFICIE,
                    linewidths=1.5, zorder=6)
        corto = texto.split("→")[0].replace("«", "").replace("»", "").strip()
        corto = corto[0].upper() + corto[1:]
        arriba_texto = n % 2 == 0
        sube = libre[min(k + 1, len(libre) - 1)] >= libre[max(k - 1, 0)]
        # Si la línea sube, arriba-izquierda / abajo-derecha; si baja, arriba-derecha / abajo-izquierda.
        izquierda_texto = arriba_texto == sube
        eje.annotate(corto, (fecha, y), xytext=(-8 if izquierda_texto else 8, 18 if arriba_texto else -20),
                     textcoords="offset points", ha="right" if izquierda_texto else "left",
                     va="bottom" if arriba_texto else "top",
                     color=TINTA_2, fontsize=7.4,
                     family=FUENTE, zorder=7,
                     arrowprops={"arrowstyle": "-", "color": EJE, "linewidth": 0.8, "shrinkA": 0, "shrinkB": 4})
    # Cifras finales
    eje.text(fechas[-1], libre[-1], f"  {euros(libre[-1])}", color=TINTA, fontsize=9, fontweight="bold",
             va="center", ha="left", family=FUENTE, clip_on=False)
    if con_metas:
        separacion = abs(en_metas[-1] - libre[-1]) / (eje.get_ylim()[1] - eje.get_ylim()[0])
        desplazamiento = 0 if separacion > 0.06 else (-12 if en_metas[-1] < libre[-1] else 12)
        eje.annotate(f"  {euros(en_metas[-1])}", (fechas[-1], en_metas[-1]), xytext=(0, desplazamiento),
                     textcoords="offset points", color=TINTA_2, fontsize=8.5, va="center", ha="left",
                     family=FUENTE, annotation_clip=False)
    _rejilla_y(eje)
    eje.xaxis.set_major_formatter(FuncFormatter(lambda v, _: mes(mdates.num2date(v).date())))
    eje.xaxis.set_major_locator(mdates.MonthLocator(interval=1 if len(ciclos) <= 12 else (2 if len(ciclos) <= 24 else 3)))
    eje.tick_params(axis="x", labelcolor=TINTA_2)
    elementos = [Line2D([0], [0], color=AZUL, linewidth=2.4, label="Dinero libre")]
    if con_metas:
        elementos.append(Line2D([0], [0], color=AQUA, linewidth=2, label="Ahorrado en metas"))
    elementos.append(Line2D([0], [0], marker="D", color="none", markerfacecolor=TINTA, markersize=6,
                            label="Hito (deuda terminada / meta conseguida)"))
    _leyenda(eje, elementos)
    return _png(figura)


# ---------- 3. Calendario de deudas y metas ----------

def calendario(filas, pie, hoy, hasta):
    """filas: [(nombre, tipo «deuda»|«meta»|«deben», fin estimado o None, fecha límite o None)]."""
    filas = filas[:12]
    alto = max(3.6, 1.95 + 0.42 * len(filas))
    figura, ejes = _tarjeta(alto, "Cuándo terminas cada cosa",
                            "Deudas a plazos, lo que te deben y tus metas, desde hoy",
                            None, "", None, pie)
    eje = ejes(abajo_pulgadas=0.8, arriba_pulgadas=1.5, izq=0.26, der=0.12)
    final = max([hasta] + [f for _, _, f, _ in filas if f] + [l for _, _, _, l in filas if l])
    eje.set_xlim(mdates.date2num(hoy) - 5, mdates.date2num(final) + 20)
    eje.set_ylim(len(filas) - 0.4, -0.6)
    colores = {"deuda": NARANJA, "meta": AQUA, "deben": AZUL}
    for y, (nombre, tipo, fin, limite) in enumerate(filas):
        inicio = mdates.date2num(hoy)
        if fin:
            dentro = fin if not limite or fin <= limite else limite
            _barra(eje, inicio, y, 0.46, mdates.date2num(dentro) - inicio, colores[tipo], horizontal=True, radio_px=4)
            if limite and fin > limite:
                _barra(eje, mdates.date2num(limite), y, 0.46, mdates.date2num(fin) - mdates.date2num(limite), ROJO,
                       horizontal=True, radio_px=4)
            despues = max(fin, limite) if limite and (limite - fin).days < 45 else fin
            eje.text(mdates.date2num(despues) + 8, y, mes(fin) + ("  ! tarde" if limite and fin > limite else ""),
                     va="center", color=ROJO if limite and fin > limite else TINTA_2, fontsize=8, family=FUENTE)
        else:
            eje.text(inicio + 4, y, "no llegas a tu ritmo actual", va="center", color=ROJO, fontsize=8, family=FUENTE)
        if limite:
            x = mdates.date2num(limite)
            eje.plot([x, x], [y - 0.36, y + 0.36], color=TINTA, linewidth=1.6, solid_capstyle="round", zorder=6)
    eje.set_yticks(range(len(filas)))
    eje.set_yticklabels([n[:26] for n, _, _, _ in filas], color=TINTA, fontsize=9, family=FUENTE)
    eje.grid(axis="x", color=REJILLA, linewidth=0.8)
    eje.set_axisbelow(True)
    meses = (final.year - hoy.year) * 12 + final.month - hoy.month
    eje.xaxis.set_major_locator(mdates.MonthLocator(interval=1 if meses <= 8 else (2 if meses <= 16 else (3 if meses <= 30 else 6))))
    eje.xaxis.set_major_formatter(FuncFormatter(lambda v, _: mes(mdates.num2date(v).date())))
    eje.tick_params(axis="x", labelcolor=TINTA_2)
    elementos = [Patch(color=NARANJA, label="Deuda"), Patch(color=AZUL, label="Te deben"), Patch(color=AQUA, label="Meta"),
                 Line2D([0], [0], color=TINTA, linewidth=1.6, label="Fecha límite"), Patch(color=ROJO, label="Pasa de la fecha")]
    usados = {t for _, t, _, _ in filas}
    elementos = [e for e in elementos if {"Deuda": "deuda", "Te deben": "deben", "Meta": "meta"}.get(e.get_label(), "x") in usados
                 or e.get_label() in ("Fecha límite", "Pasa de la fecha")]
    if not any(l for _, _, _, l in filas):
        elementos = [e for e in elementos if e.get_label() not in ("Fecha límite", "Pasa de la fecha")]
    elif not any(f and l and f > l for _, _, f, l in filas):
        elementos = [e for e in elementos if e.get_label() != "Pasa de la fecha"]
    _leyenda(eje, elementos)
    return _png(figura)


# ---------- 4. Tu próximo cobro en una barra ----------

def cobro(c, pie):
    """Una barra al 100 % con el reparto del próximo cobro y la referencia 50/30/20."""
    t = c["totales"]
    entra = c["salario"] + t["deben"]
    partes = [("Fijos y suscripciones", t["fijos"] + t["subs"], AZUL), ("Cuotas y pagos", t["cuotas"] + t["unicos"], NARANJA),
              ("Metas", t["metas"], AQUA), ("Libre", max(0.0, c["libre"]), AMARILLO)]
    total = max(entra, sum(v for _, v, _ in partes)) or 1
    alto = 4.3
    figura, ejes = _tarjeta(alto, f"Tu cobro de {mes(c['fecha'])}",
                            f"Entran {euros(entra)}" + (f" (salario {euros(c['salario'])} + te devuelven {euros(t['deben'])})"
                                                        if t["deben"] else " de salario"),
                            euros(c["libre"]), "te quedan libres", None, pie)
    eje = ejes(abajo_pulgadas=1.5, arriba_pulgadas=1.45, izq=0.065, der=0.065)
    eje.set_xlim(0, total)
    eje.set_ylim(-0.8, 0.75)
    inicio = 0.0
    for nombre, valor, color in partes:
        if valor > 0.5:
            _barra(eje, inicio, 0, 0.8, valor, color, horizontal=True, radio_px=6, hueco_px=3)
            if valor / total < 0.09:
                eje.text(inicio + valor / 2, 0.52, euros(valor), ha="center", va="bottom", color=TINTA_2,
                         fontsize=8.5, family=FUENTE, zorder=6)
            else:
                tinta = PLANO if color == AMARILLO else "#ffffff"
                eje.text(inicio + valor / 2, 0.1, euros(valor), ha="center", va="center", color=tinta, fontsize=10,
                         fontweight="bold", family=FUENTE, zorder=6)
                eje.text(inicio + valor / 2, -0.17, f"{valor / entra:.0%}".replace("%", " %"), ha="center", va="center",
                         color=tinta, fontsize=8, family=FUENTE, zorder=6, alpha=0.9)
        inicio += valor
    if c["libre"] < 0:
        # Marca de lo que entra (fuera de la barra) y, debajo, el tramo que no se puede pagar
        eje.plot([entra, entra], [0.42, 0.56], color=TINTA, linewidth=2, solid_capstyle="round", zorder=7)
        eje.text(entra, 0.58, f"entra {euros(entra)}", ha="center", va="bottom", color=TINTA, fontsize=8, family=FUENTE)
        eje.plot([entra, total], [-0.5, -0.5], color=ROJO, linewidth=2, solid_capstyle="round", zorder=7)
        eje.plot([entra, entra], [-0.42, -0.5], color=ROJO, linewidth=2, zorder=7)
        eje.text((entra + total) / 2, -0.56, f"! faltan {euros(-c['libre'])}", ha="center", va="top", color=ROJO,
                 fontsize=9, fontweight="bold", family=FUENTE)
    eje.axis("off")
    # Leyenda y referencia 50/30/20 debajo
    necesidades = (t["fijos"] + t["subs"] + t["cuotas"] + t["unicos"]) / entra if entra else 0
    ahorro = t["metas"] / entra if entra else 0
    libre = c["libre"] / entra if entra else 0
    filas = [(f"Necesidades (fijos, suscripciones, cuotas): {necesidades:.0%}", "ideal: 50 % o menos",
              VERDE if necesidades <= 0.5 else AVISO),
             (f"Metas (ahorro): {ahorro:.0%}", "ideal: 20 % o más", VERDE if 0.2 <= ahorro and libre >= 0 else AVISO),
             (f"Libre para ti: {libre:.0%}", "referencia: 30 %", ROJO if libre < 0 else (VERDE if libre >= 0.1 else AVISO))]
    pulgada = 1 / alto
    for n, (texto, ideal, color) in enumerate(filas):
        y = (1.25 - n * 0.27) * pulgada
        figura.text(0.08, y, "●", color=color, fontsize=9, va="center", family=FUENTE)
        figura.text(0.105, y, texto.replace("%", " %"), color=TINTA, fontsize=9, va="center", family=FUENTE)
        figura.text(0.935, y, ideal, color=TENUE, fontsize=8.5, va="center", ha="right", family=FUENTE)
    leyenda = figura.legend(handles=[Patch(color=color, label=n) for n, v, color in partes if v > 0.5],
                            loc="center left", bbox_to_anchor=(0.058, 1 - 1.18 * pulgada), ncol=4, frameon=False,
                            handlelength=0.9, handleheight=0.9, columnspacing=1.4, prop={"family": FUENTE, "size": 8})
    for texto in leyenda.get_texts():
        texto.set_color(TINTA_2)
    return _png(figura)


# ---------- 5. Aportación a cada meta ----------

def metas(filas, salario, pie):
    """filas: [(nombre, aportación del próximo cobro, fin estimado, fecha límite)]."""
    filas = filas[:10]
    alto = max(3.4, 1.9 + 0.5 * len(filas))
    total = sum(x for _, x, _, _ in filas)
    figura, ejes = _tarjeta(alto, "Lo que aparta cada meta", "Aportación en el próximo cobro y % de tu salario",
                            euros(total), f"en total · {total / salario:.0%} del salario".replace("%", " %") if salario else "en total",
                            None, pie)
    eje = ejes(abajo_pulgadas=0.6, arriba_pulgadas=1.45, izq=0.26, der=0.3)
    maximo = max([x for _, x, _, _ in filas] + [1])
    eje.set_xlim(0, maximo * 1.02)
    eje.set_ylim(len(filas) - 0.4, -0.6)
    for y, (nombre, valor, fin, limite) in enumerate(filas):
        if valor > 0.5:
            _barra(eje, 0, y, 0.5, valor, AQUA, horizontal=True, radio_px=4)
        texto = f"{euros(valor)} · {valor / salario:.0%}".replace("%", " %") if salario else euros(valor)
        eje.text(maximo * 1.04, y - 0.12, texto, va="center", color=TINTA, fontsize=9, family=FUENTE, clip_on=False)
        if fin:
            tarde = limite and fin > limite
            detalle = f"llegas en {mes(fin)}" + (f" · límite {mes(limite)}" if limite else "")
            eje.text(maximo * 1.04, y + 0.2, ("! " if tarde else "") + detalle, va="center", fontsize=7.5,
                     color=ROJO if tarde else TENUE, family=FUENTE, clip_on=False)
    eje.set_yticks(range(len(filas)))
    eje.set_yticklabels([n[:26] for n, _, _, _ in filas], color=TINTA, fontsize=9, family=FUENTE)
    eje.xaxis.set_visible(False)
    eje.spines["bottom"].set_visible(False)
    return _png(figura)


# ---------- 6. Comparación (propuestas y escenarios) ----------

def comparacion(series, pie, titulo, subtitulo):
    """Lo libre en cada cobro con la configuración actual y con una propuesta. series: [(nombre, proyección)]."""
    series = series[:2]
    alto = 5.2
    base, nueva = series[0][1], series[-1][1]
    colores = (AZUL, AQUA)
    figura, ejes = _tarjeta(alto, titulo, subtitulo, euros(nueva["peor"]["libre"]), "libres en el cobro más justo",
                            _estado(nueva), pie)
    eje = ejes(abajo_pulgadas=0.85, arriba_pulgadas=1.5, izq=0.12, der=0.1)
    todos = [c["libre"] for _, p in series for c in p["ciclos"]]
    abajo, arriba = min(0.0, min(todos)), max(todos)
    margen = (arriba - abajo) * 0.14 or 100
    eje.set_ylim(abajo - (margen if abajo < 0 else 0), arriba + margen)
    if abajo < 0:
        eje.axhspan(eje.get_ylim()[0], 0, color=ROJO, alpha=0.10, linewidth=0, zorder=0)
        eje.text(base["ciclos"][0]["fecha"], eje.get_ylim()[0], "  ! no llega", color=ROJO, fontsize=8, va="bottom",
                 family=FUENTE)
    eje.axhline(0, color=EJE, linewidth=1)
    for (nombre, p), color, estilo in zip(series, colores, ("-", (0, (6, 2)))):
        fechas = [c["fecha"] for c in p["ciclos"]]
        valores = [c["libre"] for c in p["ciclos"]]
        eje.plot(fechas, valores, color=color, linewidth=2.3, linestyle=estilo, solid_capstyle="round", zorder=4)
        eje.scatter(fechas, valores, s=18, color=color, edgecolors=SUPERFICIE, linewidths=1.2, zorder=5)
    fin = base["ciclos"][-1]["fecha"]
    finales = sorted((p["ciclos"][-1]["libre"], color) for (_, p), color in zip(series, colores))
    ultima, rango = None, eje.get_ylim()[1] - eje.get_ylim()[0]
    for valor, color in finales:
        y = valor if ultima is None or valor - ultima > rango * 0.06 else ultima + rango * 0.06
        eje.text(fin, y, f"  {euros(valor)}", color=TINTA, fontsize=8.5, va="center", ha="left", family=FUENTE,
                 clip_on=False)
        ultima = y
    _rejilla_y(eje)
    fechas = [c["fecha"] for c in base["ciclos"]]
    eje.set_xlim(mdates.date2num(fechas[0]) - 8, mdates.date2num(fin) + 4)
    paso = 1 if len(fechas) <= 12 else (2 if len(fechas) <= 24 else 3)
    eje.set_xticks([mdates.date2num(f) for f in fechas[::paso]])
    eje.set_xticklabels([mes(f) for f in fechas[::paso]], color=TINTA_2, fontsize=8)
    _leyenda(eje, [Line2D([0], [0], color=c, linewidth=2.3, linestyle=e, label=n[:40])
                   for (n, _), c, e in zip(series, colores, ("-", (0, (6, 2))))])
    return _png(figura)


def escenarios(lista, pie):
    """Barras horizontales del dinero libre al final de cada escenario."""
    alto = max(3.6, 1.9 + 0.5 * len(lista))
    base = lista[0][1]["final"]
    figura, ejes = _tarjeta(alto, "¿Y si…?", "Dinero libre al final de la proyección en cada caso",
                            euros(base), "con tu configuración actual", None, pie)
    eje = ejes(abajo_pulgadas=0.6, arriba_pulgadas=1.45, izq=0.27, der=0.2)
    valores = [p["final"] for _, p in lista]
    abajo, arriba = min(0.0, min(valores)), max(valores) or 1
    eje.set_xlim(abajo * 1.1, arriba * 1.02)
    eje.set_ylim(len(lista) - 0.4, -0.6)
    for y, (nombre, p) in enumerate(lista):
        valor = p["final"]
        if valor >= 0:
            _barra(eje, 0, y, 0.52, valor, AZUL, horizontal=True, radio_px=4)
        else:
            _barra(eje, valor, y, 0.52, -valor, ROJO, horizontal=True, radio_px=4)
        diferencia = "" if y == 0 else f"  ({euros(valor - base, signo=True)})"
        eje.text(max(valor, 0) + (arriba - abajo) * 0.02, y, f"{euros(valor)}{diferencia}", va="center",
                 color=TINTA, fontsize=9, family=FUENTE, clip_on=False)
        if not p["sostenible"]:
            eje.text(max(valor, 0) + (arriba - abajo) * 0.02, y + 0.3, "! algún cobro no llega", va="center",
                     color=ROJO, fontsize=7.5, family=FUENTE, clip_on=False)
    eje.axvline(0, color=EJE, linewidth=1)
    eje.set_yticks(range(len(lista)))
    eje.set_yticklabels([n for n, _ in lista], color=TINTA, fontsize=9, family=FUENTE)
    eje.get_yticklabels()[0].set_fontweight("bold")
    eje.xaxis.set_visible(False)
    eje.spines["bottom"].set_visible(False)
    return _png(figura)

