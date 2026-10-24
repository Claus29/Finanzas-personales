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
    # v5: cobro, presupuesto y avisos
    "DIA_COBRO_DESDE": "3",
    "DIA_COBRO_HASTA": "7",
    "PRESUPUESTO_CICLO": "0",
    "UMBRAL_SALDO_BAJO": "300",
    "AVISO_DEUDAS": "1",
    "AVISO_METAS": "1",
    "AVISO_RESUMEN_SEMANAL": "1",
    "AVISO_RESUMEN_CICLO": "1",
    "AVISO_SALDO_BAJO": "1",
    "AVISO_RITMO": "1",
    "AVISO_GASTO_GRANDE": "1",
    "AVISO_SUSCRIPCIONES": "0",
    # v6: recordatorio del día de pago (lo que debes, lo que te deben y suscripciones)
    "HORA_AVISO_PAGO": "00:00",  # v6; desde la v7 se usa la franja de abajo (se conserva la clave)
    "AVISO_ME_DEBEN": "1",
    # v7: recordatorios de deudas repartidos en una franja, y días para lo que te deben sin día fijo
    "FRANJA_DEUDAS_DESDE": "08:00",
    "FRANJA_DEUDAS_HASTA": "14:00",
    "DIAS_AVISO_SIN_DIA": "5,15,25",
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


def hora_aviso_pago():
    """'HH:MM' del recordatorio del día de pago (00:00 por defecto)."""
    try:
        horas, minutos = (int(x) for x in valor("HORA_AVISO_PAGO").split(":"))
        if 0 <= horas < 24 and 0 <= minutos < 60:
            return f"{horas:02d}:{minutos:02d}"
    except ValueError:
        pass
    return POR_DEFECTO["HORA_AVISO_PAGO"]


def _hora(clave):
    try:
        horas, minutos = (int(x) for x in valor(clave).split(":"))
        if 0 <= horas < 24 and 0 <= minutos < 60:
            return horas, minutos
    except ValueError:
        pass
    horas, minutos = POR_DEFECTO[clave].split(":")
    return int(horas), int(minutos)


def franja_deudas():
    """((h, m) de inicio, (h, m) de fin) de los recordatorios de deudas (08:00–14:00 por defecto)."""
    desde, hasta = _hora("FRANJA_DEUDAS_DESDE"), _hora("FRANJA_DEUDAS_HASTA")
    if hasta <= desde:
        return (8, 0), (14, 0)
    return desde, hasta


def dias_aviso_sin_dia():
    try:
        dias = sorted({int(x) for x in valor("DIAS_AVISO_SIN_DIA").replace(" ", "").split(",") if x})
        dias = [x for x in dias if 1 <= x <= 31]
        if dias:
            return dias
    except ValueError:
        pass
    return [5, 15, 25]


def saldo_diario_activo():
    # Desde la v5 la actualización diaria es siempre silenciosa y siempre ocurre; se conserva la clave.
    return valor("SALDO_DIARIO_ACTIVO") != "0"


def entero(clave, minimo, maximo):
    try:
        return min(maximo, max(minimo, int(float(valor(clave)))))
    except ValueError:
        return min(maximo, max(minimo, int(POR_DEFECTO[clave])))


def importe(clave):
    try:
        return max(0.0, float(valor(clave)))
    except ValueError:
        return float(POR_DEFECTO[clave])


def dias_cobro():
    """(primer día, último día) del mes en que suele llegar el salario."""
    desde = entero("DIA_COBRO_DESDE", 1, 28)
    return desde, max(desde, entero("DIA_COBRO_HASTA", 1, 28))


def aviso_activo(clave):
    return valor(clave) != "0"


def leer_json(ruta, defecto):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return defecto


def escribir_json(ruta, datos):
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(ruta)  # escritura atómica: nunca queda un archivo a medias


# Mientras la ventana pide la autenticación con N26, la actividad del bot no se escribe en ella.
CONSOLA = {"silenciada": False}


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
        consola.addFilter(lambda r: not CONSOLA["silenciada"] and (r.name == "root" or r.levelno >= logging.WARNING))
        raiz.addHandler(consola)
    # httpx registra cada petición a Telegram con el token en la URL: no queremos eso en el log.
    for ruidoso in ("httpx", "httpcore", "apscheduler", "telegram"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
