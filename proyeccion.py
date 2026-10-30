"""📈 Proyección: cómo se reparte tu salario en cada cobro futuro y con cuánto dinero libre te quedas.

Para cada cobro hasta el mes que elijas (PROYECCION_HASTA, «AAAA-MM»; vacío = 12 cobros):
  salario + lo que te devuelven ese mes (cuotas de lo que te deben)
  − gastos fijos − suscripciones − cuotas de deudas − pagos únicos − aportaciones a metas (y colchón)
  = libre, que se suma al dinero libre acumulado.
No se resta gasto del día a día (el usuario lo pidió así). El punto de partida es tu dinero libre
de hoy (saldo − lo pendiente del ciclo − cuentas de metas − aportaciones pendientes) más lo que te
deben este ciclo. Salario: SALARIO_ESTIMADO si lo has escrito (> 0); si no, el último cobrado.

Es una simulación: no cambia nada salvo que apliques una propuesta (y se puede deshacer).
Nunca consulta al banco.
"""
import hashlib
import math
from datetime import date

import analisis
import ciclo
import reparto
import config
import datos
import deudas
import metas
from formato import MESES, MESES_CORTOS, euros, euros_cortos, sumar_meses

COBROS_POR_DEFECTO = 12
MAX_COBROS = 36
MINIMO = 5  # aportación fija mínima del simulador (una cantidad fija de 0 € no existe: para eso están los tramos)
_CACHE = None  # mientras se calculan propuestas, lo que no cambia entre simulaciones se calcula una vez
CLASES = {"fijos": "🏠 Gastos fijos", "subs": "📺 Suscripciones", "cuotas": "💳 Cuotas", "unicos": "🧾 Pagos únicos",
          "metas": "🎯 Metas", "deben": "🤝 Te devuelven"}


def hoy():
    return config.ahora().date()


def mes_corto(d):
    return f"{MESES_CORTOS[d.month - 1]} {str(d.year)[2:]}"


def mes_largo(d):
    return f"{MESES[d.month - 1]} {d.year}"


# ---------- Salario y horizonte ----------

def salario_estimado():
    return config.importe("SALARIO_ESTIMADO")


def salario_base():
    """(importe, de dónde sale) o (None, motivo)."""
    estimado = salario_estimado()
    if estimado:
        return estimado, "estimado por ti"
    ultimo = datos.uno("SELECT * FROM ingresos WHERE tipo = 'salario' ORDER BY fecha DESC, id DESC LIMIT 1")
    if ultimo:
        return ultimo["importe"], f"último cobro, {int(ultimo['fecha'][8:10])} {MESES_CORTOS[int(ultimo['fecha'][5:7]) - 1]}"
    return None, "aún no has registrado ningún salario"


def dia_habitual():
    desde, hasta = config.dias_cobro()
    ultimo = ciclo.ultimo_salario()
    if ultimo:
        dia = int(ultimo["fecha"][8:10])
        if desde <= dia <= hasta:
            return dia
    return desde


def mes_final():
    """Primer día del mes elegido como final de la proyección, o None (= 12 cobros)."""
    texto = config.valor("PROYECCION_HASTA").strip()
    if len(texto) == 7:
        try:
            final = date(int(texto[:4]), int(texto[5:7]), 1)
        except ValueError:
            return None
        if final >= date(hoy().year, hoy().month, 1):
            return final
    return None


def fechas_cobro(cobros=None):
    """[F1, …, FN, F(N+1)]: los próximos cobros hasta el mes elegido (y el siguiente, que cierra el último)."""
    dia = dia_habitual()
    fechas = [ciclo.proximo_cobro()]
    if cobros:
        while len(fechas) <= cobros:
            fechas.append(sumar_meses(fechas[-1], 1, dia))
        return fechas
    final = mes_final()
    while True:
        siguiente = sumar_meses(fechas[-1], 1, dia)
        if final is None and len(fechas) >= COBROS_POR_DEFECTO:
            fechas.append(siguiente)
            break
        if final is not None and (date(siguiente.year, siguiente.month, 1) > final or len(fechas) >= MAX_COBROS):
            fechas.append(siguiente)
            break
        fechas.append(siguiente)
    return fechas


def indice(fechas, d):
    """Ciclo al que pertenece la fecha d: 0 = antes del próximo cobro, k = [F_k, F_k+1), None = fuera."""
    if d < fechas[0]:
        return 0
    for k in range(len(fechas) - 1):
        if fechas[k] <= d < fechas[k + 1]:
            return k + 1
    return None


# ---------- Deudas y lo que te deben, por ciclo ----------

def clase(deuda):
    if deudas.me_deben(deuda):
        return "deben"
    return {"fijo": "fijos", "suscripcion": "subs", "plazos": "cuotas"}.get(deuda["tipo"], "unicos")


