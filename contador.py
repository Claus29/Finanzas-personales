"""Contador de consultas al banco: como mucho LIMITE_CONSULTAS_DIA al día (se reinicia a las 00:00)."""
import threading

import config

_candado = threading.Lock()


class LimiteAlcanzado(Exception):
    pass


def _leer():
    datos = config.leer_json(config.CONTADOR, {})
    if datos.get("fecha") != config.hoy():
        return {"fecha": config.hoy(), "usadas": 0}
    return datos


def estado():
    """(consultas usadas hoy, límite diario)."""
    with _candado:
        return _leer()["usadas"], config.limite_diario()


def usar():
    """Reserva una consulta. Lanza LimiteAlcanzado si ya no quedan hoy."""
    with _candado:
        datos = _leer()
        if datos["usadas"] >= config.limite_diario():
            raise LimiteAlcanzado
        datos["usadas"] += 1
        config.escribir_json(config.CONTADOR, datos)


def devolver():
    """Devuelve una consulta reservada que no llegó al banco (sin internet, permiso caducado...)."""
    with _candado:
        datos = _leer()
        if datos["usadas"] > 0:
            datos["usadas"] -= 1
            config.escribir_json(config.CONTADOR, datos)
