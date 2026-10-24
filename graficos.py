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


# ---------- v8 · Análisis completo ----------
# Dos series a la vez: azul (entradas, totales, escenario actual) y naranja (salidas); tercera, verde.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")
PISTA = "#efeeea"  # fondo de las barras de progreso


def _sin_emoji(texto):
    return texto.split(" ", 1)[1] if " " in texto and not texto[0].isalnum() else texto


def _titulo(eje, titulo):
    eje.set_title(titulo, loc="left", color=TEXTO, fontsize=12, fontweight="bold", pad=12)


def _leyenda(eje, ncol):
    eje.legend(loc="upper left", bbox_to_anchor=(0, 1.02), ncol=ncol, frameon=False, fontsize=9,
               labelcolor=TEXTO_SECUNDARIO, handlelength=1.2)


def cascada(pasos, titulo):
    """Flujo en cascada. pasos: [(etiqueta, importe, tipo)] con tipo «total» (barra desde 0, azul),
    «salida» (baja, naranja) o «entrada» (sube, azul)."""
    figura, eje = _lienzo(alto=4.6)
    nivel = 0.0
    maximo = max([abs(v) for _, v, _ in pasos] + [1])
    alturas = []
    for x, (etiqueta, valor, tipo) in enumerate(pasos):
        if tipo == "total":
            base, alto, color = 0.0, valor, SERIES[0]
            nivel = valor
        elif tipo == "salida":
            base, alto, color = nivel - valor, valor, SERIES[1]
            nivel -= valor
        else:
            base, alto, color = nivel, valor, SERIES[0]
            nivel += valor
        eje.bar(x, alto, bottom=base, width=0.62, color=color, edgecolor=SUPERFICIE, linewidth=2)
        tope = max(base, base + alto)
        texto = euros_enteros(valor) if tipo != "salida" else "−" + euros_enteros(valor)
        eje.text(x, tope + maximo * 0.02, texto, ha="center", va="bottom", color=TEXTO, fontsize=8.5,
                 fontweight="bold" if tipo == "total" else "normal")
        alturas.append((base, base + alto))
        if x < len(pasos) - 1:
            eje.plot([x + 0.31, x + 0.69], [nivel, nivel], color=TEXTO_SECUNDARIO, linewidth=0.8, linestyle=(0, (2, 2)))
    eje.axhline(0, color=REJILLA, linewidth=1)
    eje.set_xticks(range(len(pasos)))
    eje.set_xticklabels([_sin_emoji(p[0]) for p in pasos], fontsize=8.5, color=TEXTO)
    abajo = min([0.0] + [min(a) for a in alturas])
    arriba = max([max(a) for a in alturas] + [1])
    eje.set_ylim(abajo - (arriba - abajo) * 0.05 if abajo < 0 else 0, arriba + (arriba - abajo) * 0.12)
    eje.yaxis.set_visible(False)
    _titulo(eje, titulo)
    return _png(figura)


def barras_dobles(etiquetas, serie_a, serie_b, nombres, titulo):
    """Dos barras por periodo (p. ej. ingresos en azul y gastos en naranja), con leyenda."""
    figura, eje = _lienzo(alto=4.4)
    n = len(etiquetas)
    ancho = 0.38
    maximo = max(list(serie_a) + list(serie_b) + [1])
    for desplazamiento, serie, color, nombre in ((-ancho / 2, serie_a, SERIES[0], nombres[0]),
                                                 (ancho / 2, serie_b, SERIES[1], nombres[1])):
        posiciones = [x + desplazamiento for x in range(n)]
        eje.bar(posiciones, serie, width=ancho, color=color, edgecolor=SUPERFICIE, linewidth=1.5, label=nombre)
        if n <= 3:  # con más periodos las cifras se pisarían: se leen en el eje y en el texto
            for x, v in zip(posiciones, serie):
                if v > 0:
                    eje.text(x, v + maximo * 0.015, euros_enteros(v), ha="center", va="bottom", color=TEXTO, fontsize=7.5)
    eje.set_xticks(range(n))
    eje.set_xticklabels(etiquetas, rotation=0 if n <= 8 else 45, ha="center" if n <= 8 else "right")
    eje.grid(axis="y", color=REJILLA, linewidth=1)
    eje.set_axisbelow(True)
    eje.yaxis.set_major_formatter(FuncFormatter(lambda v, _: euros_enteros(v)))
    eje.set_ylim(0, maximo * 1.22)
    _leyenda(eje, 2)
    _titulo(eje, titulo)
    return _png(figura)


