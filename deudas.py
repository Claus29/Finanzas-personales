"""Deudas (lo que debes y lo que te deben), cuotas, gastos fijos y suscripciones, y el saldo neto.

Sentido:
- debo     : dinero que tú pagas. Del saldo neto se resta lo que toca en el ciclo y no está pagado.
- me_deben : dinero que te tienen que pagar. NUNCA se suma al saldo neto (se muestra aparte).

Tipos:
- fecha       : pago único con día de pago («Juan, 200 €, el 20/11»). Ambos sentidos.
- cobro       : pago único en cuanto cobres, una sola vez («Mamá, 150 €»). Solo «debo».
- plazos      : un total pagado en cuotas («Mamá, 409,25 € en cuotas de 80 €»). Ambos sentidos.
- fijo        : gasto fijo cada periodo, sin fin («Alquiler 650 €»). Solo «debo».
- suscripcion : como fijo, para Netflix, Spotify... (día fijo). Solo «debo».
- sin_fecha   : aún sin día de pago (se le pone después). Solo «me_deben».

Modo (cuándo toca cada cuota de plazos y gastos fijos):
- dia   : un día fijo de cada mes (periodo «AAAA-MM»).
- cobro : en cada cobro de tu salario (periodo = fecha del salario «AAAA-MM-DD»).
- sin   : sin día fijo, en algún momento del mes (vence el último día; solo «me_deben»).

Las deudas a plazos se llevan por lo que QUEDA (total − pagado):
- Cada periodo toca una cuota (o lo que quede, si es menos).
- «Otra cantidad» cubre el periodo y la diferencia va al final (más o menos cuotas restantes).
- Una cuota no pagada en su periodo NUNCA cuenta como pagada. Se puede «pasar al mes siguiente»
  (todo el plan se retrasa un mes) o pagar «las dos juntas» el mes siguiente; o dejarla pendiente.
"""
import math
from datetime import date, timedelta

import ciclo
import config
import datos
from formato import dia_del_mes, euros, periodo, sumar_meses

TIPOS = {
    "fecha": "📅 Pago único",
    "cobro": "💶 Pago único al cobrar",
    "plazos": "🔁 A plazos",
    "fijo": "🏠 Gasto fijo",
    "suscripcion": "📺 Suscripción",
    "sin_fecha": "🕐 Sin fecha",
}
TIPOS_POR_SENTIDO = {
    "debo": ["fecha", "cobro", "plazos", "fijo", "suscripcion"],
    "me_deben": ["fecha", "plazos", "sin_fecha"],
}
MODOS = {"dia": "📅 día fijo", "cobro": "💶 al cobrar", "sin": "🕐 sin día fijo"}
SI_NO_PAGA = {
    "preguntar": "❓ preguntarme cada vez",
    "pasar": "➡️ pasar al mes siguiente",
    "juntas": "➕ las dos juntas el mes siguiente",
}
MENSUALES = ("plazos", "fijo", "suscripcion")
UNICOS = ("fecha", "cobro", "sin_fecha")
ACTIVA, TERMINADA, BORRADA = 1, 0, -1
INICIAL = "inicial"  # periodo de lo que ya estaba pagado al apuntar la deuda (no cubre ningún mes)


def hoy():
    return config.ahora().date()


def obtener(deuda_id):
    return datos.uno("SELECT * FROM deudas WHERE id = ?", deuda_id)


def activas(sentido=None):
    filas = datos.todos("SELECT * FROM deudas WHERE activa = 1 ORDER BY id")
    return filas if sentido is None else [d for d in filas if d["sentido"] == sentido]


def me_deben(deuda):
    return deuda["sentido"] == "me_deben"


def modo(deuda):
    return deuda.get("modo") or "dia"


def pagos(deuda_id):
    return datos.todos("SELECT * FROM pagos WHERE deuda_id = ? ORDER BY fecha, id", deuda_id)


def periodos_pagados(deuda_id):
    return {p["periodo"] for p in pagos(deuda_id)}


def saltos(deuda_id):
    return {s["periodo"]: s["decision"] for s in datos.todos("SELECT * FROM saltos WHERE deuda_id = ?", deuda_id)}


def pagado_total(deuda):
    return round(sum(p["importe"] for p in pagos(deuda["id"])), 2)


def cuota(deuda):
    return deuda["cuota"] if deuda["tipo"] == "plazos" else deuda["importe"]


# ---------- Periodos y cuotas ----------

def _mes(texto):
    anio, mes = (int(x) for x in texto[:7].split("-"))
    return date(anio, mes, 1)


