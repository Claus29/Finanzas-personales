"""Ciclo de cobro: cada «mes» del presupuesto va del día en que cobras hasta el siguiente cobro.

El salario suele llegar entre DIA_COBRO_DESDE y DIA_COBRO_HASTA (3–7 por defecto). El ciclo empieza
el día real del último salario registrado; si aún no hay ninguno, se estima con DIA_COBRO_DESDE.
"""
from datetime import date, timedelta

import config
import datos
from formato import dia_del_mes, sumar_meses

MAX_DIAS_CICLO = 45  # si el último salario es más antiguo, se considera que falta registrarlo


def hoy():
    return config.ahora().date()


def ultimo_salario(hasta=None):
    return datos.uno("SELECT * FROM ingresos WHERE tipo = 'salario' AND fecha <= ? ORDER BY fecha DESC, id DESC LIMIT 1",
                     (hasta or hoy()).isoformat())


def inicio_estimado(d):
    desde, _ = config.dias_cobro()
    inicio = dia_del_mes(d.year, d.month, desde)
    return inicio if d >= inicio else sumar_meses(inicio, -1, desde)


def inicio(d=None):
    d = d or hoy()
    salario = ultimo_salario(d)
    if salario:
        fecha = date.fromisoformat(salario["fecha"])
        if (d - fecha).days <= MAX_DIAS_CICLO:
            return fecha
    return inicio_estimado(d)


def proximo_cobro(d=None):
    """Fecha estimada del próximo cobro (como pronto, mañana)."""
    d = d or hoy()
    desde, hasta = config.dias_cobro()
    empieza = inicio(d)
    dia = empieza.day if desde <= empieza.day <= hasta else desde
    estimado = sumar_meses(empieza, 1, dia)
    return max(estimado, d + timedelta(days=1))


def dias_hasta_cobro(d=None):
    d = d or hoy()
    return max(1, (proximo_cobro(d) - d).days)


def inicio_anterior(d=None):
    """Inicio del ciclo anterior al actual."""
    actual = inicio(d)
    return inicio(actual - timedelta(days=1))


def cobrado_este_mes(d=None):
    """True si ya se ha registrado el salario de este mes."""
    d = d or hoy()
    desde, _ = config.dias_cobro()
    ventana = dia_del_mes(d.year, d.month, max(1, desde - 5))
    return datos.uno("SELECT 1 AS si FROM ingresos WHERE tipo = 'salario' AND fecha >= ? AND fecha <= ?",
                     ventana.isoformat(), d.isoformat()) is not None


def cobro_esperado_hoy(d=None):
    """True si hoy toca recordar el cobro: desde DIA_COBRO_DESDE y aún sin registrar."""
    d = d or hoy()
    desde, _ = config.dias_cobro()
    return d.day >= desde and not cobrado_este_mes(d)