def calendario_deudas(fechas):
    """({k: [(deuda, importe, clase)]} para k = 1..N, deudas sin fecha, {deuda_id: k en que se termina})."""
    n = len(fechas) - 1
    por_ciclo = {k: [] for k in range(1, n + 1)}
    sin_fecha = []
    fines = {}
    for deuda in deudas.activas():
        c = clase(deuda)
        if deuda["tipo"] == "sin_fecha":
            sin_fecha.append(deuda)
            continue
        if deuda["tipo"] == "fecha":
            k = indice(fechas, date.fromisoformat(deuda["fecha"]))
            if k:
                por_ciclo[k].append((deuda, deuda["importe"], c))
            continue
        if deuda["tipo"] == "cobro":
            if not deudas.salario_desde(deuda["desde"]):  # aún no se ha cobrado: va en el próximo cobro
                por_ciclo[1].append((deuda, deuda["importe"], c))
            continue
        if deuda["tipo"] not in deudas.MENSUALES:
            continue
        if deudas.modo(deuda) == "cobro":
            pendientes = deudas.cuotas_pendientes(deuda, fechas[0])
            queda = (deudas.restante(deuda)[0] - sum(i["importe"] for i in pendientes)
                     if deuda["tipo"] == "plazos" else math.inf)
            for k in range(1, n + 1):
                importe = round(min(deudas.cuota(deuda), queda), 2)
                if importe <= 0.004:
                    break
                queda -= importe
                por_ciclo[k].append((deuda, importe, c))
                if queda <= 0.004:
                    fines[deuda["id"]] = k
        else:
            lista = deudas.cuotas_pendientes(deuda, fechas[-1])
            for item in lista:
                k = indice(fechas, item["vence"])
                if k:
                    por_ciclo[k].append((deuda, item["importe"], c))
            if deuda["tipo"] == "plazos" and lista and \
                    sum(i["importe"] for i in lista) >= deudas.restante(deuda)[0] - 0.01:
                k = indice(fechas, lista[-1]["vence"])
                if k:
                    fines[deuda["id"]] = k
    return por_ciclo, sin_fecha, fines


# ---------- Metas, por ciclo ----------

def _sin_pausa(cfg):
    return {k: v for k, v in (cfg or {}).items() if k != "pausa"}


def pendiente_hoy(meta, cfg):
    """Lo que falta apartar en el ciclo actual con los cambios simulados (0 si ya lo confirmaste)."""
    if metas.estado_ciclo(meta) or 0 in cfg.get("pausa", ()):
        return 0.0
    if not _sin_pausa(cfg):
        return metas.pendiente_ciclo(meta)
    return metas.cuota(meta, metas.ahorrado(meta), ciclo.inicio(), metas.pendientes_ahora(), _sin_pausa(cfg))


def estado_inicial_metas(cambios=None):
    """{meta_id: lo ahorrado contando que este ciclo apartas lo que toca}."""
    cambios = cambios or {}
    return {m["id"]: metas.ahorrado(m) + pendiente_hoy(m, cambios.get(m["id"], {})) for m in metas.activas()}


def _cobro_metas(lista, ahorrado, pendientes, fecha, k, cambios):
    """Aportaciones de un cobro: [(meta, importe, ¿en tramo?)]. Actualiza lo ahorrado; las metas conseguidas
    salen de «pendientes» al final del cobro (así el cambio de tramo se nota en el cobro siguiente)."""
    aportes, conseguidas = [], []
    for m in lista:
        cfg = cambios.get(m["id"], {})
        en_tramo = metas.tramo_activo(m, fecha, pendientes, _sin_pausa(cfg))
        importe = 0.0 if k in cfg.get("pausa", ()) else metas.cuota(m, ahorrado[m["id"]], fecha, pendientes,
                                                                     _sin_pausa(cfg))
        antes = ahorrado[m["id"]]
        ahorrado[m["id"]] = round(antes + importe, 2)
        aportes.append((m, importe, en_tramo))
        if antes < m["objetivo"] - 0.004 <= ahorrado[m["id"]]:
            conseguidas.append(m)
    for m in conseguidas:
        pendientes.discard(m["id"])
    return aportes, conseguidas


def fin_metas(cambios=None, cobros=120):
    """{meta_id: fecha del cobro con el que llegarías al objetivo (None si no llegas en 10 años)}."""
    cambios = cambios or {}
    if reparto.activo():  # con el reparto automático depende del dinero de cada cobro: se simula todo
        r = _cacheado(("fin_reparto", repr(sorted((k, sorted(v.items())) for k, v in cambios.items()))),
                      lambda: simular(cambios, cobros=cobros))
        if r:
            ya = {m["id"] for m in metas.activas() if estado_inicial_metas(cambios)[m["id"]] >= m["objetivo"] - 0.004}
            fin = {e[4]: e[0] for e in r["eventos"] if e[2] == "meta"}
            return {m["id"]: hoy() if m["id"] in ya else fin.get(m["id"]) for m in metas.activas()}
    dia = dia_habitual()
    ahorrado = estado_inicial_metas(cambios)
    lista = metas.activas()
    pendientes = {m["id"] for m in lista if ahorrado[m["id"]] < m["objetivo"] - 0.004}
    fin = {m["id"]: hoy() for m in lista if m["id"] not in pendientes}
    fecha = ciclo.proximo_cobro()
    for k in range(1, cobros + 1):
        if not pendientes:
            break
        _, conseguidas = _cobro_metas([m for m in lista if m["id"] not in fin], ahorrado, pendientes, fecha, k, cambios)
        for m in conseguidas:
            fin[m["id"]] = fecha
        fecha = sumar_meses(fecha, 1, dia)
    return {m["id"]: fin.get(m["id"]) for m in lista}


