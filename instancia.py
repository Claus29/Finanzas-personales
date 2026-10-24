"""Garantiza que solo haya un bot funcionando y permite traer su ventana al frente."""
import socket
import sys

PUERTO = 47391  # puerto local que reserva el bot mientras funciona
TITULO = "Bot Finanzas"
_reserva = None


def _nuevo_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: nadie más puede usar el puerto
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    return s


def adquirir():
    """True si este proceso pasa a ser el único bot; False si ya hay otro funcionando."""
    global _reserva
    s = _nuevo_socket()
    try:
        s.bind(("127.0.0.1", PUERTO))
    except OSError:
        s.close()
        return False
    _reserva = s
    return True


def en_marcha():
    s = _nuevo_socket()
    try:
        s.bind(("127.0.0.1", PUERTO))
        return False
    except OSError:
        return True
    finally:
        s.close()


def poner_titulo():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(TITULO)


def traer_al_frente():
    if sys.platform != "win32":
        return
    import ctypes
    user32 = ctypes.windll.user32
    ventana = user32.FindWindowW(None, TITULO)
    if ventana:
        user32.ShowWindow(ventana, 9)  # SW_RESTORE: la saca de minimizada
        user32.SetForegroundWindow(ventana)
