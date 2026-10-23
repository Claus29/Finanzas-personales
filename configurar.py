"""Asistente de configuración: pide solo lo que falta en el .env y conecta el banco.

    python configurar.py               # completa lo que falte
    python configurar.py --reconectar  # vuelve a autorizar el acceso a N26
"""
import os
import re
import shutil
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import set_key

from banco import ErrorBanco
from saldo import BASE, ENV, cargar_config, cliente, marcar_consulta, mensaje_saldo

PATRON_APP_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def titulo(texto):
    print(f"\n{'=' * 60}\n {texto}\n{'=' * 60}")


def preguntar(texto):
    while True:
        valor = input(texto).strip().strip('"')
        if valor:
            return valor


def si(texto):
    return preguntar(f"{texto} (S/N): ").lower().startswith("s")


def guardar(clave, valor):
    set_key(str(ENV), clave, valor)
    os.environ[clave] = valor


def telegram(metodo, token=None, **params):
    token = token or os.environ["TELEGRAM_TOKEN"]
    datos = requests.post(f"https://api.telegram.org/bot{token}/{metodo}", json=params, timeout=40).json()
    if not datos.get("ok"):
        raise RuntimeError(datos.get("description", "error desconocido"))
    return datos["result"]


def configurar_token():
    titulo("PASO 1 · Bot de Telegram")
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
        guardar("TELEGRAM_TOKEN", token)
        print(f"✅ Bot encontrado: @{bot['username']}")
        return


def configurar_chat_id():
    titulo("PASO 2 · Vincular tu Telegram")
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
                guardar("TELEGRAM_CHAT_ID", str(mensaje["chat"]["id"]))
                telegram("sendMessage", chat_id=mensaje["chat"]["id"], text="✅ Te he reconocido. Solo te hablaré a ti.")
                print("✅ Telegram vinculado")
                return
            print("Vale, sigo esperando tu mensaje...")


def buscar_pem():
    candidatos = {p.resolve() for carpeta in (BASE, Path.home() / "Downloads", Path.home() / "Descargas")
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
    titulo("PASO 3 · Clave de Enable Banking")
    print("Elige el archivo .pem que se descargó al registrar la aplicación en Enable Banking.")
    while True:
        pem = buscar_pem()
        if not pem.is_file():
            print(f"❌ No encuentro {pem}")
            continue
        destino = BASE / pem.name
        if pem.resolve() != destino.resolve():
            shutil.copy2(pem, destino)
        app_id = pem.stem if PATRON_APP_ID.match(pem.stem) else preguntar("Escribe el Application ID: ")
        guardar("EB_APP_ID", app_id)
        guardar("EB_KEY_PATH", pem.name)
        try:
            app = cliente().aplicacion()
        except Exception as e:
            print(f"❌ Enable Banking no acepta esta clave ({e}). Elige otro archivo.")
            continue
        print(f"✅ Aplicación de Enable Banking: {app.get('name', app_id)}")
        return


def elegir_n26(eb):
    for pais in dict.fromkeys([os.environ.get("EB_COUNTRY") or "ES", "DE"]):
        try:
            return eb.buscar_banco("N26", pais)
        except ErrorBanco:
            continue
    raise ErrorBanco("No encuentro N26 en Enable Banking.")


def conectar_banco():
    titulo("PASO 4 · Conectar N26 (solo lectura)")
    eb = cliente()
    banco = elegir_n26(eb)
    redirect = os.environ.get("EB_REDIRECT_URL") or "https://localhost/callback"
    while True:
        try:
            url, dias = eb.iniciar_autorizacion(banco, redirect)
            break
        except ErrorBanco as e:
            print(f"❌ {e}")
            redirect = preguntar("Escribe la Redirect URL que registraste en Enable Banking: ")
            guardar("EB_REDIRECT_URL", redirect)

    print(f"Se va a abrir el navegador. Autoriza el acceso en N26 (permiso de {dias} días).")
    print("Al final llegarás a una página que NO carga: es normal.")
    print("Copia la dirección COMPLETA de la barra del navegador y pégala aquí.\n")
    webbrowser.open(url)
    while True:
        consulta = parse_qs(urlparse(preguntar("Pega aquí la dirección: ")).query)
        if "code" in consulta:
            break
        print(f"❌ Esa dirección no contiene el código ({consulta.get('error', ['falta ?code='])[0]}). "
              "Vuelve a autorizar si hace falta y pega la dirección final.")
    sesion = eb.crear_sesion(consulta["code"][0])
    guardar("EB_SESSION_ID", sesion["session_id"])
    guardar("EB_COUNTRY", banco["country"])

    mensaje = mensaje_saldo(eb, eb.sesion(sesion["session_id"]))
    marcar_consulta()  # cuenta como la consulta de hoy
    telegram("sendMessage", chat_id=os.environ["TELEGRAM_CHAT_ID"], parse_mode="Markdown",
             text=f"🎉 N26 conectado. A partir de ahora recibirás tu saldo cada día a las 00:00.\n\n{mensaje}")
    print("✅ N26 conectado. Te he enviado tu saldo actual por Telegram.")


def main():
    if not ENV.exists():
        shutil.copy(BASE / ".env.example", ENV)
    cargar_config()
    if not os.environ.get("TELEGRAM_TOKEN"):
        configurar_token()
    if not os.environ.get("TELEGRAM_CHAT_ID"):
        configurar_chat_id()
    clave = os.environ.get("EB_KEY_PATH")
    if not os.environ.get("EB_APP_ID") or not clave or not (BASE / clave).is_file():
        configurar_enable_banking()
    if "--reconectar" in sys.argv or not os.environ.get("EB_SESSION_ID"):
        conectar_banco()
    print("\n✅ Configuración completa.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nCancelado.")
    except Exception as e:
        sys.exit(f"\n❌ Error: {e}")