def libre_minimo():
    return config.importe("LIBRE_MINIMO")


# ---------- Simulación ----------

def _cobro_reparto(lista, ahorrado, pendientes, fecha, disponible, cambios):
    """Reparto automático de un cobro: [(meta, importe, False)] y las metas conseguidas con él."""
    estado = [(m, ahorrado[m["id"]]) for m in lista if m["id"] in pendientes]
    asignado, _ = reparto.repartir(disponible, estado, fecha, cambios)
    aportes, conseguidas = [], []
    for m in lista:
        importe = asignado.get(m["id"], 0.0)
        antes = ahorrado[m["id"]]
        ahorrado[m["id"]] = round(antes + importe, 2)
        aportes.append((m, importe, False))
        if antes < m["objetivo"] - 0.004 <= ahorrado[m["id"]]:
            conseguidas.append(m)
    for m in conseguidas:
        pendientes.discard(m["id"])
    return aportes, conseguidas


def simular(cambios=None, salario=None, extra_salario=0.0, contar_deben=True, sin_metas=False, cobros=None,
            repartir=None):
    """Proyección cobro a cobro. cambios: {meta_id: {campo de la meta: valor, …, pausa: {k}}}.
    Con el reparto automático (repartir, por defecto REPARTO_AUTO) tu libre es fijo y lo que sobra va a las metas."""
    cambios = cambios or {}
    repartir = reparto.activo() if repartir is None else repartir
    base, origen = salario_base()
    if salario is None:
        salario = base
    if salario is None:
        return None
    salario = round(salario + extra_salario, 2)
    minimo = libre_minimo()
    fechas = fechas_cobro(cobros)
    n = len(fechas) - 1
    por_ciclo, sin_fecha, fines = _cacheado(("deudas", tuple(fechas)), lambda: calendario_deudas(fechas))
    lista_metas = [] if sin_metas else metas.activas()
    ahorrado = estado_inicial_metas(cambios)
    pendientes = {m["id"] for m in metas.activas() if ahorrado[m["id"]] < m["objetivo"] - 0.004}

    def base_hoy():
        s = analisis.saldo_actual()
        return analisis.libre_sin_metas(deudas.neto(s["total"])[0]) if s else 0.0, \
            round(sum(i["importe"] for i in deudas.por_cobrar()), 2)
    libre_hoy, deben = _cacheado("hoy", base_hoy)
    sin_metas_hoy = round(libre_hoy + (deben if contar_deben else 0.0), 2)  # para el «hueco»: lo que falta de verdad
    # Lo que falta apartar este ciclo para las metas sale solo de lo que supere tu libre (v13: las metas ceden
    # primero; nunca dejan tu libre por debajo de LIBRE_MINIMO ni hacen un agujero). Con cambios se recalcula.
    pendiente = sum(pendiente_hoy(m, cambios.get(m["id"], {})) for m in lista_metas)
    libre_hoy -= min(pendiente, max(0.0, libre_hoy - minimo))
    libre_hoy = round(libre_hoy, 2)
    deben_hoy = deben if contar_deben else 0.0
    puente = round(libre_hoy + deben_hoy, 2)

    ciclos, eventos, acumulado = [], [], puente
    en_tramo_antes = {}
    for k in range(1, n + 1):
        fecha = fechas[k - 1]
        items = [x for x in por_ciclo[k] if contar_deben or x[2] != "deben"]
        totales = {c: 0.0 for c in CLASES}
        for _, importe, c in items:
            totales[c] += importe
        hueco = 0.0
        if repartir and lista_metas:
            pagos_previos = totales["fijos"] + totales["subs"] + totales["cuotas"] + totales["unicos"]
            hueco = max(0.0, -acumulado)  # si llegabas en negativo, este cobro lo tapa antes de repartir
            disponible = salario + totales["deben"] - pagos_previos - minimo - hueco
            habia = bool(pendientes)
            todos, conseguidas = _cobro_reparto(lista_metas, ahorrado, pendientes, fecha, disponible, cambios)
            if habia and not pendientes:
                eventos.append((fecha, k, "todas", "consigues todas tus metas: desde el próximo cobro lo que sobra queda "
                                                   "libre (¿creamos otra?)", 0))
        else:
            todos, conseguidas = _cobro_metas(lista_metas, ahorrado, pendientes, fecha, k, cambios)
        aportes = []
        for m, importe, en_tramo in todos:
            cfg = cambios.get(m["id"], {})
            limite = date.fromisoformat(cfg.get("fecha_limite", m["fecha_limite"]))
            if importe:
                aportes.append((m, importe, limite < fecha and not m["especial"]))
            if en_tramo_antes.get(m["id"]) and not en_tramo and importe:
                eventos.append((fecha, k, "tramo", f"«{m['nombre']}» vuelve a aportar {euros_cortos(importe)} por cobro",
                                m["id"]))
            en_tramo_antes[m["id"]] = en_tramo
        for m in conseguidas:
            eventos.append((fecha, k, "meta", f"consigues «{m['nombre']}»", m["id"]))
        totales["metas"] = round(sum(x for _, x, _ in aportes), 2)
        pagos = round(totales["fijos"] + totales["subs"] + totales["cuotas"] + totales["unicos"], 2)
        libre = round(salario + totales["deben"] - pagos - totales["metas"], 2)
        acumulado = round(acumulado + libre, 2)
        if libre < 0 or acumulado < 0:
            estado = "🔴"
        elif libre < minimo - 0.004:
            estado = "🟡"
        else:
            estado = "🟢"
        ciclos.append({"k": k, "fecha": fecha, "fin": fechas[k], "salario": salario, "items": items, "hueco": hueco,
                       "aportes": aportes, "por_meta": {m["id"]: (importe, en_tramo) for m, importe, en_tramo in todos},
                       "totales": {c: round(v, 2) for c, v in totales.items()}, "pagos": pagos,
                       "libre": libre, "acumulado": acumulado, "estado": estado,
                       "en_metas": round(sum(ahorrado[m["id"]] for m in lista_metas), 2),
                       "por_dia": round(libre / max(1, (fechas[k] - fecha).days), 2)})
        # Fin de deudas a plazos (y de lo que te devuelven) en este cobro
        for deuda_id, k_fin in fines.items():
            if k_fin == k:
                deuda = deudas.obtener(deuda_id)
                if deudas.me_deben(deuda):
                    eventos.append((fecha, k, "deben", f"{deuda['nombre']} termina de pagarte", deuda_id))
                else:
                    eventos.append((fecha, k, "deuda", f"terminas «{deuda['nombre']}» → +{euros_cortos(deuda['cuota'])}"
                                                       "/mes libres después", deuda_id))
        for deuda, importe, c in items:
            if c == "unicos":
                eventos.append((fecha, k, "unico", f"pago único «{deuda['nombre']}» {euros_cortos(importe)}", deuda["id"]))
    peor = min(ciclos, key=lambda x: x["libre"])
    sostenible = all(x["estado"] != "🔴" for x in ciclos)
    maximo_metas = min(round(x["salario"] + x["totales"]["deben"] - x["pagos"] - minimo, 2) for x in ciclos)
    orden = {"meta": 0, "todas": 1, "tramo": 2, "deuda": 3, "deben": 4, "unico": 5}
    return {"salario": salario, "origen": origen if not extra_salario else f"{origen}, {euros_cortos(extra_salario)}",
            "fechas": fechas, "ciclos": ciclos, "puente": puente, "libre_hoy": libre_hoy, "deben_hoy": deben_hoy,
            "eventos": sorted(eventos, key=lambda x: (x[0], orden[x[2]])), "sin_fecha": sin_fecha, "peor": peor,
            "sostenible": sostenible, "cumple": sostenible and all(x["estado"] == "🟢" for x in ciclos),
            "minimo": minimo, "maximo_metas": maximo_metas, "final": ciclos[-1]["acumulado"],
            "hueco": round(max(0.0, -sin_metas_hoy), 2), "reparto": bool(repartir and lista_metas),
            "rojos": [x for x in ciclos if x["estado"] == "🔴"], "metas": lista_metas, "cambios": cambios,
            "contar_deben": contar_deben}


