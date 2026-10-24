"""Deudas, cuotas y pagos fijos, y el saldo neto del ciclo.

Tipos:
- fecha    : pago único con fecha («Juan, 200 €, el 20/11»).
- cobro    : pago único en cuanto cobres («Mamá, 150 €, al cobrar»).
- plazos   : cuotas mensuales («Móvil, 50 €/mes, quedan 8 cuotas, día 10»).
- fijo     : pago mensual sin fin («Alquiler, 650 €, día 1»).
- me_deben : dinero que te deben (no se resta del saldo neto).

En el saldo neto solo se resta lo que toca pagar en el ciclo actual y aún no está marcado como
pagado; de las deudas a plazos, solo la cuota del ciclo (nunca el total). Marcar «pagado» es lo que
evita restarlo dos veces, porque cuando pagas el dinero ya ha salido del banco.
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
    "me_deben": "🤝 Me deben",
}
ACTIVA, TERMINADA, BORRADA = 1, 0, -1


def hoy():
    return config.ahora().date()


def obtener(deuda_id):
    return datos.uno("SELECT * FROM deudas WHERE id = ?", deuda_id)


def activas(incluir_me_deben=True):
    filas = datos.todos("SELECT * FROM deudas WHERE activa = 1 ORDER BY id")
    return filas if incluir_me_deben else [d for d in filas if d["tipo"] != "me_deben"]


def _mes(texto):
    anio, mes = (int(x) for x in texto.split("-"))
    return date(anio, mes, 1)


def pagos(deuda_id):
    return datos.todos("SELECT * FROM pagos WHERE deuda_id = ? ORDER BY fecha, id", deuda_id)


def periodos_pagados(deuda_id):
    return {p["periodo"] for p in pagos(deuda_id)}


def vencimiento(deuda, per):
    """Fecha en que vence la cuota del mes `per` ('AAAA-MM'), teniendo en cuenta los aplazamientos."""
    aplazo = datos.valor("SELECT nueva_fecha FROM aplazos WHERE deuda_id = ? AND periodo = ?", deuda["id"], per)
    if aplazo:
        return date.fromisoformat(aplazo)
    mes = _mes(per)
    return dia_del_mes(mes.year, mes.month, deuda["dia"])


def importe_cuota(deuda, numero):
    """Importe de la cuota número `numero` (desde 0). La última ajusta los céntimos."""
    if deuda["tipo"] == "plazos" and numero == deuda["cuotas_total"] - 1:
        return round(deuda["importe"] - deuda["cuota"] * (deuda["cuotas_total"] - 1), 2)
    return deuda["cuota"]


def periodos(deuda):
    """Todos los meses de la deuda mensual (para plazos, solo los de sus cuotas)."""
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


def pendientes(d=None):
    """Lo que toca pagar en el ciclo actual y no está pagado: [{deuda, periodo, importe, vence, atrasada}]."""
    d = d or hoy()
    proximo = ciclo.proximo_cobro(d)
    lista = []
    for deuda in activas(incluir_me_deben=False):
        if deuda["tipo"] == "fecha":
            vence = date.fromisoformat(deuda["fecha"])
            if vence < proximo:
                lista.append({"deuda": deuda, "periodo": "unico", "importe": deuda["importe"], "vence": vence})
        elif deuda["tipo"] == "cobro":
            salario = salario_desde(deuda["desde"], d)
            if salario:
                lista.append({"deuda": deuda, "periodo": "unico", "importe": deuda["importe"],
                              "vence": date.fromisoformat(salario["fecha"])})
        else:
            pagados = periodos_pagados(deuda["id"])
            for numero, per in enumerate(periodos(deuda)):
                vence = vencimiento(deuda, per)
                if vence >= proximo:
                    continue
                if per not in pagados:
                    lista.append({"deuda": deuda, "periodo": per, "importe": importe_cuota(deuda, numero),
                                  "vence": vence})
    for item in lista:
        item["atrasada"] = item["vence"] < d
    return sorted(lista, key=lambda x: x["vence"])


def comprometido_proximo_cobro(d=None):
    """Deudas «al cobrar» que se pagarán con el próximo salario (aún no se restan del neto)."""
    d = d or hoy()
    return [deuda for deuda in activas(incluir_me_deben=False)
            if deuda["tipo"] == "cobro" and not salario_desde(deuda["desde"], d)]


def neto(saldo_total, d=None):
    """(saldo neto, lista de pendientes del ciclo)."""
    lista = pendientes(d)
    return round(saldo_total - sum(x["importe"] for x in lista), 2), lista


def restante(deuda):
    """(dinero que falta por pagar, cuotas que faltan o None)."""
    if deuda["tipo"] == "plazos":
        pagadas = len(periodos_pagados(deuda["id"]))
        quedan = deuda["cuotas_total"] - pagadas
        total = sum(importe_cuota(deuda, n) for n in range(pagadas, deuda["cuotas_total"]))
        return round(total, 2), quedan
    if deuda["tipo"] == "fijo":
        return deuda["importe"], None
    return deuda["importe"], None


def fecha_fin(deuda):
    if deuda["tipo"] != "plazos":
        return None
    return vencimiento(deuda, periodos(deuda)[-1])


def proximo_pago(deuda, d=None):
    """(fecha, periodo, importe) del próximo pago sin hacer, o None."""
    d = d or hoy()
    if deuda["tipo"] == "fecha":
        return date.fromisoformat(deuda["fecha"]), "unico", deuda["importe"]
    if deuda["tipo"] == "cobro":
        salario = salario_desde(deuda["desde"], d)
        return (date.fromisoformat(salario["fecha"]) if salario else ciclo.proximo_cobro(d)), "unico", deuda["importe"]
    if deuda["tipo"] == "me_deben":
        return None
    pagados = periodos_pagados(deuda["id"])
    for numero, per in enumerate(periodos(deuda)):
        if per not in pagados:
            return vencimiento(deuda, per), per, importe_cuota(deuda, numero)
    return None


# ---------- Cambios ----------

def crear(nombre, tipo, importe, cuota=None, cuotas_total=None, dia=None, fecha=None, desde=None):
    deuda_id = datos.ejecutar(
        "INSERT INTO deudas (nombre, tipo, importe, cuota, cuotas_total, dia, fecha, desde, creada) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nombre, tipo, round(importe, 2), cuota, cuotas_total, dia, fecha, desde, config.ahora().isoformat())
    accion = datos.registrar_accion("deudas", deuda_id, "DELETE FROM deudas WHERE id = ?1",
                                    f"Deuda «{nombre}» creada")
    return deuda_id, accion


def pagar(deuda_id, per, importe=None):
    """Marca un pago. Devuelve (texto, id de acción para deshacer)."""
    deuda = obtener(deuda_id)
    fecha = hoy().isoformat()
    if deuda["tipo"] in ("fecha", "cobro", "me_deben"):
        parcial = importe is not None and importe < deuda["importe"] - 0.004
        pagado = importe if parcial else deuda["importe"]
        pago_id = datos.ejecutar("INSERT INTO pagos (deuda_id, periodo, importe, fecha) VALUES (?, ?, ?, ?)",
                                 deuda_id, "unico", pagado, fecha)
        if parcial:
            datos.ejecutar("UPDATE deudas SET importe = ROUND(importe - ?, 2) WHERE id = ?", pagado, deuda_id)
            deshacer = ("UPDATE deudas SET importe = ROUND(importe + (SELECT importe FROM pagos WHERE id = ?1), 2) "
                        "WHERE id = (SELECT deuda_id FROM pagos WHERE id = ?1); DELETE FROM pagos WHERE id = ?1")
            texto = f"parte pagada; quedan {round(deuda['importe'] - pagado, 2)}"
        else:
            datos.ejecutar("UPDATE deudas SET activa = 0 WHERE id = ?", deuda_id)
            deshacer = ("UPDATE deudas SET activa = 1 WHERE id = (SELECT deuda_id FROM pagos WHERE id = ?1); "
                        "DELETE FROM pagos WHERE id = ?1")
            texto = "cobrada" if deuda["tipo"] == "me_deben" else "pagada"
    else:
        numero = periodos(deuda).index(per) if per in periodos(deuda) else 0
        pago_id = datos.ejecutar("INSERT INTO pagos (deuda_id, periodo, importe, fecha) VALUES (?, ?, ?, ?)",
                                 deuda_id, per, importe_cuota(deuda, numero), fecha)
        deshacer = ("UPDATE deudas SET activa = 1 WHERE id = (SELECT deuda_id FROM pagos WHERE id = ?1); "
                    "DELETE FROM pagos WHERE id = ?1")
        texto = "cuota pagada"
        if deuda["tipo"] == "plazos" and len(periodos_pagados(deuda_id)) >= deuda["cuotas_total"]:
            datos.ejecutar("UPDATE deudas SET activa = 0 WHERE id = ?", deuda_id)
            texto = "última cuota pagada: ¡deuda terminada! 🎉"
    accion = datos.registrar_accion("pagos", pago_id, deshacer, f"Pago de «{deuda['nombre']}»")
    return texto, accion


def aplazar(deuda_id, per, nueva_fecha=None, al_cobro=False):
    """Aplaza un pago a otra fecha o al próximo cobro. Devuelve un texto con el resultado."""
    deuda = obtener(deuda_id)
    datos.ejecutar("UPDATE deudas SET aplazamientos = aplazamientos + 1 WHERE id = ?", deuda_id)
    if deuda["tipo"] in ("fecha", "cobro"):
        if al_cobro:
            # Se pagará con el siguiente salario que se registre a partir de mañana.
            datos.ejecutar("UPDATE deudas SET tipo = 'cobro', desde = ?, fecha = NULL WHERE id = ?",
                           (hoy() + timedelta(days=1)).isoformat(), deuda_id)
            return "aplazada al próximo cobro"
        datos.ejecutar("UPDATE deudas SET tipo = 'fecha', fecha = ?, desde = NULL WHERE id = ?",
                       nueva_fecha.isoformat(), deuda_id)
        return f"aplazada al {nueva_fecha:%d/%m}"
    if al_cobro:
        nueva_fecha = ciclo.proximo_cobro()
    datos.ejecutar("INSERT OR REPLACE INTO aplazos (deuda_id, periodo, nueva_fecha) VALUES (?, ?, ?)",
                   deuda_id, per, nueva_fecha.isoformat())
    return f"cuota aplazada al {nueva_fecha:%d/%m}"


def borrar(deuda_id):
    deuda = obtener(deuda_id)
    datos.ejecutar("UPDATE deudas SET activa = -1 WHERE id = ?", deuda_id)
    return datos.registrar_accion("deudas", deuda_id, "UPDATE deudas SET activa = 1 WHERE id = ?1",
                                  f"Deuda «{deuda['nombre']}» borrada")


def cambiar(deuda_id, campo, valor):
    if campo not in ("importe", "cuota", "dia", "fecha", "nombre"):
        raise ValueError(campo)
    datos.ejecutar(f"UPDATE deudas SET {campo} = ? WHERE id = ?", valor, deuda_id)
    deuda = obtener(deuda_id)
    if campo == "cuota" and deuda["tipo"] == "plazos":
        datos.ejecutar("UPDATE deudas SET importe = ROUND(cuota * cuotas_total, 2) WHERE id = ?", deuda_id)
    if campo == "importe" and deuda["tipo"] == "fijo":
        datos.ejecutar("UPDATE deudas SET cuota = importe WHERE id = ?", deuda_id)