def ratio_meses(etiquetas, fracciones, titulo):
    """% del salario comprometido por periodo, con las referencias del 30 % y el 40 %."""
    figura, eje = _lienzo()
    valores = [f * 100 for f in fracciones]
    posiciones = range(len(valores))
    eje.bar(posiciones, valores, width=0.6, color=SERIES[0], edgecolor=SUPERFICIE, linewidth=2)
    tope = max(valores + [45])
    for x, v in zip(posiciones, valores):
        eje.text(x, v + tope * 0.015, f"{v:.0f} %", ha="center", va="bottom", color=TEXTO, fontsize=8.5, zorder=4,
                 bbox={"facecolor": SUPERFICIE, "edgecolor": "none", "pad": 1})
    for nivel, texto in ((30, "30 % recomendado"), (40, "40 % límite")):
        eje.hlines(nivel, -0.5, len(valores) - 0.5, color=TEXTO_SECUNDARIO, linewidth=1, linestyle=(0, (4, 3)))
        eje.text(len(valores) - 0.4, nivel, texto, va="center", ha="left", color=TEXTO_SECUNDARIO, fontsize=8)
    eje.set_xticks(list(posiciones))
    eje.set_xticklabels(etiquetas, rotation=0 if len(etiquetas) <= 8 else 45,
                        ha="center" if len(etiquetas) <= 8 else "right")
    eje.yaxis.set_visible(False)
    eje.set_ylim(0, tope * 1.15)
    eje.set_xlim(-0.6, len(valores) + 1.1)
    _titulo(eje, titulo)
    return _png(figura)


def progreso(lista, titulo, etiqueta=None):
    """Barras de progreso horizontales. lista: [(nombre, valor, máximo, ...)].
    etiqueta(fila, fracción) da el texto a la derecha (por defecto, el %)."""
    etiqueta = etiqueta or (lambda fila, fraccion: f"{fraccion * 100:.0f} %")
    lista = list(reversed(lista[:10]))
    figura, eje = _lienzo(alto=max(2.2, 0.62 * len(lista) + 1.1))
    for y, fila in enumerate(lista):
        nombre, valor, maximo = fila[:3]
        fraccion = max(0.0, min(1.0, valor / maximo if maximo else 1.0))
        eje.barh(y, 1.0, height=0.46, color=PISTA, linewidth=0)
        eje.barh(y, fraccion, height=0.46, color=SERIES[0], linewidth=0)
        eje.text(1.02, y, etiqueta(fila, fraccion), va="center", color=TEXTO, fontsize=9)
    eje.set_yticks(range(len(lista)))
    eje.set_yticklabels([_sin_emoji(f[0])[:28] for f in lista], fontsize=10, color=TEXTO)
    eje.set_xlim(0, 1.45)
    eje.xaxis.set_visible(False)
    eje.spines["bottom"].set_visible(False)
    _titulo(eje, titulo)
    return _png(figura)


def y_libre(valor, anterior, rango):
    return valor - anterior > rango * 0.06


def lineas(fechas, series, titulo, inicio_proyeccion=None, desde_cero=False):
    """Varias líneas (máx. 3) sobre fechas, con leyenda y la cifra final de cada una.
    series: [(nombre, [valores])]. Desde `inicio_proyeccion` el fondo se marca como «previsión»."""
    figura, eje = _lienzo(alto=4.4)
    finales = []
    for (nombre, valores), color in zip(series, SERIES):
        eje.plot(fechas, valores, color=color, linewidth=2, label=nombre, solid_capstyle="round")
        eje.scatter([fechas[-1]], [valores[-1]], s=40, color=color, edgecolors=SUPERFICIE, linewidths=1.5, zorder=3)
        finales.append((valores[-1], color))
    if desde_cero:
        abajo, arriba = eje.get_ylim()
        eje.set_ylim(min(0, abajo), max(0, arriba))
        eje.axhline(0, color=TEXTO_SECUNDARIO, linewidth=0.8)
    # Cifras finales a la derecha del último punto, sin solaparse
    finales.sort()
    ultima = None
    rango = eje.get_ylim()[1] - eje.get_ylim()[0]
    x = fechas[-1] + (fechas[-1] - fechas[0]) * 0.02
    for valor, color in finales:
        y = valor if ultima is None or y_libre(valor, ultima, rango) else ultima + rango * 0.06
        eje.text(x, y, euros_enteros(valor), va="center", ha="left", color=color, fontsize=9, fontweight="bold")
        ultima = y
    if inicio_proyeccion is not None:
        eje.axvspan(inicio_proyeccion, fechas[-1], color=PISTA, alpha=0.6, linewidth=0, zorder=0)
        eje.text(inicio_proyeccion, eje.get_ylim()[1], " previsión", va="top", ha="left", color=TEXTO_SECUNDARIO,
                 fontsize=8)
    eje.grid(axis="y", color=REJILLA, linewidth=1)
    eje.set_axisbelow(True)
    eje.yaxis.set_major_formatter(FuncFormatter(lambda v, _: euros_enteros(v)))
    eje.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{MESES_CORTOS[mdates.num2date(v).month - 1]} "
                                                             f"{str(mdates.num2date(v).year)[2:]}"))
    eje.xaxis.set_major_locator(mdates.MonthLocator(interval=2 if len(fechas) > 8 else 1))
    eje.margins(x=0.02)
    eje.set_xlim(fechas[0], fechas[-1] + (fechas[-1] - fechas[0]) * 0.13)
    if len(series) > 1:
        _leyenda(eje, len(series))
    _titulo(eje, titulo)
    return _png(figura)
