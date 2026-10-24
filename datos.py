"""Base de datos local (SQLite) del bot.

Guarda los saldos diarios, los movimientos del banco, los cobros, las deudas, las metas y los
recordatorios. Es del usuario: las actualizaciones nunca la sustituyen (está en .gitignore) y
cada día se guarda una copia de seguridad en la carpeta «copias» (se conservan las 14 últimas).
"""
import logging
import sqlite3
from contextlib import contextmanager

import config

RUTA = config.BASE / "datos.db"
COPIAS = config.BASE / "copias"
COPIAS_A_CONSERVAR = 14

ESQUEMA = """
CREATE TABLE IF NOT EXISTS saldos (
    fecha TEXT NOT NULL, uid TEXT NOT NULL, importe REAL NOT NULL, moneda TEXT NOT NULL DEFAULT 'EUR',
    PRIMARY KEY (fecha, uid));
CREATE TABLE IF NOT EXISTS movimientos (
    id TEXT PRIMARY KEY, uid TEXT NOT NULL, fecha TEXT NOT NULL, importe REAL NOT NULL,
    moneda TEXT NOT NULL DEFAULT 'EUR', descripcion TEXT NOT NULL DEFAULT '', contraparte TEXT NOT NULL DEFAULT '',
    mcc TEXT NOT NULL DEFAULT '', categoria TEXT NOT NULL DEFAULT '', interno INTEGER NOT NULL DEFAULT 0,
    importado TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS movimientos_fecha ON movimientos (fecha);
CREATE TABLE IF NOT EXISTS reglas (clave TEXT PRIMARY KEY, categoria TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ingresos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, importe REAL NOT NULL, tipo TEXT NOT NULL,
    nota TEXT NOT NULL DEFAULT '', movimiento_id TEXT, creado TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deudas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, tipo TEXT NOT NULL,
    importe REAL NOT NULL, cuota REAL, cuotas_total INTEGER, dia INTEGER, fecha TEXT, desde TEXT,
    avisar_dias INTEGER NOT NULL DEFAULT 2, aplazamientos INTEGER NOT NULL DEFAULT 0,
    activa INTEGER NOT NULL DEFAULT 1, creada TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, deuda_id INTEGER NOT NULL, periodo TEXT NOT NULL,
    importe REAL NOT NULL, fecha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS aplazos (
    deuda_id INTEGER NOT NULL, periodo TEXT NOT NULL, nueva_fecha TEXT NOT NULL, PRIMARY KEY (deuda_id, periodo));
CREATE TABLE IF NOT EXISTS metas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, objetivo REAL NOT NULL, fecha_limite TEXT NOT NULL,
    ahorrado REAL NOT NULL DEFAULT 0, uid TEXT, activa INTEGER NOT NULL DEFAULT 1, completada TEXT,
    creada TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS aportaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, meta_id INTEGER NOT NULL, fecha TEXT NOT NULL, importe REAL NOT NULL);
CREATE TABLE IF NOT EXISTS recordatorios (
    id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT NOT NULL, frecuencia TEXT NOT NULL, fecha TEXT,
    dia_semana INTEGER, dia_mes INTEGER, hora TEXT NOT NULL, activo INTEGER NOT NULL DEFAULT 1, creado TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS enviados (clave TEXT PRIMARY KEY, momento TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pospuestos (clave TEXT PRIMARY KEY, hasta TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cola_avisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT NOT NULL, botones TEXT NOT NULL DEFAULT '[]',
    desde TEXT NOT NULL, enviado TEXT);
CREATE TABLE IF NOT EXISTS acciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tabla TEXT NOT NULL, fila_id INTEGER NOT NULL,
    deshacer TEXT NOT NULL, descripcion TEXT NOT NULL, momento TEXT NOT NULL);
"""


