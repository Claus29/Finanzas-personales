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
import config
import datos
import deudas
import metas
from formato import MESES, MESES_CORTOS, euros, euros_cortos, sumar_meses

COBROS_POR_DEFECTO = 12
MAX_COBROS = 36
MINIMO = 5  # aportación mínima que proponen los ajustes (una cantidad fija de 0 € no existe)
JUSTO = 0.05  # 🟡 si lo libre de un cobro es menos del 5 % del salario
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


def fechas_cobro():
    """[F1, …, FN, F(N+1)]: los próximos cobros hasta el mes elegido (y el siguiente, que cierra el último)."""
    dia = dia_habitual()
    fechas = [ciclo.proximo_cobro()]
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

def pendiente_hoy(meta, cfg):
    """Lo que falta apartar en el ciclo actual con los cambios simulados (0 si ya lo confirmaste)."""
    if metas.estado_ciclo(meta) or 0 in cfg.get("pausa", ()):
        return 0.0
    if not cfg.get("aporte_modo") and not cfg.get("aporte_fijo") and not cfg.get("fecha_limite"):
        return metas.pendiente_ciclo(meta)
    return aporte(meta, metas.ahorrado(meta), ciclo.inicio(), cfg)


def estado_inicial_metas(cambios=None):
    """{meta_id: lo ahorrado contando que este ciclo apartas lo que toca}."""
    cambios = cambios or {}
    return {m["id"]: metas.ahorrado(m) + pendiente_hoy(m, cambios.get(m["id"], {})) for m in metas.activas()}


def aporte(meta, ahorrado, fecha_cobro, cfg):
    """Lo que toca apartar en el cobro de fecha_cobro (con los cambios simulados de cfg)."""
    objetivo = meta["objetivo"]
    falta = round(objetivo - ahorrado, 2)
    if falta <= 0.004:
        return 0.0
    modo = cfg.get("aporte_modo", meta["aporte_modo"])
    fijo = cfg.get("aporte_fijo", meta["aporte_fijo"])
    if modo == "fija" and fijo > 0:
        return round(min(fijo, falta), 2)
    limite = date.fromisoformat(cfg.get("fecha_limite", meta["fecha_limite"]))
    return round(falta / metas.meses_hasta(limite, fecha_cobro), 2)


def fin_metas(cambios=None, cobros=120):
    """{meta_id: fecha del cobro con el que llegarías al objetivo (None si no llegas en 10 años)}."""
    cambios = cambios or {}
    dia = dia_habitual()
    ahorrado = estado_inicial_metas(cambios)
    fin = {}
    fecha = ciclo.proximo_cobro()
    lista = metas.activas()
    for m in lista:
        if ahorrado[m["id"]] >= m["objetivo"] - 0.004:
            fin[m["id"]] = hoy()
    for k in range(1, cobros + 1):
        for m in lista:
            if m["id"] in fin:
                continue
            cfg = cambios.get(m["id"], {})
            if k not in cfg.get("pausa", ()):
                ahorrado[m["id"]] += aporte(m, ahorrado[m["id"]], fecha, cfg)
            if ahorrado[m["id"]] >= m["objetivo"] - 0.004:
                fin[m["id"]] = fecha
        if len(fin) == len(lista):
            break
        fecha = sumar_meses(fecha, 1, dia)
    return {m["id"]: fin.get(m["id"]) for m in lista}


# ---------- Simulación ----------