def fin_de_mes(d):
    return dia_del_mes(d.year, d.month, 31)


def nombre_periodo(per):
    from formato import MESES
    if len(per) == 7:
        return MESES[int(per[5:7]) - 1]
    return f"el cobro del {per[8:10]}/{per[5:7]}"


def vencimiento(deuda, per):
    """Día en que vence el periodo `per`, teniendo en cuenta los aplazamientos."""
    aplazo = datos.valor("SELECT nueva_fecha FROM aplazos WHERE deuda_id = ? AND periodo = ?", deuda["id"], per)
    if aplazo:
        return date.fromisoformat(aplazo)
    if len(per) == 10:  # cobro: el día del salario
        return date.fromisoformat(per)
    mes = _mes(per)
    if modo(deuda) == "sin":
        return fin_de_mes(mes)
    return dia_del_mes(mes.year, mes.month, deuda["dia"] or 1)


def aplazada(deuda, per):
    if per == "unico":
        return deuda["aplazamientos"] > 0
    return datos.valor("SELECT 1 FROM aplazos WHERE deuda_id = ? AND periodo = ?", deuda["id"], per) is not None


def periodos(deuda, hasta):
    """[(periodo, vence)] de una deuda mensual cuyo vencimiento es anterior a `hasta`."""
    if not deuda["desde"]:
        return []
    if modo(deuda) == "cobro":
        salarios = datos.todos("SELECT fecha FROM ingresos WHERE tipo = 'salario' AND fecha >= ? AND fecha <= ? "
                               "ORDER BY fecha", deuda["desde"][:10], hoy().isoformat())
        lista = [(s["fecha"], vencimiento(deuda, s["fecha"])) for s in salarios]
    else:
        lista = []
        mes = _mes(deuda["desde"])
        while mes < hasta + timedelta(days=62) and len(lista) < 600:
            per = periodo(mes)
            lista.append((per, vencimiento(deuda, per)))
            mes = sumar_meses(mes, 1, 1)
    return [(per, vence) for per, vence in lista if vence < hasta]


def cuotas_pendientes(deuda, hasta):
    """Cuotas sin pagar con vencimiento anterior a `hasta`: [{periodo, vence, importe, juntas}].

    `juntas` es cuántas cuotas incluye (más de 1 si se decidió pagar «las dos juntas»).
    """
    pagados = periodos_pagados(deuda["id"])
    decisiones = saltos(deuda["id"])
    importe_cuota = cuota(deuda)
    queda = restante(deuda)[0] if deuda["tipo"] == "plazos" else math.inf
    acumulado, acumuladas = 0.0, 0
    lista = []
    for per, vence in periodos(deuda, hasta):
        if queda <= 0.004:
            break
        if per in pagados:
            acumulado, acumuladas = 0.0, 0
            continue
        decision = decisiones.get(per)
        if decision == "pasar":
            continue  # este periodo no toca: todo el plan se retrasa
        if decision == "juntas":
            acumulado += importe_cuota
            acumuladas += 1
            continue
        importe = round(min(importe_cuota + acumulado, queda), 2)
        queda -= importe
        lista.append({"periodo": per, "vence": vence, "importe": importe, "juntas": acumuladas + 1})
        acumulado, acumuladas = 0.0, 0
    return lista


def restante(deuda):
    """(dinero que falta, cuotas que faltan o None). Para gastos fijos y suscripciones, el importe del periodo."""
    if deuda["tipo"] == "plazos":
        queda = max(0.0, round(deuda["importe"] - pagado_total(deuda), 2))
        return queda, math.ceil(queda / deuda["cuota"] - 1e-9) if deuda["cuota"] else 0
    return deuda["importe"], None


def cuotas_hechas(deuda):
    return len([p for p in pagos(deuda["id"]) if p["periodo"] not in (INICIAL, "unico")])


def numero_cuota(deuda):
    """(número de la próxima cuota, total de cuotas) para mostrar «cuota 3/6»."""
    hechas = cuotas_hechas(deuda)
    return hechas + 1, hechas + (restante(deuda)[1] or 0)


def salario_desde(fecha_iso, hasta=None):
    """Primer salario registrado en o después de `fecha_iso` (hasta hoy)."""
    return datos.uno("SELECT * FROM ingresos WHERE tipo = 'salario' AND fecha >= ? AND fecha <= ? ORDER BY fecha LIMIT 1",
                     fecha_iso, (hasta or hoy()).isoformat())


