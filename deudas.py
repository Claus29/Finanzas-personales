"""Deudas (lo que debes y lo que te deben), cuotas, pagos fijos y suscripciones, y el saldo neto.

Sentido:
- debo     : dinero que tú pagas. Se resta del saldo neto lo que toca en el ciclo.
- me_deben : dinero que te tienen que pagar. NUNCA se suma al saldo neto (se muestra aparte).

Tipos:
- fecha       : pago único con día de pago («Juan, 200 €, el 20/11»). Ambos sentidos.
- cobro       : pago único en cuanto cobres («Mamá, 150 €, al cobrar»). Solo «debo».
- plazos      : cuotas mensuales con día de pago. Ambos sentidos.
- fijo        : pago mensual sin fin («Alquiler, 650 €, día 1»). Solo «debo».
- suscripcion : como fijo, para Netflix, Spotify... Solo «debo».
- sin_fecha   : aún sin día de pago (se le puede poner después). Solo «me_deben».

Del saldo neto solo se resta lo del ciclo actual aún no marcado como pagado; de las deudas a plazos,
solo la cuota del ciclo (nunca el total). Marcar «pagado» evita restarlo dos veces: cuando pagas, el
dinero ya ha salido del banco. Aplazar cambia el día de pago (y su recordatorio).
"""
from datetime import date, timedelta

import ciclo
import config
import datos
from formato import dia_del_mes, periodo, sumar_meses

TIPOS = {
    "fecha": "📅 Pago único",
    "cobro": "💶 Al cobrar",
    "plazos": "🔁 A plazos",
    "fijo": "🏠 Fijo mensual",
    "suscripcion": "📺 Suscripción",
    "sin_fecha": "🕐 Sin fecha",
}
TIPOS_POR_SENTIDO = {
    "debo": ["fecha", "cobro", "plazos", "fijo", "suscripcion"],
    "me_deben": ["fecha", "plazos", "sin_fecha"],
}
MENSUALES = ("plazos", "fijo", "suscripcion")
UNICOS = ("fecha", "cobro", "sin_fecha")
ACTIVA, TERMINADA, BORRADA = 1, 0, -1


def hoy():
    return config.ahora().date()


def obtener(deuda_id):
    return datos.uno("SELECT * FROM deudas WHERE id = ?", deuda_id)


def activas(sentido=None):
    filas = datos.todos("SELECT * FROM deudas WHERE activa = 1 ORDER BY id")
    return filas if sentido is None else [d for d in filas if d["sentido"] == sentido]


def me_deben(deuda):
    return deuda["sentido"] == "me_deben"


def _mes(texto):
    anio, mes = (int(x) for x in texto.split("-"))
    return date(anio, mes, 1)


def pagos(deuda_id):
    return datos.todos("SELECT * FROM pagos WHERE deuda_id = ? ORDER BY fecha, id", deuda_id)


def periodos_pagados(deuda_id):
    return {p["periodo"] for p in pagos(deuda_id)}


def vencimiento(deuda, per):
    """Día de pago de la cuota del mes `per` ('AAAA-MM'), teniendo en cuenta los aplazamientos."""
    aplazo = datos.valor("SELECT nueva_fecha FROM aplazos WHERE deuda_id = ? AND periodo = ?", deuda["id"], per)
    if aplazo:
        return date.fromisoformat(aplazo)
    mes = _mes(per)
    return dia_del_mes(mes.year, mes.month, deuda["dia"])


def aplazada(deuda, per):
    if per == "unico":
        return deuda["aplazamientos"] > 0
    return datos.valor("SELECT 1 FROM aplazos WHERE deuda_id = ? AND periodo = ?", deuda["id"], per) is not None


def importe_cuota(deuda, numero):
    """Importe de la cuota número `numero` (desde 0). La última de unos plazos ajusta los céntimos."""
    if deuda["tipo"] == "plazos" and numero == deuda["cuotas_total"] - 1:
        return round(deuda["importe"] - deuda["cuota"] * (deuda["cuotas_total"] - 1), 2)
    return deuda["cuota"]