def simular(cambios=None, salario=None, extra_salario=0.0, contar_deben=True, sin_metas=False):
    """Proyección cobro a cobro. cambios: {meta_id: {aporte_modo, aporte_fijo, fecha_limite, pausa: {k}}}."""
    cambios = cambios or {}
    base, origen = salario_base()
    if salario is None:
        salario = base
    if salario is None:
        return None
    salario = round(salario + extra_salario, 2)
    fechas = fechas_cobro()
    n = len(fechas) - 1
    por_ciclo, sin_fecha, fines = _cacheado(("deudas", tuple(fechas)), lambda: calendario_deudas(fechas))
    lista_metas = [] if sin_metas else metas.activas()
    ahorrado = estado_inicial_metas(cambios)

    def base_hoy():
        s = analisis.saldo_actual()
        libre = analisis.dinero_libre(deudas.neto(s["total"])[0]) if s else 0.0
        return libre + sum(metas.pendiente_ciclo(m) for m in metas.activas()), \
            round(sum(i["importe"] for i in deudas.por_cobrar()), 2)
    libre_hoy, deben = _cacheado("hoy", base_hoy)
    # El dinero libre de hoy ya descuenta lo que falta apartar este ciclo; con cambios simulados se recalcula.
    libre_hoy -= sum(pendiente_hoy(m, cambios.get(m["id"], {})) for m in lista_metas)
    libre_hoy = round(libre_hoy, 2)
    deben_hoy = deben if contar_deben else 0.0
    puente = round(libre_hoy + deben_hoy, 2)

    ciclos, eventos, acumulado = [], [], puente
    for k in range(1, n + 1):
        fecha = fechas[k - 1]
        items = [x for x in por_ciclo[k] if contar_deben or x[2] != "deben"]
        totales = {c: 0.0 for c in CLASES}
        for _, importe, c in items:
            totales[c] += importe
        aportes = []
        for m in lista_metas:
            cfg = cambios.get(m["id"], {})
            importe = 0.0 if k in cfg.get("pausa", ()) else aporte(m, ahorrado[m["id"]], fecha, cfg)
            limite = date.fromisoformat(cfg.get("fecha_limite", m["fecha_limite"]))
            antes = ahorrado[m["id"]]
            ahorrado[m["id"]] = round(antes + importe, 2)
            if importe:
                aportes.append((m, importe, limite < fecha and not m["especial"]))
            if antes < m["objetivo"] - 0.004 <= ahorrado[m["id"]]:
                eventos.append((fecha, k, "meta", f"consigues «{m['nombre']}»", m["id"]))
        totales["metas"] = round(sum(x for _, x, _ in aportes), 2)
        pagos = round(totales["fijos"] + totales["subs"] + totales["cuotas"] + totales["unicos"], 2)
        libre = round(salario + totales["deben"] - pagos - totales["metas"], 2)
        acumulado = round(acumulado + libre, 2)
        if libre < 0 or acumulado < 0:
            estado = "🔴"
        elif libre < salario * JUSTO:
            estado = "🟡"
        else:
            estado = "🟢"
        ciclos.append({"k": k, "fecha": fecha, "fin": fechas[k], "salario": salario, "items": items,
                       "aportes": aportes, "totales": {c: round(v, 2) for c, v in totales.items()}, "pagos": pagos,
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
    maximo_metas = min(round(x["salario"] + x["totales"]["deben"] - x["pagos"], 2) for x in ciclos)
    return {"salario": salario, "origen": origen if not extra_salario else f"{origen}, {euros_cortos(extra_salario)}",
            "fechas": fechas, "ciclos": ciclos, "puente": puente, "libre_hoy": libre_hoy, "deben_hoy": deben_hoy,
            "eventos": sorted(eventos, key=lambda x: (x[0], x[2])), "sin_fecha": sin_fecha, "peor": peor,
            "sostenible": sostenible, "maximo_metas": maximo_metas, "final": ciclos[-1]["acumulado"],
            "rojos": [x for x in ciclos if x["estado"] == "🔴"], "metas": lista_metas, "cambios": cambios,
            "contar_deben": contar_deben}


def _cacheado(clave, calcular):
    if _CACHE is None:
        return calcular()
    if clave not in _CACHE:
        _CACHE[clave] = calcular()
    return _CACHE[clave]


def veredicto(p):
    if not p["sostenible"]:
        primero = p["rojos"][0]
        return "🔴", (f"No es sostenible: en el cobro de {mes_largo(primero['fecha'])} "
                      + (f"te faltan {euros(-primero['libre'])}" if primero["libre"] < 0
                         else f"tu dinero libre baja a {euros(primero['acumulado'])}"))
    if any(x["estado"] == "🟡" for x in p["ciclos"]):
        return "🟡", f"Llega, pero justo: el cobro más ajustado ({mes_largo(p['peor']['fecha'])}) te deja {euros(p['peor']['libre'])}"
    return "🟢", f"Sostenible: en cada cobro te quedan al menos {euros(p['peor']['libre'])} libres"


# ---------- Propuestas para que sea sostenible (o para acelerar) ----------

def aportes_primer_cobro(p):
    """{meta_id: aportación en el primer cobro proyectado} (base de las propuestas)."""
    base = {}
    for x in p["ciclos"]:
        for m, importe, _ in x["aportes"]:
            base.setdefault(m["id"], importe)
    return base


def _sin_rojos(cambios, holgado=False):
    """¿Sin cobros en rojo? Con holgado, además todos en verde (al menos un 5 % del salario libre)."""
    r = simular(cambios)
    if r is None:
        return False, r
    return (all(x["estado"] == "🟢" for x in r["ciclos"]) if holgado else r["sostenible"]), r


def _mejor_criterio(probar):
    """Primero intenta dejar todo en verde; si no se puede, que al menos no haya rojos."""
    for holgado in (True, False):
        resultado = probar(holgado)
        if resultado is not None:
            return resultado
    return None


def _buscar(funcion, bajo, alto, pasos=18):
    """Mayor valor en [bajo, alto] para el que funcion(valor) es cierto (supone monotonía)."""
    if not funcion(bajo):
        return None
    for _ in range(pasos):
        medio = (bajo + alto) / 2
        if funcion(medio):
            bajo = medio
        else:
            alto = medio
    return bajo


def propuestas(p):
    """[{clave, titulo, explicacion, cambios, resultado}] para la configuración actual."""
    global _CACHE
    _CACHE = {}
    try:
        return _propuestas(p)
    finally:
        _CACHE = None


def _propuestas(p):
    base = aportes_primer_cobro(p)
    activas = [m for m in p["metas"] if m["id"] in base]
    lista = []
    if not activas:
        return lista
    if not p["sostenible"]:
        # A) Recortar todas las aportaciones en la misma proporción
        def con_factor(f):
            return {m["id"]: {"aporte_modo": "fija", "aporte_fijo": max(MINIMO, math.floor(base[m["id"]] * f))}
                    for m in activas}
        f = _mejor_criterio(lambda h: _buscar(lambda x: _sin_rojos(con_factor(x), h)[0], 0.0, 1.0))
        if f is not None:
            cambios = con_factor(f)
            lista.append({"clave": "A", "titulo": f"✂️ Recortar todas las metas al {f * 100:.0f} %",
                          "explicacion": "Cada meta aporta lo mismo en proporción; llegan más tarde.",
                          "cambios": cambios, "resultado": simular(cambios)})
        # B) Alargar las fechas de las metas con aportación «necesaria»
        necesarias = [m for m in activas if m["aporte_modo"] != "fija" and not m["especial"]]
        if necesarias:
            def con_meses(n):
                return {m["id"]: {"fecha_limite": sumar_meses(date.fromisoformat(m["fecha_limite"]), n, 28).isoformat()}
                        for m in necesarias}
            plazos = (1, 2, 3, 4, 6, 9, 12, 18, 24, 36)
            meses = _mejor_criterio(lambda h: next((n for n in plazos if _sin_rojos(con_meses(n), h)[0]), None))
            if meses:
                cambios = con_meses(meses)
                lista.append({"clave": "B", "titulo": f"📅 Alargar {meses} mes{'es' if meses > 1 else ''} las fechas",
                              "explicacion": "Las metas con aportación «la necesaria» piden menos cada cobro.",
                              "cambios": cambios, "resultado": simular(cambios)})
        # C) Por prioridad: se mantiene la de fecha más cercana y se recortan las demás, empezando por la más lejana
        orden = sorted(activas, key=lambda m: (m["especial"] != "colchon", m["fecha_limite"]))

        def priorizar(holgado):
            cambios = {}
            for m in reversed(orden[1:]):
                def con(x, m=m, previos=dict(cambios)):
                    return {**previos, m["id"]: {"aporte_modo": "fija",
                                                 "aporte_fijo": max(MINIMO, math.floor(base[m["id"]] * x))}}
                x = _buscar(lambda v: _sin_rojos(con(v), holgado)[0], 0.0, 1.0)
                cambios = con(x if x is not None else 0.0)
                if x is not None:
                    return cambios
            return None
        cambios = _mejor_criterio(priorizar) if len(orden) > 1 else None
        if cambios:
            lista.append({"clave": "C", "titulo": f"🥇 Priorizar «{orden[0]['nombre']}»",
                          "explicacion": "La meta más próxima sigue igual; se recortan las demás, la más lejana primero.",
                          "cambios": cambios, "resultado": simular(cambios)})
    elif p["peor"]["libre"] > 20:
        # D) Acelerar: la mitad de lo que sobra en el cobro más justo, repartido según lo que le falta a cada meta
        extra = math.floor(p["peor"]["libre"] / 2)
        normales = [m for m in activas if not m["especial"]]
        faltas = {m["id"]: max(0.0, m["objetivo"] - metas.ahorrado(m)) for m in normales}
        total = sum(faltas.values())
        if total > 0 and extra >= 10:
            cambios = {m["id"]: {"aporte_modo": "fija", "aporte_fijo": round(base[m["id"]] + extra * faltas[m["id"]] / total)}
                       for m in normales}
            lista.append({"clave": "D", "titulo": f"🚀 Acelerar tus metas (+{euros_cortos(extra)}/cobro)",
                          "explicacion": "Usas la mitad de lo que te sobra en el cobro más justo para llegar antes.",
                          "cambios": cambios, "resultado": simular(cambios)})
    return lista


def firma(p):
    """Identifica la configuración actual (para no volver a proponer lo que ignoraste)."""
    partes = [f"{p['salario']:.0f}"] + [f"{m['id']}:{m['aporte_modo']}:{m['aporte_fijo']:.0f}:{m['fecha_limite']}"
                                         for m in p["metas"]]
    partes += [str(d["id"]) for d in deudas.activas()]
    return hashlib.sha1("|".join(partes).encode()).hexdigest()[:10]


def ignorada(p):
    return datos.enviado(f"proy_ignorar:{firma(p)}")


def aplicar(cambios, descripcion):
    """Guarda los cambios de una propuesta en las metas. Devuelve el id de acción para deshacer."""
    deshacer = []
    for meta_id, cfg in cambios.items():
        meta = metas.obtener(meta_id)
        deshacer.append(f"UPDATE metas SET aporte_modo = '{meta['aporte_modo']}', aporte_fijo = {float(meta['aporte_fijo'])}, "
                        f"fecha_limite = '{meta['fecha_limite']}' WHERE id = {int(meta_id)} AND ?1 IS NOT NULL")
        for campo in ("aporte_modo", "aporte_fijo", "fecha_limite"):
            if campo in cfg:
                metas.configurar(meta_id, campo, cfg[campo])
    return datos.registrar_accion("metas", 0, "; ".join(deshacer), descripcion)


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
    if not p or p["sostenible"]:
        return None
    icono, texto = veredicto(p)
    return f"{icono} <b>Proyección</b>: {texto}. Mira 📈 Proyección › ⚖️ Ajustar."


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

