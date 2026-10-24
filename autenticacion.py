"""Autenticación con N26 (solo lectura) a través de Enable Banking.

Se ejecuta en la ventana del bot la primera vez y cada vez que el permiso deja de ser válido.
Comprueba todo lo que puede fallar antes de empezar, detecta sola la dirección de vuelta al
copiarla y, si algo sale mal, genera un enlace nuevo sin cerrar nada.
"""
import logging
import sys
import time
import uuid
import webbrowser
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import requests

import config
import consultas
from banco import ErrorBanco
from consola import preguntar, si, texto_plano, titulo

REDIRECT_POR_DEFECTO = "https://localhost/callback"
DIAS_PERMISO_MAX = 180


def permiso_valido():
    """True si hay un permiso activo y cuentas guardadas. Los fallos de red se propagan."""
    session_id = config.valor("EB_SESSION_ID")
    if not session_id or not consultas.conexion().get("cuentas"):
        return False
    try:
        sesion = consultas.cliente().sesion(session_id)
    except ErrorBanco as e:
        if e.estado in (400, 401, 403, 404, 422):
            return False
        raise
    return sesion.get("status") == "AUTHORIZED"


# ---------- Comprobaciones previas ----------

def comprobar_aplicacion(eb):
    """Espera a que la aplicación de Enable Banking esté activa y la devuelve."""
    while True:
        app = eb.aplicacion()
        if app.get("active", True):
            print(f"✅ Aplicación de Enable Banking: {app.get('name', config.valor('EB_APP_ID'))}")
            return app
        print("❌ Tu aplicación de Enable Banking no está activa.")
        print("   1. Entra en el Control Panel de Enable Banking > API applications.")
        print("   2. En tu aplicación pulsa «Link accounts», elige N26 y autoriza tus cuentas.")
        input("   Cuando lo hayas hecho, pulsa Enter para comprobarlo otra vez...")


def elegir_redirect(app):
    """Usa la dirección de vuelta registrada en la aplicación (evita el error de redirect)."""
    registradas = [u for u in app.get("redirect_urls") or [] if u]
    actual = config.valor("EB_REDIRECT_URL")
    if actual in registradas:
        return actual
    return registradas[0] if registradas else (actual or REDIRECT_POR_DEFECTO)


def elegir_n26(eb):
    paises = list(dict.fromkeys([config.valor("EB_COUNTRY"), "ES", "DE"]))
    for pais in paises:
        for banco in eb.bancos(pais):
            if "N26" in banco["name"].upper():
                return banco
    raise ErrorBanco(404, "N26 no aparece en la lista de bancos de Enable Banking.")


# ---------- Dirección de vuelta ----------