def _cacheado(clave, calcular):
    if _CACHE is None:
        return calcular()
    if clave not in _CACHE:
        _CACHE[clave] = calcular()
    return _CACHE[clave]


def veredicto(p):
    if p.get("hueco"):
        icono, resto = veredicto({**p, "hueco": 0})
        return "🔴", (f"Hasta el cobro del {p['ciclos'][0]['fecha'].day} {MESES_CORTOS[p['ciclos'][0]['fecha'].month - 1]} "
                      f"te faltan {euros(p['hueco'])}. Después: {icono} {resto[0].lower() + resto[1:]}")
    if not p["sostenible"]:
        primero = p["rojos"][0]
        return "🔴", (f"No es sostenible: en el cobro de {mes_largo(primero['fecha'])} "
                      + (f"te faltan {euros(-primero['libre'])}" if primero["libre"] < 0
                         else f"tu dinero libre baja a {euros(primero['acumulado'])}"))
    if not p["cumple"]:
        justo = next(x for x in p["ciclos"] if x["estado"] == "🟡")
        return "🟡", (f"Llega, pero en el cobro de {mes_largo(justo['fecha'])} te quedan {euros(justo['libre'])} libres, "
                      f"menos de los {euros(p['minimo'])} que quieres")
    if p["minimo"]:
        return "🟢", f"Sostenible: en cada cobro te quedan al menos {euros(p['peor']['libre'])} libres (quieres {euros(p['minimo'])})"
    return "🟢", f"Sostenible: en cada cobro te quedan al menos {euros(p['peor']['libre'])} libres"


