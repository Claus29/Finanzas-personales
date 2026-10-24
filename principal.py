"""Programa principal: lo ejecuta BOT.bat en la ventana «Bot Finanzas».

Todo ocurre en esta única ventana y en este único proceso:
1. Comprueba que no haya otro bot funcionando (si lo hay, trae su ventana al frente y sale).
2. Completa la configuración que falte (Telegram y clave de Enable Banking).
3. Arranca el bot. Si el permiso de N26 no es válido (primera vez, caducado o desvinculado), el
   bot sigue funcionando con los últimos datos y esta misma ventana pide la autenticación.
"""
import logging
import sys
import time

import requests

import bot
import config
import configurar
import datos
import instancia

OTRA_INSTANCIA = 4  # código de salida que BOT.bat entiende como «ya hay un bot abierto»
ESPERA_REINTENTO = 30


def cabecera():
    print("=" * 60)
    print("   BOT FINANZAS - funcionando")
    print("=" * 60)
    print("  No cierres esta ventana: si la cierras, el bot se detiene.")
    print("  Puedes minimizarla. Para volver a abrirla: «Bot Finanzas» en el escritorio.\n")


def esperar_internet():
    """Al arrancar con Windows puede no haber red todavía."""
    avisado = False
    while True:
        try:
            requests.get("https://api.telegram.org", timeout=10)
            return
        except requests.RequestException:
            if not avisado:
                logging.warning("Sin conexión a internet; reintento cada %s segundos", ESPERA_REINTENTO)
                avisado = True
            time.sleep(ESPERA_REINTENTO)


def ciclo():
    """Configuración y bot. Devuelve cuando el bot se detiene."""
    config.cargar()
    datos.iniciar()
    configurar.completar()
    esperar_internet()
    bot.ejecutar()


def main():
    if not instancia.adquirir():
        print("El bot ya está abierto en otra ventana. Te la traigo al frente.")
        instancia.traer_al_frente()
        sys.exit(OTRA_INSTANCIA)
    instancia.poner_titulo()
    config.configurar_registro()
    cabecera()
    while True:
        try:
            ciclo()
            return
        except KeyboardInterrupt:
            return
        except Exception as e:
            logging.getLogger("detalle").exception("Error en el bot")
            logging.warning("El bot se ha detenido por un error: %s", e)
            logging.warning("Vuelvo a intentarlo en %s segundos...", ESPERA_REINTENTO)
            time.sleep(ESPERA_REINTENTO)


if __name__ == "__main__":
    main()
