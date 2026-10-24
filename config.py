"""Rutas, configuración (.env), fecha/hora local y registro del bot."""
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv, set_key

BASE = Path(__file__).resolve().parent
ENV = BASE / ".env"
CONEXION = BASE / "conexion.json"          # permiso del banco y cuentas elegidas
CONTADOR = BASE / "contador_api.json"      # consultas al banco de hoy
ULTIMO_SALDO = BASE / "ultimo_saldo.json"  # último saldo obtenido (para no repetir consultas)
ULTIMO_ENVIO_AUTOMATICO = BASE / "ultima_consulta.txt"  # nombre heredado de versiones anteriores
REGISTRO = BASE / "bot.log"

LIMITE_MIN, LIMITE_MAX, LIMITE_RECOMENDADO = 1, 20, 4
POR_DEFECTO = {
    "LIMITE_CONSULTAS_DIA": str(LIMITE_RECOMENDADO),
    "HORA_SALDO_DIARIO": "00:00",
    "SALDO_DIARIO_ACTIVO": "1",
    "ZONA_HORARIA": "Europe/Madrid",
    "EB_COUNTRY": "ES",
}


def cargar():
    if not ENV.exists() and (BASE / ".env.example").exists():
        shutil.copy(BASE / ".env.example", ENV)
    # override=True: los cambios hechos desde Ajustes o al reconectar se ven sin reiniciar.
    load_dotenv(ENV, override=True)


def valor(clave):
    return os.environ.get(clave) or POR_DEFECTO.get(clave, "")


def guardar(clave, nuevo):
    ENV.touch(exist_ok=True)
    set_key(str(ENV), clave, str(nuevo))
    os.environ[clave] = str(nuevo)


def zona():
    try:
        return ZoneInfo(valor("ZONA_HORARIA"))
    except Exception:
        return ZoneInfo(POR_DEFECTO["ZONA_HORARIA"])


def ahora():
    return datetime.now(zona())


def hoy():
    return ahora().date().isoformat()


def limite_diario():
    try:
        return min(LIMITE_MAX, max(LIMITE_MIN, int(valor("LIMITE_CONSULTAS_DIA"))))
    except ValueError:
        return LIMITE_RECOMENDADO


def hora_saldo_diario():
    try:
        horas, minutos = (int(x) for x in valor("HORA_SALDO_DIARIO").split(":"))
        if 0 <= horas < 24 and 0 <= minutos < 60:
            return horas, minutos
    except ValueError:
        pass
    return 0, 0


def saldo_diario_activo():
    return valor("SALDO_DIARIO_ACTIVO") != "0"


def leer_json(ruta, defecto):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return defecto


def escribir_json(ruta, datos):
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(ruta)  # escritura atómica: nunca queda un archivo a medias


class FormatoVentana(logging.Formatter):
    """En la ventana, los errores en una línea; el detalle técnico completo queda en bot.log."""

    def format(self, record):
        copia = logging.makeLogRecord(record.__dict__)
        copia.exc_info = copia.exc_text = None
        texto = super().format(copia)
        return f"{texto}: {record.exc_info[1]}" if record.exc_info else texto


def configurar_registro():
    raiz = logging.getLogger()
    if raiz.handlers:
        return
    raiz.setLevel(logging.INFO)
    archivo = RotatingFileHandler(REGISTRO, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    archivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    raiz.addHandler(archivo)
    if sys.stdout:
        consola = logging.StreamHandler(sys.stdout)
        consola.setFormatter(FormatoVentana("  %(asctime)s  %(message)s", datefmt="%d/%m %H:%M:%S"))
        consola.addFilter(lambda r: r.name == "root" or r.levelno >= logging.WARNING)
        raiz.addHandler(consola)
    # httpx registra cada petición a Telegram con el token en la URL: no queremos eso en el log.
    for ruidoso in ("httpx", "httpcore", "apscheduler", "telegram"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
