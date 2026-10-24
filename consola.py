"""Utilidades para hablar con el usuario en la ventana del bot."""
import html
import re


def titulo(texto):
    print(f"\n{'=' * 60}\n {texto}\n{'=' * 60}")


def preguntar(texto):
    while True:
        valor = input(texto).strip().strip('"')
        if valor:
            return valor


def si(texto):
    return preguntar(f"{texto} (S/N): ").lower().startswith("s")


def texto_plano(mensaje_html):
    """Convierte un mensaje de Telegram (HTML) en texto para la ventana."""
    return html.unescape(re.sub(r"<[^>]+>", "", mensaje_html))