# ---------- Propuestas para que sea sostenible (o para acelerar) ----------
# Cada propuesta tiene una o varias variantes; se recomienda una. «Cumple» = ningún cobro en rojo y en todos
# te queda al menos el libre mínimo (LIBRE_MINIMO). Los recortes son TEMPORALES (tramos): al terminar,
# la meta recupera (sube para llegar a su fecha) o se aplaza (vuelve a su cuota normal y se mueve su fecha).

CAMPOS = ("aporte_modo", "aporte_fijo", "fecha_limite", "prioridad", "tramo_aporte", "tramo_hasta", "tramo_despues")
SIN_TRAMO = {"prioridad": 0, "tramo_aporte": -1, "tramo_hasta": "", "tramo_despues": ""}


def aportes_primer_cobro(p):
    """{meta_id: aportación en el primer cobro proyectado}."""
    base = {}
    for x in p["ciclos"]:
        for m, importe, _ in x["aportes"]:
            base.setdefault(m["id"], importe)
    return base


def _cumple(cambios):
    r = simular(cambios)
    return (r is not None and r["cumple"]), r


def _buscar(funcion, bajo, alto, pasos=16):
    """Mayor valor en [bajo, alto] para el que funcion(valor) es cierto (supone monotonía)."""
    if funcion(alto):
        return alto
    if not funcion(bajo):
        return None
    for _ in range(pasos):
        medio = (bajo + alto) / 2
        if funcion(medio):
            bajo = medio
        else:
            alto = medio
    return bajo


def _sin_conseguir():
    ahorrado = estado_inicial_metas()
    return [m for m in metas.activas() if ahorrado[m["id"]] < m["objetivo"] - 0.004]


def cuota_normal(meta):
    """Cuota de cada cobro sin tramos: la fija o la necesaria, y nunca menos de lo necesario para llegar a tiempo."""
    ahorrado = estado_inicial_metas()[meta["id"]]
    primero = ciclo.proximo_cobro()
    normal = metas.cuota(meta, ahorrado, primero, set(), {"tramo_aporte": -1})
    falta = max(0.0, meta["objetivo"] - ahorrado)
    necesaria = falta / metas.meses_hasta(date.fromisoformat(meta["fecha_limite"]), primero)
    return round(max(normal, min(necesaria, falta)), 2)


def _con_fechas_aplazadas(cambios, ids):
    """En «aplazar», la fecha de cada meta recortada pasa a ser el cobro en que de verdad llega."""
    fines = fin_metas(cambios)
    for meta_id in ids:
        meta = metas.obtener(meta_id)
        fin = fines.get(meta_id)
        if fin and fin.isoformat() > meta["fecha_limite"]:
            cambios[meta_id]["fecha_limite"] = sumar_meses(fin, 0, 28).isoformat()
    return cambios


def _variante(codigo, nombre, cambios, ids):
    ok, r = _cumple(cambios)
    motivo = "" if ok else (veredicto(r)[1] if r else "")
    corto = {"r": "recuperar", "a": "aplazar", "m": "menos", "n": "nada"}.get(codigo, "propuesta")
    return {"codigo": codigo, "nombre": nombre, "corto": corto, "cambios": cambios, "resultado": r, "posible": ok,
            "motivo": motivo, "reducidas": ids}


