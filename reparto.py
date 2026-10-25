"""💸 Reparto automático (v11): tu libre es fijo y TODO lo que sobra de cada cobro va a tus metas.

En cada cobro:  lo que entra − todos los pagos del ciclo − tu libre (LIBRE_MINIMO) − lo que faltaba antes
del cobro (el «hueco», si llegabas en negativo) = sobrante, que se reparte entre las metas según REPARTO_MODO:
- «necesario» (por defecto): primero lo necesario para que cada meta llegue a su fecha (si no alcanza para
  todas, por orden de prioridad) y lo que quede, en cascada desde la 1.ª prioritaria.
- «cascada»: todo a la 1.ª prioritaria hasta completarla, luego a la 2.ª, etc.
Orden: prioridad (1.ª, 2.ª…), después el colchón y después la fecha límite más cercana.
Si todas las metas están completas, el sobrante se queda libre.

La misma regla se usa en la proyección y en la vida real. En la vida real el reparto se fija al registrar
el salario (tablas reparto_ciclos y reparto_metas) y no cambia durante el ciclo; lo que te deben solo
entra cuando confirmas que te han pagado (reparto aparte, sin tocar tu libre).
"""
from datetime import date

import config
import datos

MODOS = {"necesario": "🧮 Lo necesario para cada fecha y el resto a la 1.ª prioritaria",
         "cascada": "🥇 En cascada: todo a la 1.ª prioritaria hasta completarla, luego a la siguiente"}


def activo():
    return config.valor("REPARTO_AUTO") == "1"


def modo():
    valor = config.valor("REPARTO_MODO")
    return valor if valor in MODOS else "necesario"


def _campo(meta, cambios, campo):
    cfg = (cambios or {}).get(meta["id"], {})
    return cfg[campo] if campo in cfg else meta[campo]


def orden(lista, cambios=None):
    """Metas en el orden en que reciben dinero: prioridad, colchón, fecha límite más cercana."""
    def clave(meta):
        prioridad = _campo(meta, cambios, "prioridad") or 0
        return (prioridad == 0, prioridad, meta["especial"] != "colchon", _campo(meta, cambios, "fecha_limite"),
                meta["id"])
    return sorted(lista, key=clave)


def necesaria(meta, ahorrado, fecha_cobro, cambios=None):
    """Lo justo en este cobro para llegar a la fecha límite."""
    import metas
    falta = max(0.0, meta["objetivo"] - ahorrado)
    limite = date.fromisoformat(_campo(meta, cambios, "fecha_limite"))
    return round(falta / metas.meses_hasta(limite, fecha_cobro), 2)


def repartir(disponible, estado, fecha_cobro, cambios=None, forma=None):
    """Reparte `disponible` entre [(meta, ahorrado)]. Devuelve ({meta_id: importe}, lo que sobra)."""
    forma = forma or modo()
    restante = max(0.0, round(disponible, 2))
    ahorrado = {m["id"]: a for m, a in estado}
    lista = [m for m in orden([m for m, _ in estado], cambios) if m["objetivo"] - ahorrado[m["id"]] > 0.004]
    asignado = {m["id"]: 0.0 for m in lista}
    if forma == "necesario":
        for m in lista:
            parte = min(necesaria(m, ahorrado[m["id"]], fecha_cobro, cambios), restante)
            asignado[m["id"]] += parte
            restante -= parte
    for m in lista:  # cascada (o el resto, en «necesario»)
        falta = m["objetivo"] - ahorrado[m["id"]] - asignado[m["id"]]
        parte = min(max(0.0, falta), restante)
        asignado[m["id"]] += parte
        restante -= parte
    return {k: round(v, 2) for k, v in asignado.items() if v > 0.004}, round(restante, 2)


# ---------- Vida real: el reparto de cada ciclo ----------

def fijar_ciclo(fecha_salario, importe, hueco=0.0):
    """Al registrar el salario: calcula y guarda el reparto del ciclo. Devuelve el resumen (o None si no está activo)."""
    if not activo():
        return None
    import deudas
    import metas
    from proyeccion import libre_minimo
    ciclo_clave = fecha_salario.isoformat()
    pagos = round(sum(i["importe"] for i in deudas.pendientes(fecha_salario)), 2)
    libre = libre_minimo()
    disponible = round(importe - pagos - libre - hueco, 2)
    estado = [(m, metas.ahorrado(m)) for m in metas.activas()]
    asignado, sobra = repartir(disponible, estado, fecha_salario)
    a_metas = round(sum(asignado.values()), 2)
    datos.ejecutar("DELETE FROM reparto_metas WHERE ciclo = ?", ciclo_clave)
    datos.varios("INSERT INTO reparto_metas (meta_id, ciclo, importe) VALUES (?, ?, ?)",
                 [(meta_id, ciclo_clave, v) for meta_id, v in asignado.items()])
    datos.ejecutar("INSERT OR REPLACE INTO reparto_ciclos (ciclo, salario, pagos, libre, hueco, a_metas, sobra, modo, "
                   "creado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", ciclo_clave, importe, pagos, libre, round(hueco, 2),
                   a_metas, sobra, modo(), config.ahora().isoformat())
    return del_ciclo(ciclo_clave)