def periodos(deuda):
    """Meses de una deuda mensual (para plazos, solo los de sus cuotas)."""
    inicio = _mes(deuda["desde"])
    if deuda["tipo"] == "plazos":
        return [periodo(sumar_meses(inicio, n, 1)) for n in range(deuda["cuotas_total"])]
    meses = []
    mes = inicio
    limite = sumar_meses(hoy(), 14, 1)
    while mes <= limite:
        meses.append(periodo(mes))
        mes = sumar_meses(mes, 1, 1)
    return meses


def salario_desde(fecha_iso, hasta=None):
    """Primer salario registrado en o después de `fecha_iso` (hasta hoy)."""
    return datos.uno("SELECT * FROM ingresos WHERE tipo = 'salario' AND fecha >= ? AND fecha <= ? ORDER BY fecha LIMIT 1",
                     fecha_iso, (hasta or hoy()).isoformat())


def pendientes(d=None, sentido="debo"):
    """Pagos del ciclo actual aún no marcados: [{deuda, periodo, importe, vence, atrasada}].

    Con sentido «debo» es lo que se resta del saldo neto; con «me_deben», lo que te tienen que pagar.
    """
    d = d or hoy()
    proximo = ciclo.proximo_cobro(d)
    lista = []
    for deuda in activas(sentido):
        if deuda["tipo"] == "fecha":
            vence = date.fromisoformat(deuda["fecha"])
            if vence < proximo:
                lista.append({"deuda": deuda, "periodo": "unico", "importe": deuda["importe"], "vence": vence})
        elif deuda["tipo"] == "cobro":
            salario = salario_desde(deuda["desde"], d)
            if salario:
                lista.append({"deuda": deuda, "periodo": "unico", "importe": deuda["importe"],
                              "vence": date.fromisoformat(salario["fecha"])})
        elif deuda["tipo"] in MENSUALES:
            pagados = periodos_pagados(deuda["id"])
            for numero, per in enumerate(periodos(deuda)):
                vence = vencimiento(deuda, per)
                if vence < proximo and per not in pagados:
                    lista.append({"deuda": deuda, "periodo": per, "importe": importe_cuota(deuda, numero),
                                  "vence": vence})
    for item in lista:
        item["atrasada"] = item["vence"] < d
    return sorted(lista, key=lambda x: x["vence"])


def por_cobrar(d=None):
    """Lo que te tienen que pagar en este ciclo (no se suma al saldo neto)."""
    return pendientes(d, "me_deben")


def comprometido_proximo_cobro(d=None):
    """Deudas «al cobrar» que se pagarán con el próximo salario (aún no se restan del neto)."""
    d = d or hoy()
    return [deuda for deuda in activas("debo") if deuda["tipo"] == "cobro" and not salario_desde(deuda["desde"], d)]


def neto(saldo_total, d=None):
    """(saldo neto, lista de pendientes del ciclo). Lo que te deben no cuenta."""
    lista = pendientes(d, "debo")
    return round(saldo_total - sum(x["importe"] for x in lista), 2), lista


def restante(deuda):
    """(dinero que falta, cuotas que faltan o None). Para fijos y suscripciones, el importe mensual."""
    if deuda["tipo"] == "plazos":
        pagadas = len(periodos_pagados(deuda["id"]))
        total = sum(importe_cuota(deuda, n) for n in range(pagadas, deuda["cuotas_total"]))
        return round(total, 2), deuda["cuotas_total"] - pagadas
    return deuda["importe"], None


def fecha_fin(deuda):
    if deuda["tipo"] != "plazos":
        return None
    return vencimiento(deuda, periodos(deuda)[-1])