def priorizar(prioritarias):
    """Propuesta «🥇 Priorizar»: las prioritarias (en orden) aportan normal; las demás, lo justo para cumplir
    mientras la anterior no esté conseguida. Variantes «recuperar» y «aplazar»."""
    activas = _sin_conseguir()
    ids = [i for i in prioritarias if any(m["id"] == i for m in activas)]
    if not ids:
        return None
    por_id = {m["id"]: m for m in activas}
    resto = sorted((m for m in activas if m["id"] not in ids), key=lambda m: m["fecha_limite"])
    ranking = [por_id[i] for i in ids] + resto
    if len(ranking) < 2:
        return None
    normales = {m["id"]: cuota_normal(m) for m in ranking}
    variantes = []
    for despues in ("recuperar", "aplazar"):
        cambios = {m["id"]: {**SIN_TRAMO, "prioridad": (ids.index(m["id"]) + 1) if m["id"] in ids else 0}
                   for m in ranking}
        for m in resto:  # las no prioritarias parten de su cuota normal (nunca de un recorte antiguo)
            if despues == "aplazar":
                cambios[m["id"]].update(aporte_modo="fija", aporte_fijo=round(normales[m["id"]]))
            elif m["aporte_modo"] == "fija" and m["aporte_fijo"] < normales[m["id"]] - 0.5:
                cambios[m["id"]]["aporte_modo"] = "necesaria"
        reducidas = []

        def reducida(m, x, despues=despues):
            espera = ids[ids.index(m["id"]) - 1] if m["id"] in ids else ids[-1]
            cfg = {"tramo_aporte": math.floor(normales[m["id"]] * x), "tramo_hasta": f"meta:{espera}",
                   "tramo_despues": despues}
            if despues == "aplazar":
                cfg.update(aporte_modo="fija", aporte_fijo=round(normales[m["id"]]))
            return cfg
        if not _cumple(cambios)[0]:
            for m in reversed(ranking[1:]):
                previos = {k: dict(v) for k, v in cambios.items()}

                def con(x, m=m, previos=previos):
                    nuevo = {k: dict(v) for k, v in previos.items()}
                    nuevo[m["id"]].update(reducida(m, x))
                    return nuevo
                reducidas.append(m["id"])
                x = _buscar(lambda v: _cumple(con(v))[0], 0.0, 1.0)
                cambios = con(x if x is not None else 0.0)
                if x is not None:
                    break
        if despues == "aplazar" and reducidas and not _cumple(cambios)[0]:
            # Ni esperando cabe su cuota normal después: se baja a lo que puedas pagar (y llega más tarde).
            for meta_id in reducidas:
                previos = {k: dict(v) for k, v in cambios.items()}

                def con_despues(y, meta_id=meta_id, previos=previos):
                    nuevo = {k: dict(v) for k, v in previos.items()}
                    nuevo[meta_id]["aporte_fijo"] = max(MINIMO, math.floor(normales[meta_id] * y))
                    return nuevo
                y = _buscar(lambda v: _cumple(con_despues(v))[0], 0.0, 1.0)
                cambios = con_despues(y if y is not None else 0.0)
                if y is not None:
                    break
        if despues == "aplazar":
            cambios = _con_fechas_aplazadas(cambios, reducidas)
        nombre = "🔁 Recuperar" if despues == "recuperar" else "📅 Aplazar"
        variantes.append(_variante(despues[0], nombre, cambios, reducidas))
    posibles = [v for v in variantes if v["posible"]]
    nombres = " y ".join(f"«{por_id[i]['nombre']}»" for i in ids)
    return {"clave": "Q" + "-".join(map(str, ids)), "titulo": f"🥇 Priorizar {nombres}",
            "explicacion": ("Las prioritarias aportan lo normal. Las demás aportan menos (o nada) hasta conseguirlas; "
                            "después recuperan para llegar a su fecha o se aplazan."),
            "variantes": variantes, "recomendada": posibles[0]["codigo"] if posibles else None,
            "prioritarias": ids}


def recortar(p):
    """Propuesta «✂️ Recortar»: todas las metas aportan menos (o nada) hasta el primer cobro en que vuelve a
    caber su cuota normal; después se aplazan (cuota normal y fecha nueva)."""
    activas = _sin_conseguir()
    if not activas:
        return None
    normales = {m["id"]: cuota_normal(m) for m in activas}
    ids = [m["id"] for m in activas]

    def con(x, hasta):
        return {m["id"]: {"prioridad": 0, "tramo_aporte": math.floor(normales[m["id"]] * x),
                          "tramo_hasta": f"fecha:{hasta.isoformat()}", "tramo_despues": "aplazar",
                          "aporte_modo": "fija", "aporte_fijo": round(normales[m["id"]])} for m in activas}
    hasta = next((f for f in p["fechas"][1:] if _cumple(con(0.0, f))[0]), None)
    if not hasta:
        return None
    variantes = []
    x = _buscar(lambda v: _cumple(con(v, hasta))[0], 0.0, 1.0)
    if x and sum(math.floor(normales[i] * x) for i in ids) >= 5:
        variantes.append(_variante("m", f"✂️ Aportar menos (el {x * 100:.0f} %)",
                                   _con_fechas_aplazadas(con(x, hasta), ids), ids))
    variantes.append(_variante("n", "⏸️ No aportar nada", _con_fechas_aplazadas(con(0.0, hasta), ids), ids))
    posibles = [v for v in variantes if v["posible"]]
    return {"clave": "R", "titulo": f"✂️ Recortar todas hasta {mes_largo(hasta)}",
            "explicacion": (f"Hasta el cobro de {mes_largo(hasta)} tus metas aportan menos o nada; después vuelven a su "
                            "cuota normal y se aplazan sus fechas."),
            "variantes": variantes, "recomendada": posibles[0]["codigo"] if posibles else None, "hasta": hasta}