def hueco_antes_de_cobrar(importe, ya_en_saldo):
    """Lo que faltaba antes de este cobro (dinero libre sin metas en negativo). Si el banco ya trajo el salario,
    se descuenta para no contarlo dos veces."""
    import analisis
    import deudas
    import metas
    s = analisis.saldo_actual()
    if not s:
        return 0.0
    neto, _ = deudas.neto(s["total"])
    libre = analisis.dinero_libre(neto) + sum(metas.pendiente_ciclo(m) for m in metas.activas())
    if ya_en_saldo:
        libre -= importe
    return round(max(0.0, -libre), 2)


def fijar_ciclo_actual():
    """Al activar el reparto a mitad de ciclo: este ciclo también se reparte, con el dinero libre que tienes ahora
    (sin las aportaciones a metas aún pendientes) menos tu libre. Si no llega, las metas reciben 0 € este ciclo.
    No hace nada si el ciclo ya tiene reparto o aún no hay salario registrado."""
    import analisis
    import ciclo
    import deudas
    import metas
    from proyeccion import libre_minimo
    salario = ciclo.ultimo_salario()
    if not activo() or not salario:
        return None
    clave = ciclo.inicio().isoformat()
    if datos.uno("SELECT 1 AS si FROM reparto_ciclos WHERE ciclo = ?", clave):
        return del_ciclo(clave)
    s = analisis.saldo_actual()
    if not s:
        return None
    neto, pendientes = deudas.neto(s["total"])
    libre_sin_metas = analisis.dinero_libre(neto) + sum(metas.pendiente_ciclo(m) for m in metas.activas())
    libre = libre_minimo()
    estado = [(m, metas.ahorrado(m)) for m in metas.activas() if not metas.estado_ciclo(m)]
    asignado, sobra = repartir(libre_sin_metas - libre, estado, ciclo.inicio())
    datos.varios("INSERT INTO reparto_metas (meta_id, ciclo, importe) VALUES (?, ?, ?)",
                 [(meta_id, clave, v) for meta_id, v in asignado.items()])
    datos.ejecutar("INSERT OR REPLACE INTO reparto_ciclos (ciclo, salario, pagos, libre, hueco, a_metas, sobra, modo, "
                   "creado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", clave, salario["importe"],
                   round(sum(i["importe"] for i in pendientes), 2), libre, round(max(0.0, -libre_sin_metas), 2),
                   round(sum(asignado.values()), 2), sobra, modo(), config.ahora().isoformat())
    return del_ciclo(clave)


def del_ciclo(ciclo_clave):
    """Resumen guardado del reparto de un ciclo: dict con salario, pagos, libre, hueco, a_metas, sobra, metas."""
    fila = datos.uno("SELECT * FROM reparto_ciclos WHERE ciclo = ?", ciclo_clave)
    if not fila:
        return None
    resumen = dict(fila)
    resumen["metas"] = {f["meta_id"]: f["importe"] for f in
                        datos.todos("SELECT * FROM reparto_metas WHERE ciclo = ?", ciclo_clave)}
    return resumen


def de_meta(meta_id, ciclo_clave):
    """Lo que le toca a una meta en el reparto fijado de un ciclo (None si ese ciclo no tiene reparto)."""
    if not activo() or not datos.uno("SELECT 1 AS si FROM reparto_ciclos WHERE ciclo = ?", ciclo_clave):
        return None
    return datos.valor("SELECT importe FROM reparto_metas WHERE meta_id = ? AND ciclo = ?", meta_id, ciclo_clave) or 0.0


def extra(importe):
    """Dinero que entra fuera del salario (p. ej. te devuelven algo): todo a las metas, sin tocar tu libre."""
    import ciclo
    import metas
    estado = [(m, metas.ahorrado(m)) for m in metas.activas()]
    return repartir(importe, estado, ciclo.inicio())
