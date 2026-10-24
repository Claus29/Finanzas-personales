"""Asistente de configuración inicial: Telegram y clave de Enable Banking.

Solo pregunta lo que falta en el .env, así que en una instalación ya configurada no pregunta nada.
La conexión con N26 está en autenticacion.py.
"""
import re
import shutil
import webbrowser
from pathlib import Path

import requests

import config
import consultas
from consola import preguntar, si, titulo

PATRON_APP_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def telegram(metodo, token=None, **params):
    token = token or config.valor("TELEGRAM_TOKEN")
    datos = requests.post(f"https://api.telegram.org/bot{token}/{metodo}", json=params, timeout=40).json()
    if not datos.get("ok"):
        raise RuntimeError(datos.get("description", "error desconocido"))
    return datos["result"]


def configurar_token():
    titulo("CONFIGURACION 1/3 · Bot de Telegram")
    print("1. Abre Telegram y busca @BotFather")
    print("2. Escríbele /newbot y sigue las instrucciones (nombre y usuario acabado en 'bot')")
    print("3. Copia el token que te da (algo como 123456789:ABCdef...)\n")
    webbrowser.open("https://t.me/BotFather")
    while True:
        token = preguntar("Pega aquí el token: ")
        try:
            bot = telegram("getMe", token=token)
        except Exception as e:
            print(f"❌ Ese token no funciona ({e}). Prueba otra vez.")
            continue
        config.guardar("TELEGRAM_TOKEN", token)
        print(f"✅ Bot encontrado: @{bot['username']}")
        return


def configurar_chat_id():
    titulo("CONFIGURACION 2/3 · Vincular tu Telegram")
    usuario = telegram("getMe")["username"]
    pendientes = telegram("getUpdates", timeout=0)
    offset = pendientes[-1]["update_id"] + 1 if pendientes else None
    print(f"Abre Telegram y envía cualquier mensaje (por ejemplo /start) a @{usuario}")
    print("Esperando tu mensaje...")
    webbrowser.open(f"https://t.me/{usuario}")
    while True:
        for update in telegram("getUpdates", offset=offset, timeout=30):
            offset = update["update_id"] + 1
            mensaje = update.get("message")
            if not mensaje or mensaje["chat"]["type"] != "private":
                continue
            de = mensaje["from"]
            quien = de.get("first_name", "") + (f" (@{de['username']})" if de.get("username") else "")
            if si(f"Mensaje recibido de {quien}. ¿Eres tú?"):
                telegram("getUpdates", offset=offset, timeout=0)  # marca los mensajes como leídos
                config.guardar("TELEGRAM_CHAT_ID", str(mensaje["chat"]["id"]))
                telegram("sendMessage", chat_id=mensaje["chat"]["id"], text="✅ Te he reconocido. Solo te hablaré a ti.")
                print("✅ Telegram vinculado")
                return
            print("Vale, sigo esperando tu mensaje...")


def buscar_pem():
    candidatos = {p.resolve() for carpeta in (config.BASE, Path.home() / "Downloads", Path.home() / "Descargas")
                  if carpeta.is_dir() for p in carpeta.glob("*.pem") if PATRON_APP_ID.match(p.stem)}
    if len(candidatos) == 1:
        pem = candidatos.pop()
        if si(f"He encontrado la clave {pem}. ¿Es esta?"):
            return pem
    try:
        from tkinter import Tk, filedialog
        raiz = Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        ruta = filedialog.askopenfilename(title="Elige tu archivo .pem de Enable Banking",
                                          filetypes=[("Clave privada", "*.pem"), ("Todos", "*.*")])
        raiz.destroy()
        if ruta:
            return Path(ruta)
    except Exception:
        pass
    return Path(preguntar("Escribe la ruta completa de tu archivo .pem: "))


def configurar_enable_banking():
    titulo("CONFIGURACION 3/3 · Clave de Enable Banking")
    print("Elige el archivo .pem que se descargó al registrar la aplicación en Enable Banking.")
    while True:
        pem = buscar_pem()
        if not pem.is_file():
            print(f"❌ No encuentro {pem}")
            continue
        destino = config.BASE / pem.name
        if pem.resolve() != destino.resolve():
            shutil.copy2(pem, destino)
        app_id = pem.stem if PATRON_APP_ID.match(pem.stem) else preguntar("Escribe el Application ID: ")
        config.guardar("EB_APP_ID", app_id)
        config.guardar("EB_KEY_PATH", pem.name)
        try:
            app = consultas.cliente().aplicacion()
        except Exception as e:
            print(f"❌ Enable Banking no acepta esta clave ({e}). Elige otro archivo.")
            continue
        print(f"✅ Aplicación de Enable Banking: {app.get('name', app_id)}")
        return


def completar():
    """Pide solo lo que falte. Devuelve True si se ha configurado algo."""
    config.cargar()
    cambios = False
    if not config.valor("TELEGRAM_TOKEN"):
        configurar_token()
        cambios = True
    if not config.valor("TELEGRAM_CHAT_ID"):
        configurar_chat_id()
        cambios = True
    clave = config.valor("EB_KEY_PATH")
    if not config.valor("EB_APP_ID") or not clave or not (config.BASE / clave).is_file():
        configurar_enable_banking()
        cambios = True
    return cambios
