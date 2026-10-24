"""Formato de importes, fechas y barras, y lectura de lo que escribe el usuario."""
import calendar
import re
from datetime import date, timedelta

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
MESES_CORTOS = [m[:3] for m in MESES]
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def euros(cantidad, signo=False):
    texto = f"{abs(cantidad):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    prefijo = "-" if cantidad < -0.004 else ("+" if signo and cantidad > 0.004 else "")
    return f"{prefijo}{texto} €"


def euros_cortos(cantidad):
    """Sin decimales cuando no hacen falta (para tablas y botones)."""
    if abs(cantidad - round(cantidad)) < 0.005:
        texto = f"{abs(round(cantidad)):,}".replace(",", ".")
        return f"{'-' if cantidad < -0.004 else ''}{texto} €"
    return euros(cantidad)


def fecha_corta(d):
    return f"{d.day} {MESES_CORTOS[d.month - 1]}"


def fecha_larga(d):
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def mes_y_anio(d):
    return f"{MESES[d.month - 1]} {d.year}"


def barra(fraccion, ancho=12):
    fraccion = max(0.0, min(1.0, fraccion))
    llenos = round(fraccion * ancho)
    return "▓" * llenos + "░" * (ancho - llenos)


def semaforo(fraccion_usada):
    """Verde < 80 %, amarillo < 100 %, rojo a partir de 100 %."""
    return "🟢" if fraccion_usada < 0.8 else ("🟡" if fraccion_usada < 1 else "🔴")


def dia_del_mes(anio, mes, dia):
    """Fecha con ese día del mes, o el último día si el mes es más corto (p. ej. 31 en febrero)."""
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


def sumar_meses(d, meses, dia=None):
    total = d.year * 12 + d.month - 1 + meses
    return dia_del_mes(total // 12, total % 12 + 1, dia or d.day)


def meses_entre(desde, hasta):
    return (hasta.year - desde.year) * 12 + hasta.month - desde.month


def periodo(d):
    return f"{d.year:04d}-{d.month:02d}"


# ---------- Lo que escribe el usuario ----------

def leer_importe(texto):
    """'1.850,50' / '1850.5' / '1850' / '50€' -> float. None si no es un importe válido (> 0)."""
    limpio = texto.strip().lower().replace("€", "").replace("eur", "").replace(" ", "")
    if not limpio or not re.fullmatch(r"[\d.,]+", limpio):
        return None
    if "," in limpio and "." in limpio:
        limpio = limpio.replace(".", "").replace(",", ".") if limpio.rfind(",") > limpio.rfind(".") \
            else limpio.replace(",", "")
    elif "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", limpio):
        limpio = limpio.replace(".", "")
    try:
        cantidad = round(float(limpio), 2)
    except ValueError:
        return None
    return cantidad if cantidad > 0 else None


def leer_entero(texto, minimo, maximo):
    try:
        numero = int(texto.strip())
    except ValueError:
        return None
    return numero if minimo <= numero <= maximo else None


def leer_fecha(texto, hoy):
    """'hoy', 'mañana', '20/11', '20-11-2026', '20/11/26' -> date (si no hay año, la próxima)."""
    t = texto.strip().lower()
    if t == "hoy":
        return hoy
    if t in ("mañana", "manana"):
        return hoy + timedelta(days=1)
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?", t)
    if not m:
        return None
    dia, mes = int(m.group(1)), int(m.group(2))
    anio = int(m.group(3)) if m.group(3) else hoy.year
    if anio < 100:
        anio += 2000
    try:
        fecha = date(anio, mes, dia)
    except ValueError:
        return None
    if not m.group(3) and fecha < hoy - timedelta(days=60):
        fecha = date(anio + 1, mes, dia)
    return fecha


def leer_mes(texto, hoy):
    """'08/2027', '8/27', 'agosto 2027', 'agosto' -> último día de ese mes (futuro)."""
    t = texto.strip().lower()
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{2,4})", t)
    if m:
        mes, anio = int(m.group(1)), int(m.group(2))
    else:
        m = re.fullmatch(r"([a-záéíóú]+)(?:\s+(?:de\s+)?(\d{2,4}))?", t)
        if not m:
            return None
        nombre = m.group(1)
        coincide = [i for i, n in enumerate(MESES) if n.startswith(nombre[:3])]
        if not coincide:
            return None
        mes = coincide[0] + 1
        anio = int(m.group(2)) if m.group(2) else (hoy.year if mes >= hoy.month else hoy.year + 1)
    if anio < 100:
        anio += 2000
    if not 1 <= mes <= 12:
        return None
    final = dia_del_mes(anio, mes, 31)
    return final if final >= hoy else None


def leer_hora(texto):
    m = re.fullmatch(r"(\d{1,2})(?:[:.h](\d{2}))?", texto.strip().lower())
    if not m:
        return None
    horas, minutos = int(m.group(1)), int(m.group(2) or 0)
    return f"{horas:02d}:{minutos:02d}" if horas < 24 and minutos < 60 else None