def pendientes(d=None, sentido="debo"):
    """Pagos del ciclo actual aún no marcados: [{deuda, periodo, importe, vence, atrasada, juntas}].

    Con sentido «debo» es lo que se resta del saldo neto; con «me_deben», lo que te tienen que pagar.
    """
    d = d or hoy()
    proximo = ciclo.proximo_cobro(d)
    if sentido == "me_deben":
        # Lo que te deben va por meses (no depende de cuándo cobras tú): hasta el final de este mes.
        proximo = max(proximo, fin_de_mes(d) + timedelta(days=1))
    lista = []
    for deuda in activas(sentido):
        if deuda["tipo"] == "fecha":
            vence = date.fromisoformat(deuda["fecha"])
            if vence < proximo:
                lista.append({"deuda": deuda, "periodo": "unico", "importe": deuda["importe"], "vence": vence, "juntas": 1})
        elif deuda["tipo"] == "cobro":
            salario = salario_desde(deuda["desde"], d)
            if salario:
                lista.append({"deuda": deuda, "periodo": "unico", "importe": deuda["importe"],
                              "vence": date.fromisoformat(salario["fecha"]), "juntas": 1})
        elif deuda["tipo"] in MENSUALES:
            hasta = max(proximo, fin_de_mes(d) + timedelta(days=1)) if modo(deuda) == "sin" else proximo
            for item in cuotas_pendientes(deuda, hasta):
                if modo(deuda) == "sin" and _mes(item["periodo"]) > date(d.year, d.month, 1):
                    continue
                lista.append({"deuda": deuda, **item})
    for item in lista:
        item["atrasada"] = item["vence"] < d
    return sorted(lista, key=lambda x: x["vence"])


def por_cobrar(d=None):
    """Lo que te tienen que pagar en este ciclo (no se suma al saldo neto)."""
    return pendientes(d, "me_deben")


def comprometido_proximo_cobro(d=None):
    """[(deuda, importe)] que se pagará con el próximo salario (aún no se resta del neto)."""
    d = d or hoy()
    lista = []
    for deuda in activas("debo"):
        if deuda["tipo"] == "cobro" and not salario_desde(deuda["desde"], d):
            lista.append((deuda, deuda["importe"]))
        elif deuda["tipo"] in MENSUALES and modo(deuda) == "cobro":
            queda = restante(deuda)[0] if deuda["tipo"] == "plazos" else cuota(deuda)
            if queda > 0.004:
                lista.append((deuda, round(min(cuota(deuda), queda), 2)))
    return lista


def neto(saldo_total, d=None):
    """(saldo neto, lista de pendientes del ciclo). Lo que te deben no cuenta."""
    lista = pendientes(d, "debo")
    return round(saldo_total - sum(x["importe"] for x in lista), 2), lista


def proximo_pago(deuda, d=None):
    """(fecha, periodo, importe) del próximo pago sin hacer, o None.

    Para las cuotas «al cobrar» aún no cobradas, el periodo es None (se sabrá al cobrar).
    """
    d = d or hoy()
    if deuda["tipo"] == "fecha":
        return date.fromisoformat(deuda["fecha"]), "unico", deuda["importe"]
    if deuda["tipo"] == "cobro":
        salario = salario_desde(deuda["desde"], d)
        return (date.fromisoformat(salario["fecha"]) if salario else ciclo.proximo_cobro(d)), "unico", deuda["importe"]
    if deuda["tipo"] not in MENSUALES:
        return None
    if deuda["tipo"] == "plazos" and restante(deuda)[0] <= 0.004:
        return None
    lejos = sumar_meses(d, 600 if deuda["tipo"] == "plazos" else 14, 1)
    lista = cuotas_pendientes(deuda, lejos)
    if lista:
        return lista[0]["vence"], lista[0]["periodo"], lista[0]["importe"]
    if modo(deuda) == "cobro":
        queda = restante(deuda)[0] if deuda["tipo"] == "plazos" else cuota(deuda)
        return ciclo.proximo_cobro(d), None, round(min(cuota(deuda), queda), 2)
    return None


def fecha_fin(deuda):
    """Fecha estimada de la última cuota de unos plazos (None si no aplica o ya está pagada)."""
    if deuda["tipo"] != "plazos":
        return None
    cuotas_faltan = restante(deuda)[1]
    proximo = proximo_pago(deuda)
    if not cuotas_faltan or not proximo:
        return None
    return sumar_meses(proximo[0], cuotas_faltan - 1, proximo[0].day)


# ---------- Cambios ----------