@contextmanager
def conexion():
    con = sqlite3.connect(RUTA, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def iniciar():
    with conexion() as con:
        con.executescript(ESQUEMA)
        migrar(con)


def migrar(con):
    """Cambios de esquema entre versiones: solo se añaden columnas (nunca se borran ni renombran)."""
    columnas = {fila["name"] for fila in con.execute("PRAGMA table_info(deudas)")}
    if "sentido" not in columnas:  # v6: deudas que debes («debo») y que te deben («me_deben»)
        con.execute("ALTER TABLE deudas ADD COLUMN sentido TEXT NOT NULL DEFAULT 'debo'")
    # Las «me deben» de la v5 (solo nombre e importe) pasan a «me deben, sin fecha».
    con.execute("UPDATE deudas SET sentido = 'me_deben', tipo = 'sin_fecha' WHERE tipo = 'me_deben'")
    if "modo" not in columnas:  # v7: cuándo se paga cada cuota (día fijo, al cobrar o sin día fijo)
        con.execute("ALTER TABLE deudas ADD COLUMN modo TEXT NOT NULL DEFAULT 'dia'")
    if "si_no_paga" not in columnas:  # v7: qué hacer con una cuota no pagada en su mes
        con.execute("ALTER TABLE deudas ADD COLUMN si_no_paga TEXT NOT NULL DEFAULT 'preguntar'")
    con.execute("CREATE TABLE IF NOT EXISTS saltos (deuda_id INTEGER NOT NULL, periodo TEXT NOT NULL, "
                "decision TEXT NOT NULL, fecha TEXT NOT NULL, PRIMARY KEY (deuda_id, periodo))")


def todos(sql, *parametros):
    with conexion() as con:
        return [dict(fila) for fila in con.execute(sql, parametros)]


def tabla(sql, *parametros):
    """(nombres de columna, filas como listas) — también cuando no hay filas."""
    with conexion() as con:
        cursor = con.execute(sql, parametros)
        return [c[0] for c in cursor.description], [list(f) for f in cursor.fetchall()]


def uno(sql, *parametros):
    filas = todos(sql, *parametros)
    return filas[0] if filas else None


def valor(sql, *parametros):
    fila = uno(sql, *parametros)
    return next(iter(fila.values())) if fila else None


def ejecutar(sql, *parametros):
    with conexion() as con:
        return con.execute(sql, parametros).lastrowid


def varios(sql, filas):
    with conexion() as con:
        con.executemany(sql, filas)


# ---------- Acciones que se pueden deshacer ----------

def registrar_accion(tabla, fila_id, deshacer, descripcion):
    """Guarda cómo deshacer una acción (SQL con un único parámetro: el id de la fila)."""
    return ejecutar("INSERT INTO acciones (tabla, fila_id, deshacer, descripcion, momento) VALUES (?, ?, ?, ?, ?)",
                    tabla, fila_id, deshacer, descripcion, config.ahora().isoformat())


def deshacer(accion_id, minutos=10):
    """Deshace la acción si tiene menos de `minutos`. Devuelve su descripción o None."""
    accion = uno("SELECT * FROM acciones WHERE id = ?", accion_id)
    if not accion:
        return None
    from datetime import datetime
    if (config.ahora() - datetime.fromisoformat(accion["momento"])).total_seconds() > minutos * 60:
        return None
    with conexion() as con:
        for sentencia in accion["deshacer"].split(";"):
            if sentencia.strip():
                con.execute(sentencia, (accion["fila_id"],))
        con.execute("DELETE FROM acciones WHERE id = ?", (accion_id,))
    return accion["descripcion"]


# ---------- Avisos ya enviados / pospuestos ----------

def enviado(clave):
    return uno("SELECT 1 AS si FROM enviados WHERE clave = ?", clave) is not None


def marcar_enviado(clave):
    ejecutar("INSERT OR REPLACE INTO enviados (clave, momento) VALUES (?, ?)", clave, config.ahora().isoformat())


def ultimo_envio(prefijo):
    return valor("SELECT MAX(momento) FROM enviados WHERE clave LIKE ?", prefijo + "%")


def posponer(clave, hasta):
    ejecutar("INSERT OR REPLACE INTO pospuestos (clave, hasta) VALUES (?, ?)", clave, hasta.isoformat())


def pospuesto_hasta(clave):
    from datetime import datetime
    hasta = valor("SELECT hasta FROM pospuestos WHERE clave = ?", clave)
    return datetime.fromisoformat(hasta) if hasta else None


def encolar_aviso(texto, botones=None, desde=None):
    """Aviso para enviar por Telegram a partir de `desde` (por defecto, hoy a las 09:00).

    Se usa para lo que se descubre de madrugada (actualización de las 00:00): nunca se avisa a esa hora.
    """
    import json
    ahora = config.ahora()
    desde = desde or max(ahora, ahora.replace(hour=9, minute=0, second=0, microsecond=0))
    ejecutar("INSERT INTO cola_avisos (texto, botones, desde) VALUES (?, ?, ?)", texto, json.dumps(botones or []),
             desde.isoformat())


def avisos_listos():
    return todos("SELECT * FROM cola_avisos WHERE enviado IS NULL AND desde <= ? ORDER BY id", config.ahora().isoformat())


def marcar_aviso_enviado(aviso_id):
    ejecutar("UPDATE cola_avisos SET enviado = ? WHERE id = ?", config.ahora().isoformat(), aviso_id)


# ---------- Copia de seguridad ----------

def copia_de_seguridad():
    """Una copia al día de datos.db; se conservan las COPIAS_A_CONSERVAR más recientes."""
    COPIAS.mkdir(exist_ok=True)
    destino = COPIAS / f"datos_{config.hoy()}.db"
    if destino.exists():
        return
    try:
        with conexion() as origen:
            copia = sqlite3.connect(destino)
            try:
                origen.backup(copia)
            finally:
                copia.close()
    except sqlite3.Error:
        logging.getLogger("detalle").exception("No se ha podido hacer la copia de seguridad")
        return
    for vieja in sorted(COPIAS.glob("datos_*.db"))[:-COPIAS_A_CONSERVAR]:
        vieja.unlink(missing_ok=True)