def proximo_pago(deuda, d=None):
    """(fecha, periodo, importe) del próximo pago sin hacer, o None (sin fecha)."""
    d = d or hoy()
    if deuda["tipo"] == "fecha":
        return date.fromisoformat(deuda["fecha"]), "unico", deuda["importe"]
    if deuda["tipo"] == "cobro":
        salario = salario_desde(deuda["desde"], d)
        return (date.fromisoformat(salario["fecha"]) if salario else ciclo.proximo_cobro(d)), "unico", deuda["importe"]
    if deuda["tipo"] not in MENSUALES:
        return None
    pagados = periodos_pagados(deuda["id"])
    for numero, per in enumerate(periodos(deuda)):
        if per not in pagados:
            return vencimiento(deuda, per), per, importe_cuota(deuda, numero)
    return None


# ---------- Cambios ----------

def crear(nombre, tipo, importe, cuota=None, cuotas_total=None, dia=None, fecha=None, desde=None, sentido="debo"):
    deuda_id = datos.ejecutar(
        "INSERT INTO deudas (nombre, tipo, importe, cuota, cuotas_total, dia, fecha, desde, creada, sentido) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nombre, tipo, round(importe, 2), cuota, cuotas_total, dia, fecha, desde, config.ahora().isoformat(), sentido)
    accion = datos.registrar_accion("deudas", deuda_id, "DELETE FROM deudas WHERE id = ?1",
                                    f"«{nombre}» apuntada")
    return deuda_id, accion


def pagar(deuda_id, per, importe=None):
    """Marca un pago (o un cobro, si te deben). Devuelve (texto, id de acción para deshacer)."""
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
            texto = f"{'te ha pagado' if cobro else 'pagado'} una parte; quedan {quedan}"
        else:
            datos.ejecutar("UPDATE deudas SET activa = 0 WHERE id = ?", deuda_id)
            deshacer = ("UPDATE deudas SET activa = 1 WHERE id = (SELECT deuda_id FROM pagos WHERE id = ?1); "
                        "DELETE FROM pagos WHERE id = ?1")
            texto = "cobrada del todo 🎉" if cobro else "pagada"
    else:
        lista = periodos(deuda)
        numero = lista.index(per) if per in lista else 0
        pago_id = datos.ejecutar("INSERT INTO pagos (deuda_id, periodo, importe, fecha) VALUES (?, ?, ?, ?)",
                                 deuda_id, per, importe_cuota(deuda, numero), fecha)
        deshacer = ("UPDATE deudas SET activa = 1 WHERE id = (SELECT deuda_id FROM pagos WHERE id = ?1); "
                    "DELETE FROM pagos WHERE id = ?1")
        texto = "cuota cobrada" if cobro else ("pago del mes hecho" if deuda["tipo"] != "plazos" else "cuota pagada")
        if deuda["tipo"] == "plazos" and len(periodos_pagados(deuda_id)) >= deuda["cuotas_total"]:
            datos.ejecutar("UPDATE deudas SET activa = 0 WHERE id = ?", deuda_id)
            texto = "última cuota cobrada: ¡te lo ha devuelto todo! 🎉" if cobro else "última cuota pagada: ¡deuda terminada! 🎉"
    accion = datos.registrar_accion("pagos", pago_id, deshacer, f"{'Cobro' if cobro else 'Pago'} de «{deuda['nombre']}»")
    return texto, accion


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
    if campo not in ("importe", "cuota", "dia", "fecha", "nombre"):
        raise ValueError(campo)
    datos.ejecutar(f"UPDATE deudas SET {campo} = ? WHERE id = ?", valor, deuda_id)
    deuda = obtener(deuda_id)
    if campo == "fecha" and deuda["tipo"] in ("sin_fecha", "cobro"):
        datos.ejecutar("UPDATE deudas SET tipo = 'fecha', desde = NULL WHERE id = ?", deuda_id)
    if campo == "cuota" and deuda["tipo"] == "plazos":
        datos.ejecutar("UPDATE deudas SET importe = ROUND(cuota * cuotas_total, 2) WHERE id = ?", deuda_id)
    if campo == "importe" and deuda["tipo"] in ("fijo", "suscripcion"):
        datos.ejecutar("UPDATE deudas SET cuota = importe WHERE id = ?", deuda_id)