def leer_portapapeles():
    """Texto del portapapeles de Windows ('' si no hay o no se puede leer)."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        if not user32.OpenClipboard(None):
            return ""
        try:
            datos = user32.GetClipboardData(13)  # CF_UNICODETEXT
            if not datos:
                return ""
            puntero = kernel32.GlobalLock(datos)
            if not puntero:
                return ""
            try:
                return ctypes.wstring_at(puntero).strip()
            finally:
                kernel32.GlobalUnlock(datos)
        finally:
            user32.CloseClipboard()
    except Exception:
        return ""


def parece_vuelta(texto, redirect):
    base = redirect.split("?")[0].rstrip("/")
    return texto.startswith(base) and ("code=" in texto or "error=" in texto)


def esperar_direccion(redirect):
    """Espera la dirección de vuelta: la detecta en el portapapeles o la acepta escrita/pegada."""
    if sys.platform != "win32":
        return preguntar("> ")
    import msvcrt
    visto = leer_portapapeles()
    escrito = ""
    print("> ", end="", flush=True)
    while True:
        while msvcrt.kbhit():
            tecla = msvcrt.getwch()
            if tecla in ("\r", "\n"):
                print()
                if escrito.strip():
                    return escrito.strip().strip('"')
                print("> ", end="", flush=True)
            elif tecla == "\b":
                if escrito:
                    escrito = escrito[:-1]
                    print("\b \b", end="", flush=True)
            elif tecla == "\x03":
                raise KeyboardInterrupt
            elif tecla in ("\x00", "\xe0"):
                msvcrt.getwch()  # flechas y teclas especiales: se ignoran
            else:
                escrito += tecla
                print(tecla, end="", flush=True)
        copiado = leer_portapapeles()
        if copiado != visto:
            visto = copiado
            if parece_vuelta(copiado, redirect):
                print("\n📋 Dirección detectada en el portapapeles.")
                return copiado
        time.sleep(0.3)


def leer_vuelta(texto):
    """Extrae code/state/error de la dirección de vuelta (o acepta el código solo)."""
    consulta = parse_qs(urlparse(texto).query)
    if not consulta and "://" not in texto and " " not in texto and len(texto) > 10:
        return {"code": texto}
    return {clave: valores[0] for clave, valores in consulta.items()}


# ---------- Cuentas ----------

def describir_cuentas(sesion):
    cuentas = []
    for n, cuenta in enumerate(sesion.get("accounts") or [], 1):
        if isinstance(cuenta, str):
            cuenta = {"uid": cuenta}
        iban = ((cuenta.get("account_id") or {}).get("iban") or "").replace(" ", "")
        nombre = cuenta.get("name") or cuenta.get("details") or cuenta.get("product") or f"Cuenta {n}"
        cuentas.append({"uid": cuenta["uid"], "nombre": nombre.strip(), "iban4": iban[-4:] if iban else ""})
    return cuentas


def elegir_cuentas(cuentas):
    print("\nN26 ha compartido estas cuentas:")
    for n, cuenta in enumerate(cuentas, 1):
        print(f"   {n}. {consultas.nombre_cuenta(cuenta)}")
    if len(cuentas) == 1:
        return cuentas
    while True:
        respuesta = input("Pulsa Enter para ver todas, o escribe los números que quieres ver (ej: 1,3): ").strip()
        if not respuesta:
            return cuentas
        try:
            elegidas = sorted({int(x) for x in respuesta.replace(" ", "").split(",") if x})
            if elegidas and all(1 <= n <= len(cuentas) for n in elegidas):
                return [cuentas[n - 1] for n in elegidas]
        except ValueError:
            pass
        print(f"❌ Escribe números del 1 al {len(cuentas)} separados por comas.")


# ---------- Proceso completo ----------

def obtener_sesion(eb, banco, redirect, dias):
    """Repite enlace → autorización → dirección de vuelta hasta conseguir una sesión."""
    while True:
        state = str(uuid.uuid4())
        try:
            url = eb.iniciar_autorizacion(banco, redirect, dias, state)
        except ErrorBanco as e:
            logging.getLogger("detalle").error("Fallo en /auth: %s", e)
            print(f"❌ Enable Banking no ha generado el enlace: {e.texto[:300]}")
            input("Pulsa Enter para intentarlo otra vez...")
            continue

        print(f"\n1. Se abre el navegador: autoriza el acceso en N26 (permiso de {dias} días).")
        print("   Marca TODAS las cuentas que quieras ver en el bot.")
        print("2. Al final llegarás a una página que NO carga. Es normal.")
        print("3. Copia la dirección de esa página (barra de arriba del navegador, Ctrl+C).")
        print("   La detecto sola al copiarla. También puedes pegarla aquí y pulsar Enter.")
        print(f"\n   Si el navegador no se abre, copia este enlace en él:\n   {url}\n")
        webbrowser.open(url)

        while True:
            datos = leer_vuelta(esperar_direccion(redirect))
            if datos.get("error"):
                motivo = datos.get("error_description") or datos["error"]
                print(f"❌ N26 no ha dado el permiso ({motivo}). Vamos a intentarlo con un enlace nuevo.")
                break
            if not datos.get("code"):
                print("❌ Esa no es la dirección correcta. Copia la de la página que NO carga "
                      f"(empieza por {redirect}?code=...).")
                continue
            if datos.get("state") and datos["state"] != state:
                print("❌ Esa dirección es de un intento anterior. Copia la de este intento.")
                continue
            try:
                return eb.crear_sesion(datos["code"])
            except ErrorBanco as e:
                logging.getLogger("detalle").error("Fallo en /sessions: %s", e)
                print("❌ Ese código ya no vale (caduca en pocos minutos y solo se puede usar una vez).")
                print("   Vamos a intentarlo con un enlace nuevo.")
                break
        input("Pulsa Enter para abrir un enlace nuevo...")


def autenticar():
    titulo("CONECTAR N26 (solo lectura)")
    eb = consultas.cliente()
    app = comprobar_aplicacion(eb)
    redirect = elegir_redirect(app)
    banco = elegir_n26(eb)
    maximo = (banco.get("maximum_consent_validity") or 90 * 86400) // 86400
    dias = max(1, min(DIAS_PERMISO_MAX, maximo))

    while True:
        sesion = obtener_sesion(eb, banco, redirect, dias)
        cuentas = describir_cuentas(sesion)
        if cuentas:
            break
        print("❌ N26 no ha compartido ninguna cuenta. Al autorizar, marca tus cuentas.")
        input("Pulsa Enter para intentarlo otra vez...")

    elegidas = elegir_cuentas(cuentas)
    valido_hasta = (sesion.get("access") or {}).get("valid_until") or \
        (datetime.now(timezone.utc) + timedelta(days=dias)).isoformat()
    config.guardar("EB_SESSION_ID", sesion["session_id"])
    config.guardar("EB_COUNTRY", banco["country"])
    config.guardar("EB_REDIRECT_URL", redirect)
    config.escribir_json(config.CONEXION, {"valido_hasta": valido_hasta, "cuentas": elegidas})
    logging.info("N26 conectado (%s cuentas, válido hasta %s)", len(elegidas), valido_hasta[:10])
    print("✅ N26 conectado.")
    probar_conexion()


def probar_conexion():
    print("\nConsultando tu saldo para comprobar que todo funciona (gasta 1 consulta de hoy)...")
    try:
        cuerpo = consultas.consultar()
    except consultas.LimiteAlcanzado:
        print("ℹ️  Hoy ya no quedan consultas: la prueba se hará con tu próxima consulta.")
        return
    except (requests.ConnectionError, requests.Timeout):
        print("ℹ️  Sin conexión ahora mismo: la prueba se hará con tu próxima consulta.")
        return
    print("\n" + texto_plano(cuerpo) + "\n")
    if not si("¿Son correctos estos saldos?"):
        print("He guardado todos los tipos de saldo que da el banco en bot.log.")
        print("Pásale a Claude las líneas que empiezan por «Saldos de» para revisarlo.")