def crear(nombre, tipo, importe, cuota=None, cuotas_total=None, dia=None, fecha=None, desde=None, sentido="debo",
          modo="dia", si_no_paga="preguntar", ya_pagado=0.0):
    deuda_id = datos.ejecutar(
        "INSERT INTO deudas (nombre, tipo, importe, cuota, cuotas_total, dia, fecha, desde, creada, sentido, modo, "
        "si_no_paga) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nombre, tipo, round(importe, 2), cuota, cuotas_total, dia, fecha, desde, config.ahora().isoformat(), sentido,
        modo, si_no_paga)
    if ya_pagado and ya_pagado > 0:
        datos.ejecutar("INSERT INTO pagos (deuda_id, periodo, importe, fecha) VALUES (?, ?, ?, ?)",
                       deuda_id, INICIAL, round(ya_pagado, 2), hoy().isoformat())
    accion = datos.registrar_accion("deudas", deuda_id, "DELETE FROM pagos WHERE deuda_id = ?1; "
                                                        "DELETE FROM deudas WHERE id = ?1", f"«{nombre}» apuntada")
    return deuda_id, accion


def pagar(deuda_id, per, importe=None):
    """Marca un pago (o un cobro, si te deben). Devuelve (texto, id de acción para deshacer).

    Para cuotas, `importe` distinto de la cuota es «otra cantidad»: cubre el periodo igualmente.
    """
    deuda = obtener(deuda_id)
    fecha = hoy().isoformat()
    cobro = me_deben(deuda)
    if deuda["tipo"] in UNICOS:
        parcial = importe is not None and importe < deuda["importe"] - 0.004
        pagado = importe if parcial else deuda["importe"]
        pago_id = datos.ejecutar("INSERT INTO pagos (deuda_id, periodo, importe, fecha) VALUES (?, ?, ?, ?)",
                                 deuda_id, "unico", pagado, fecha)
        if parcial:
            datos.ejecutar("UPDATE deudas SET importe = ROUND(importe - ?, 2) WHERE id = ?", pagado, deuda_id)
            deshacer = ("UPDATE deudas SET importe = ROUND(importe + (SELECT importe FROM pagos WHERE id = ?1), 2) "
                        "WHERE id = (SELECT deuda_id FROM pagos WHERE id = ?1); DELETE FROM pagos WHERE id = ?1")
            quedan = round(deuda["importe"] - pagado, 2)
            texto = f"{'te ha pagado' if cobro else 'pagado'} {euros(pagado)}; quedan {euros(quedan)}"
        else:
            datos.ejecutar("UPDATE deudas SET activa = 0 WHERE id = ?", deuda_id)
            deshacer = ("UPDATE deudas SET activa = 1 WHERE id = (SELECT deuda_id FROM pagos WHERE id = ?1); "
                        "DELETE FROM pagos WHERE id = ?1")
            texto = "cobrada del todo 🎉" if cobro else "pagada"
    else:
        if importe is None:
            pendiente = next((c for c in cuotas_pendientes(deuda, sumar_meses(hoy(), 600, 1)) if c["periodo"] == per), None)
            importe = pendiente["importe"] if pendiente else cuota(deuda)
        if deuda["tipo"] == "plazos":
            importe = min(importe, restante(deuda)[0]) or importe
        pago_id = datos.ejecutar("INSERT INTO pagos (deuda_id, periodo, importe, fecha) VALUES (?, ?, ?, ?)",
                                 deuda_id, per, round(importe, 2), fecha)
        deshacer = ("UPDATE deudas SET activa = 1 WHERE id = (SELECT deuda_id FROM pagos WHERE id = ?1); "
                    "DELETE FROM pagos WHERE id = ?1")
        deuda_ahora = obtener(deuda_id)
        if deuda["tipo"] == "plazos":
            queda, cuotas_faltan = restante(deuda_ahora)
            if queda <= 0.004:
                datos.ejecutar("UPDATE deudas SET activa = 0 WHERE id = ?", deuda_id)
                texto = "última cuota: ¡te lo ha devuelto todo! 🎉" if cobro else "última cuota: ¡deuda terminada! 🎉"
            else:
                texto = (f"{'cobrados' if cobro else 'pagados'} {euros(importe)}; quedan {euros(queda)} "
                         f"({cuotas_faltan} cuota{'s' if cuotas_faltan != 1 else ''})")
        else:
            texto = f"pago de {nombre_periodo(per)} hecho"
    accion = datos.registrar_accion("pagos", pago_id, deshacer, f"{'Cobro' if cobro else 'Pago'} de «{deuda['nombre']}»")
    return texto, accion


