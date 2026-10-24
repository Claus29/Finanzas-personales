"""Gráficos (PNG) para Telegram: evolución del saldo y gastos por categoría.

Una sola serie, un solo color (validado), líneas de 2 px, rejilla muy suave, barras finas con la
cifra al final y el dato principal también en el texto del mensaje.
"""
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from formato import MESES_CORTOS  # noqa: E402

SUPERFICIE = "#fcfcfb"
SERIE = "#2a78d6"
TEXTO = "#0b0b0b"
TEXTO_SECUNDARIO = "#52514e"
REJILLA = "#e6e5e1"


def euros_enteros(v):
    """En los gráficos, todas las cifras en euros enteros para que se lean igual."""
    return f"{round(v):,} €".replace(",", ".")


def _lienzo(alto=4.2):
    figura, eje = plt.subplots(figsize=(8, alto), dpi=150)
    figura.patch.set_facecolor(SUPERFICIE)
    eje.set_facecolor(SUPERFICIE)
    for lado in ("top", "right", "left"):
        eje.spines[lado].set_visible(False)
    eje.spines["bottom"].set_color(REJILLA)
    eje.tick_params(colors=TEXTO_SECUNDARIO, labelsize=9, length=0)
    return figura, eje


def _png(figura):
    salida = io.BytesIO()
    figura.savefig(salida, format="png", facecolor=SUPERFICIE, bbox_inches="tight", pad_inches=0.3)
    plt.close(figura)
    salida.seek(0)
    return salida


def evolucion(serie, titulo):
    """serie: [(fecha, saldo)]"""
    fechas = [d for d, _ in serie]
    valores = [v for _, v in serie]
    figura, eje = _lienzo()
    eje.plot(fechas, valores, color=SERIE, linewidth=2, solid_capstyle="round", solid_joinstyle="round")
    eje.fill_between(fechas, valores, min(valores) - abs(min(valores)) * 0.02, color=SERIE, alpha=0.10, linewidth=0)
    eje.scatter([fechas[-1]], [valores[-1]], s=60, color=SERIE, edgecolors=SUPERFICIE, linewidths=2, zorder=3)
    eje.annotate(euros_enteros(valores[-1]), (fechas[-1], valores[-1]), xytext=(8, 0), textcoords="offset points",
                 va="center", color=TEXTO, fontsize=10, fontweight="bold")
    minimo = valores.index(min(valores))
    if 0 < minimo < len(valores) - 1:
        eje.annotate(f"mín. {euros_enteros(valores[minimo])}", (fechas[minimo], valores[minimo]), xytext=(0, -14),
                     textcoords="offset points", ha="center", color=TEXTO_SECUNDARIO, fontsize=8)
    eje.grid(axis="y", color=REJILLA, linewidth=1)
    eje.set_axisbelow(True)
    eje.yaxis.set_major_formatter(FuncFormatter(lambda v, _: euros_enteros(v)))
    eje.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{mdates.num2date(v).day} "
                                                             f"{MESES_CORTOS[mdates.num2date(v).month - 1]}"))
    eje.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=6))
    eje.set_title(titulo, loc="left", color=TEXTO, fontsize=12, fontweight="bold", pad=12)
    eje.margins(x=0.06)
    return _png(figura)


def categorias(lista, titulo):
    """lista: [(nombre visible, total)] de mayor a menor (máx. 8)."""
    lista = list(reversed(lista[:8]))
    # Las fuentes de los gráficos no tienen emojis: se quitan (en el texto del mensaje se mantienen).
    nombres = [n.split(" ", 1)[1] if " " in n and not n[0].isalnum() else n for n, _ in lista]
    valores = [v for _, v in lista]
    figura, eje = _lienzo(alto=max(2.4, 0.5 * len(lista) + 1.2))
    eje.barh(nombres, valores, height=0.5, color=SERIE, edgecolor=SUPERFICIE, linewidth=2)
    maximo = max(valores)
    for y, v in enumerate(valores):
        eje.text(v + maximo * 0.015, y, euros_enteros(v), va="center", color=TEXTO, fontsize=9)
    eje.set_xlim(0, maximo * 1.18)
    eje.xaxis.set_visible(False)
    eje.spines["bottom"].set_visible(False)
    eje.tick_params(axis="y", labelsize=10, colors=TEXTO)
    eje.set_title(titulo, loc="left", color=TEXTO, fontsize=12, fontweight="bold", pad=12)
    return _png(figura)


def barras_meses(etiquetas, valores, titulo):
    """Barras verticales por mes (p. ej. deuda pendiente al final de cada mes)."""
    figura, eje = _lienzo()
    posiciones = range(len(valores))
    eje.bar(posiciones, valores, width=0.6, color=SERIE, edgecolor=SUPERFICIE, linewidth=2)
    maximo = max(valores) if valores else 1
    for x, v in zip(posiciones, valores):
        if v > 0:
            eje.text(x, v + maximo * 0.02, euros_enteros(v), ha="center", va="bottom", color=TEXTO, fontsize=8)
    eje.set_xticks(list(posiciones))
    eje.set_xticklabels(etiquetas, rotation=0 if len(etiquetas) <= 8 else 45, ha="center" if len(etiquetas) <= 8 else "right")
    eje.yaxis.set_visible(False)
    eje.set_ylim(0, maximo * 1.15)
    eje.set_title(titulo, loc="left", color=TEXTO, fontsize=12, fontweight="bold", pad=12)
    return _png(figura)