def alargar(p):
    """Propuesta «📅 Alargar»: las metas con aportación «la necesaria» alargan su fecha lo justo."""
    necesarias = [m for m in _sin_conseguir() if m["aporte_modo"] != "fija" and not m["especial"]
                  and m["tramo_aporte"] < 0]
    if not necesarias:
        return None

    def con(n):
        return {m["id"]: {"fecha_limite": sumar_meses(date.fromisoformat(m["fecha_limite"]), n, 28).isoformat()}
                for m in necesarias}
    meses = next((n for n in (1, 2, 3, 4, 6, 9, 12, 18, 24, 36) if _cumple(con(n))[0]), None)
    if not meses:
        return None
    variante = _variante("u", f"📅 Alargar {meses} mes{'es' if meses > 1 else ''}", con(meses), [m["id"] for m in necesarias])
    return {"clave": "B", "titulo": variante["nombre"] + " las fechas",
            "explicacion": "Las metas con aportación «la necesaria» piden menos cada cobro porque tienen más tiempo.",
            "variantes": [variante], "recomendada": "u"}


def acelerar(p):
    """Propuesta «🚀 Acelerar»: lo que sobra por encima de tu libre mínimo en el cobro más justo va a tus metas."""
    if not p["cumple"]:
        return None
    sobra = math.floor(p["peor"]["libre"] - p["minimo"])
    normales = [m for m in _sin_conseguir() if not m["especial"] and m["tramo_aporte"] < 0]
    faltas = {m["id"]: max(0.0, m["objetivo"] - estado_inicial_metas()[m["id"]]) for m in normales}
    total = sum(faltas.values())
    if sobra < 10 or total <= 0:
        return None
    base = {m["id"]: cuota_normal(m) for m in normales}

    def con(extra):
        return {m["id"]: {"aporte_modo": "fija", "aporte_fijo": round(base[m["id"]] + extra * faltas[m["id"]] / total)}
                for m in normales}
    extra = _buscar(lambda v: _cumple(con(v))[0], 0.0, float(sobra))
    if not extra or extra < 10:
        return None
    extra = math.floor(extra)
    variante = _variante("u", f"🚀 Acelerar (+{euros_cortos(extra)}/cobro)", con(extra), [m["id"] for m in normales])
    return {"clave": "D", "titulo": variante["nombre"],
            "explicacion": (f"Lo que te sobra por encima de tu libre mínimo ({euros_cortos(p['minimo'])}) va a tus metas, "
                            "repartido según lo que le falta a cada una: llegan antes."),
            "variantes": [variante], "recomendada": "u"}


def _tarde():
    """Metas (no especiales) que con la configuración actual llegan después de su fecha (o nunca)."""
    fines = fin_metas()
    return [m for m in _sin_conseguir() if not m["especial"]
            and (fines.get(m["id"]) is None or fines[m["id"]].isoformat() > m["fecha_limite"])], fines


def priorizar_reparto(prioritarias):
    """Con el reparto automático, priorizar es solo el orden: la 1.ª recibe primero."""
    activas = _sin_conseguir()
    por_id = {m["id"]: m for m in activas}
    ids = [i for i in prioritarias if i in por_id]
    if not ids:
        return None
    cambios = {m["id"]: {"prioridad": (ids.index(m["id"]) + 1) if m["id"] in ids else 0} for m in activas}
    variante = _variante("u", "🥇 Aplicar este orden", cambios, [])
    variante["posible"] = True  # cambiar el orden siempre se puede (el dinero total es el mismo)
    nombres = " y ".join(f"«{por_id[i]['nombre']}»" for i in ids)
    explicacion = ("Recibe primero lo necesario para llegar a su fecha y, después, todo lo que sobre hasta completarse."
                   if reparto.modo() == "necesario" else
                   "Recibe todo lo que sobra hasta completarse; después pasa a la siguiente.")
    return {"clave": "Q" + "-".join(map(str, ids)), "titulo": f"🥇 Priorizar {nombres}", "explicacion": explicacion,
            "variantes": [variante], "recomendada": "u", "prioritarias": ids}


def fechas_reparto(p):
    """Con el reparto automático: poner a cada meta que llega tarde la fecha en que de verdad llega."""
    tarde, fines = _tarde()
    tarde = [m for m in tarde if fines.get(m["id"])]
    if not tarde:
        return None
    cambios = {m["id"]: {"fecha_limite": sumar_meses(fines[m["id"]], 0, 28).isoformat()} for m in tarde}
    variante = _variante("u", "📅 Mover las fechas", cambios, [m["id"] for m in tarde])
    variante["posible"] = True
    return {"clave": "F", "titulo": "📅 Poner a cada meta la fecha en que llega",
            "explicacion": "Con lo que sobra de cada cobro no llegan a tiempo: así sus fechas cuadran con la realidad.",
            "variantes": [variante], "recomendada": "u"}


def prioritarias_actuales():
    """Ids de las metas marcadas como prioritarias (en orden) o, si no hay, la de fecha más cercana."""
    activas = _sin_conseguir()
    marcadas = sorted((m for m in activas if m["prioridad"] > 0), key=lambda m: m["prioridad"])
    if marcadas:
        return [m["id"] for m in marcadas]
    normales = sorted((m for m in activas if not m["especial"]), key=lambda m: m["fecha_limite"])
    return [normales[0]["id"]] if normales else []