def saltar(deuda_id, per, decision):
    """Cuota no pagada en su periodo: «pasar» (el plan se retrasa) o «juntas» (se paga con la siguiente).

    Nunca se registra como pagada. Devuelve (texto, id de acción para deshacer).
    """
    deuda = obtener(deuda_id)
    datos.ejecutar("INSERT OR REPLACE INTO saltos (deuda_id, periodo, decision, fecha) VALUES (?, ?, ?, ?)",
                   deuda_id, per, decision, hoy().isoformat())
    fila = datos.valor("SELECT rowid FROM saltos WHERE deuda_id = ? AND periodo = ?", deuda_id, per)
    accion = datos.registrar_accion("saltos", fila, "DELETE FROM saltos WHERE rowid = ?1",
                                    f"Cuota de {nombre_periodo(per)} de «{deuda['nombre']}»")
    if decision == "pasar":
        return f"la cuota de {nombre_periodo(per)} pasa al mes siguiente (todo el plan se retrasa un mes)", accion
    return f"la cuota de {nombre_periodo(per)} se pagará junto con la siguiente", accion


def periodos_sin_pagar_cerrados(deuda, d=None):
    """Periodos ya terminados (mes acabado o siguiente cobro registrado) sin pago ni decisión."""
    d = d or hoy()
    if deuda["tipo"] != "plazos":
        return []
    resultado = []
    for item in cuotas_pendientes(deuda, d):
        per = item["periodo"]
        if len(per) == 10:
            cerrado = datos.valor("SELECT 1 FROM ingresos WHERE tipo = 'salario' AND fecha > ? AND fecha <= ?",
                                  per, d.isoformat()) is not None
        else:
            cerrado = fin_de_mes(_mes(per)) < d
        if cerrado:
            resultado.append(item)
    return resultado


def aplazar(deuda_id, per, nueva_fecha=None, al_cobro=False):
    """Cambia el día de pago (a una fecha o, si debes, al próximo cobro). Devuelve un texto."""
    deuda = obtener(deuda_id)
    datos.ejecutar("UPDATE deudas SET aplazamientos = aplazamientos + 1 WHERE id = ?", deuda_id)
    if deuda["tipo"] in UNICOS:
        if al_cobro and not me_deben(deuda):
            # Se pagará con el siguiente salario que se registre a partir de mañana.
            datos.ejecutar("UPDATE deudas SET tipo = 'cobro', desde = ?, fecha = NULL WHERE id = ?",
                           (hoy() + timedelta(days=1)).isoformat(), deuda_id)
            return "aplazada al próximo cobro"
        datos.ejecutar("UPDATE deudas SET tipo = 'fecha', fecha = ?, desde = NULL WHERE id = ?",
                       nueva_fecha.isoformat(), deuda_id)
        return f"nuevo día de pago: {nueva_fecha:%d/%m}"
    if al_cobro:
        nueva_fecha = ciclo.proximo_cobro()
    datos.ejecutar("INSERT OR REPLACE INTO aplazos (deuda_id, periodo, nueva_fecha) VALUES (?, ?, ?)",
                   deuda_id, per, nueva_fecha.isoformat())
    return f"cuota aplazada al {nueva_fecha:%d/%m}"


def borrar(deuda_id):
    deuda = obtener(deuda_id)
    datos.ejecutar("UPDATE deudas SET activa = -1 WHERE id = ?", deuda_id)
    return datos.registrar_accion("deudas", deuda_id, "UPDATE deudas SET activa = 1 WHERE id = ?1",
                                  f"«{deuda['nombre']}» borrada")


def cambiar(deuda_id, campo, valor):
    if campo not in ("importe", "cuota", "dia", "fecha", "nombre", "si_no_paga"):
        raise ValueError(campo)
    datos.ejecutar(f"UPDATE deudas SET {campo} = ? WHERE id = ?", valor, deuda_id)
    deuda = obtener(deuda_id)
    if campo == "fecha" and deuda["tipo"] in ("sin_fecha", "cobro"):
        datos.ejecutar("UPDATE deudas SET tipo = 'fecha', desde = NULL WHERE id = ?", deuda_id)
    if campo == "importe" and deuda["tipo"] in ("fijo", "suscripcion"):
        datos.ejecutar("UPDATE deudas SET cuota = importe WHERE id = ?", deuda_id)
    if deuda["tipo"] == "plazos" and campo in ("importe", "cuota"):
        datos.ejecutar("UPDATE deudas SET cuotas_total = ? WHERE id = ?",
                       cuotas_hechas(deuda) + (restante(deuda)[1] or 0), deuda_id)
    if deuda["tipo"] == "plazos" and restante(deuda)[0] <= 0.004:
        datos.ejecutar("UPDATE deudas SET activa = 0 WHERE id = ?", deuda_id)