def _con_cache(funcion, *args):
    global _CACHE
    if _CACHE is not None:
        return funcion(*args)
    _CACHE = {}
    try:
        return funcion(*args)
    finally:
        _CACHE = None


def propuestas(p):
    """Propuestas para la configuración actual (si no cumple: priorizar, recortar, alargar; si sobra: acelerar)."""
    def calcular():
        if reparto.activo():
            tarde = _tarde()[0]
            if not tarde:
                return []
            # Se propone poner primero la meta que llega tarde (detrás, las prioritarias que ya tuvieras)
            orden = [tarde[0]["id"]] + [i for i in prioritarias_actuales() if i != tarde[0]["id"]]
            return [x for x in (priorizar_reparto(orden), fechas_reparto(p)) if x]
        if p["cumple"]:
            return [x for x in (acelerar(p),) if x]
        return [x for x in (priorizar(prioritarias_actuales()), recortar(p), alargar(p)) if x]
    return _con_cache(calcular)


def propuesta(p, clave):
    """Una propuesta por su clave («Q3-1», «R», «B», «D»)."""
    def calcular():
        if clave.startswith("Q"):
            ids = [int(x) for x in clave[1:].split("-") if x.isdigit()]
            return priorizar_reparto(ids) if reparto.activo() else priorizar(ids)
        return {"R": recortar, "B": alargar, "D": acelerar, "F": fechas_reparto}.get(clave, lambda _: None)(p)
    return _con_cache(calcular)


def variante(x, codigo=None):
    codigo = codigo or x["recomendada"]
    return next((v for v in x["variantes"] if v["codigo"] == codigo), None)


def firma(p):
    """Identifica la configuración actual (para no volver a proponer lo que ignoraste)."""
    partes = [f"{p['salario']:.0f}", f"{p['minimo']:.0f}"]
    partes += [":".join(str(m[c]) for c in ("id",) + CAMPOS) for m in p["metas"]]
    partes += [str(d["id"]) for d in deudas.activas()]
    return hashlib.sha1("|".join(partes).encode()).hexdigest()[:10]


def ignorada(p):
    return datos.enviado(f"proy_ignorar:{firma(p)}")


def _literal(valor):
    if isinstance(valor, (int, float)):
        return repr(float(valor)) if isinstance(valor, float) else str(int(valor))
    return "'" + str(valor).replace("'", "''") + "'"


def aplicar(cambios, descripcion):
    """Guarda los cambios de una propuesta en las metas. Devuelve el id de acción para deshacer."""
    deshacer = []
    for meta_id, cfg in cambios.items():
        meta = metas.obtener(meta_id)
        valores = ", ".join(f"{c} = {_literal(meta[c])}" for c in CAMPOS)
        deshacer.append(f"UPDATE metas SET {valores} WHERE id = {int(meta_id)} AND ?1 IS NOT NULL")
        for campo in CAMPOS:
            if campo in cfg:
                metas.configurar(meta_id, campo, cfg[campo])
    return datos.registrar_accion("metas", 0, "; ".join(deshacer), descripcion)


def metas_tarde():
    """[(meta, fin estimado)] con aportación fija que, sin tramo, no llegan a su fecha (p. ej. tras un recorte antiguo)."""
    fines = fin_metas()
    lista = []
    for m in _sin_conseguir():
        if m["especial"] or m["tramo_aporte"] >= 0 or m["aporte_modo"] != "fija":
            continue
        fin = fines.get(m["id"])
        if fin is None or fin.isoformat() > m["fecha_limite"]:
            lista.append((m, fin))
    return lista


# ---------- Escenarios ----------

def escenarios(p):
    """[(nombre, proyección)] comparados con la actual."""
    lista = [("Ahora", p),
             ("Cobras 100 € menos", simular(extra_salario=-100)),
             ("Cobras 100 € más", simular(extra_salario=100)),
             ("Sin lo que te deben", simular(contar_deben=False)),
             ("Sin aportar a metas", simular(sin_metas=True))]
    return [(n, r) for n, r in lista if r]


def aviso_si_insostenible():
    """Texto corto si la configuración actual deja algún cobro en rojo (para avisar tras un cambio)."""
    p = simular()
    if not p or p["cumple"]:
        return None
    icono, texto = veredicto(p)
    return f"{icono} <b>Proyección</b>: {texto}. Elige qué meta priorizar o mira las propuestas."


def resumen_corto():
    """Una línea para el plan «¡Cobrado!»."""
    p = simular()
    if not p:
        return None
    icono, texto = veredicto(p)
    return f"{icono} Proyección hasta {mes_largo(p['ciclos'][-1]['fecha'])}: {texto[0].lower() + texto[1:]}."


def aviso_horizonte():
    final = mes_final()
    return mes_largo(final) if final else f"{COBROS_POR_DEFECTO} cobros"

