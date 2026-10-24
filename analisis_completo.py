"""📊 Análisis › 🧭 Análisis completo: todo junto (saldo, deudas, metas, gastos) por ciclos de cobro.

Siete pantallas, cada una con un texto corto, un gráfico y una línea «💡 Qué significa»:
📌 Ahora · 📅 Por meses · 📆 Anual · 💧 Flujo de caja · 🎯 Metas · 🩺 Salud financiera · 🔮 Trayectoria.

Un «mes» es un ciclo de cobro (del día que cobras al siguiente cobro). Todo se calcula con lo
guardado en la actualización diaria: nunca se pregunta al banco. Si un ciclo no tiene datos del
banco (la primera descarga solo trae ~90 días), se indica «datos desde …» y no se inventa nada.

Índice de salud financiera (0–100): nota que resume cómo van tus finanzas. Pesos (PESOS):
ahorro 25 · endeudamiento 20 · colchón 20 · presupuesto 15 · puntualidad 10 · metas 10.
Solo se evalúa lo que tiene datos (el colchón, solo si está activado) y se reparte el peso entre
lo evaluado. 🟢 80–100 bien · 🟡 50–79 mejorable · 🔴 < 50 hay que actuar.
"""
import html
import math
from datetime import date, timedelta

import analisis
import analisis_deudas
import ciclo
import colchon
import config
import datos
import deudas
import graficos
import metas
import movimientos
from formato import MESES, MESES_CORTOS, euros, euros_cortos, fecha_corta, sumar_meses
from movimientos import CATEGORIAS

PESOS = {"ahorro": 25, "endeudamiento": 20, "colchon": 20, "presupuesto": 15, "puntualidad": 10, "metas": 10}
NOMBRES = {"ahorro": "🐷 Ahorro", "endeudamiento": "💳 Endeudamiento", "colchon": "🛟 Colchón",
           "presupuesto": "🎯 Presupuesto", "puntualidad": "⏰ Puntualidad", "metas": "🏁 Metas"}
TASA_IDEAL = 0.20  # ahorrar el 20 % de lo que entra
HORMIGA = 10.0  # gastos pequeños (menos de 10 €) que sumados se notan
PANTALLAS = {"ahora": "📌 Ahora", "meses": "📅 Por meses", "anual": "📆 Anual", "flujo": "💧 Flujo de caja",
             "metas": "🎯 Metas", "salud": "🩺 Salud", "tray": "🔮 Trayectoria"}


def e(texto):
    return html.escape(str(texto))


def hoy():
    return config.ahora().date()


def pct(fraccion):
    return f"{fraccion * 100:.0f} %"


def etiqueta(inicio):
    """Nombre corto del ciclo: el mes en que empieza («nov 26»)."""
    return f"{MESES_CORTOS[inicio.month - 1]} {str(inicio.year)[2:]}"


def flecha(cambio):
    return "➖" if abs(cambio) < 0.02 else ("🔺" if cambio > 0 else "🔻")


# ---------- Ciclos y datos de cada ciclo ----------

def ciclos(n=12, d=None):
    """[(inicio, fin)] de los últimos n ciclos de cobro, del más antiguo al actual (fin excluido)."""
    d = d or hoy()
    inicio, fin = ciclo.inicio(d), ciclo.proximo_cobro(d)
    lista = [(inicio, fin)]
    while len(lista) < n:
        anterior = ciclo.inicio(inicio - timedelta(days=1))
        if (inicio - anterior).days < 20:  # antes del primer salario registrado: un mes antes
            anterior = sumar_meses(inicio, -1)
        lista.append((anterior, inicio))
        inicio = anterior
    return list(reversed(lista))


def primer_movimiento():
    valor = datos.valor("SELECT MIN(fecha) FROM movimientos")
    return date.fromisoformat(valor) if valor else None


def primer_saldo():
    valor = datos.valor("SELECT MIN(fecha) FROM saldos")
    return date.fromisoformat(valor) if valor else None


def gastos_periodo(desde, hasta):
    """Gastado entre desde y hasta (excluido) según los movimientos, o None si no hay datos de esos días."""
    primero = primer_movimiento()
    if not primero or primero > desde:
        return None
    return movimientos.gastos_e_ingresos(desde, hasta)[0]


def pagos_entre(desde, hasta, sentido="debo"):
    """{tipo de deuda: total pagado} con fecha de pago en el periodo (sin lo «ya pagado» al apuntarla)."""
    filas = datos.todos("SELECT d.tipo, SUM(p.importe) AS total FROM pagos p JOIN deudas d ON d.id = p.deuda_id "
                        "WHERE d.sentido = ? AND p.periodo != ? AND p.fecha >= ? AND p.fecha < ? GROUP BY d.tipo",
                        sentido, deudas.INICIAL, desde.isoformat(), hasta.isoformat())
    return {f["tipo"]: round(f["total"], 2) for f in filas}


def todas_las_metas():
    return datos.todos("SELECT * FROM metas WHERE activa >= 0")


def a_metas_entre(desde, hasta):
    """Dinero que ha ido a tus metas en el periodo (lo que ha crecido lo ahorrado en cada una)."""
    total = 0.0
    for m in todas_las_metas():
        if m["creada"][:10] >= hasta.isoformat():
            continue
        total += metas.ahorrado_en(m, hasta - timedelta(days=1)) - metas.ahorrado_en(m, desde - timedelta(days=1))
    return round(total, 2)


def resumen(inicio, fin):
    """Todo lo de un ciclo: ingresos, gastos (fijos, cuotas, suscripciones, variable), metas y lo que queda."""
    d = hoy()
    actual = inicio <= d < fin
    hasta = min(fin, d + timedelta(days=1))
    primero = primer_movimiento()
    con_movimientos = bool(primero) and primero <= hasta - timedelta(days=1)
    parcial = con_movimientos and primero > inicio
    salario = datos.valor("SELECT COALESCE(SUM(importe), 0) FROM ingresos WHERE tipo = 'salario' AND fecha >= ? "
                          "AND fecha < ?", inicio.isoformat(), hasta.isoformat())
    categorias = []
    if con_movimientos:
        gastos, ingresos = movimientos.gastos_e_ingresos(inicio, hasta)
        categorias = movimientos.por_categoria(inicio, hasta)
    else:
        ingresos = datos.valor("SELECT COALESCE(SUM(importe), 0) FROM ingresos WHERE fecha >= ? AND fecha < ?",
                               inicio.isoformat(), hasta.isoformat())
        desde_saldo = primer_saldo()
        antes = analisis.total_en(inicio) if desde_saldo and desde_saldo <= inicio else None
        despues = analisis.total_en(hasta - timedelta(days=1))
        gastos = max(0.0, round(antes + ingresos - despues, 2)) if antes is not None and despues is not None else 0.0
    hay_datos = con_movimientos or (gastos > 0 or ingresos > 0)
    pagos = pagos_entre(inicio, hasta)
    fijos = pagos.get("fijo", 0.0)
    subs = max(pagos.get("suscripcion", 0.0), dict(categorias).get("suscripciones", 0.0))
    cuotas = round(sum(v for k, v in pagos.items() if k not in ("fijo", "suscripcion")), 2)
    variable = max(0.0, round(gastos - fijos - subs - cuotas, 2))
    a_metas = a_metas_entre(inicio, hasta)
    comprometido = round(sum(pagos.values()), 2)
    if actual:
        comprometido += sum(i["importe"] for i in deudas.pendientes(d))
    base_ratio = salario or ingresos
    dias = max(1, (hasta - inicio).days)
    return {
        "inicio": inicio, "fin": fin, "hasta": hasta, "actual": actual, "parcial": parcial, "hay_datos": hay_datos,
        "con_movimientos": con_movimientos, "ingresos": round(ingresos, 2), "salario": round(salario, 2),
        "gastos": round(gastos, 2), "fijos": fijos, "cuotas": cuotas, "subs": round(subs, 2), "variable": variable,
        "metas": a_metas, "queda": round(ingresos - gastos - a_metas, 2), "balance": round(ingresos - gastos, 2),
        "tasa": (ingresos - gastos) / ingresos if ingresos > 0 else None, "dias": dias,
        "diario": round(gastos / dias, 2), "ratio": comprometido / base_ratio if base_ratio > 0 else None,
        "comprometido": round(comprometido, 2), "categorias": categorias,
    }


def historial(n=12):
    """Resúmenes de los últimos n ciclos con datos (del más antiguo al actual)."""
    return [r for r in (resumen(i, f) for i, f in ciclos(n)) if r["hay_datos"]]


def cerrados(lista, n=3):
    """Los últimos n ciclos completos (sin el actual ni los que empiezan antes de tener datos)."""
    return [r for r in lista if not r["actual"] and not r["parcial"]][-n:]


def ahorro_mensual():
    """(ahorro medio al mes, ingreso medio al mes, de dónde sale) para proyectar."""
    lista = historial(6)
    completos = cerrados(lista, 3)
    if completos:
        return (round(sum(r["balance"] for r in completos) / len(completos), 2),
                round(sum(r["ingresos"] for r in completos) / len(completos), 2),
                f"media de tus {len(completos)} último{'s' if len(completos) > 1 else ''} ciclo{'s' if len(completos) > 1 else ''}")
    c = analisis.datos_ciclo()
    if c["transcurridos"] >= 7 and c["ingresos"] > 0:
        return round(c["ingresos"] - c["proyeccion"], 2), c["ingresos"], "previsión del ciclo actual"
    return None, None, ""


def dinero_libre():
    s = analisis.saldo_actual()
    if not s:
        return None
    neto, _ = deudas.neto(s["total"])
    return analisis.dinero_libre(neto)


def patrimonio():
    """(patrimonio neto, saldo, te deben, debes)."""
    s = analisis.saldo_actual()
    saldo = s["total"] if s else 0.0
    deben = round(sum(deudas.restante(x)[0] for x in deudas.activas("me_deben")), 2)
    debes = round(sum(analisis_deudas.deuda_pendiente(x) for x in deudas.activas("debo")), 2)
    return round(saldo + deben - debes, 2), saldo, deben, debes


def necesario_metas():
    """Lo que necesitas apartar al mes para llegar a tiempo a todas tus metas."""
    return round(sum(metas.progreso(m)["mensual"] for m in metas.activas() if not m["especial"]), 2)


# ---------- 📌 Ahora ----------

def ahora():
    s = analisis.saldo_actual()
    if not s:
        return analisis.texto_saldo(), []
    d = hoy()
    neto, items = deudas.neto(s["total"])
    pendiente = round(sum(i["importe"] for i in items), 2)
    en_metas = colchon.dinero_en_metas()
    apartar = round(sum(metas.pendiente_ciclo(m) for m in metas.activas()), 2)
    libre = round(s["total"] - pendiente - en_metas - apartar, 2)
    diario, dias = analisis.puedes_gastar(neto)
    pat, saldo, deben, debes = patrimonio()
    c = analisis.datos_ciclo()
    lineas = [f"📌 <b>Ahora mismo</b> ({fecha_corta(d)}) · <i>{analisis.texto_actualizado().lower()}</i>", "",
              f"💰 En tus cuentas: <b>{euros(s['total'])}</b>"]
    if pendiente:
        lineas.append(f"💸 Pendiente de pagar este ciclo: −{euros(pendiente)}")
    if en_metas:
        lineas.append(f"🎯 Ya está en las cuentas de tus metas: −{euros(en_metas)}")
    if apartar:
        lineas.append(f"🎯 Falta apartar este ciclo para metas: −{euros(apartar)}")
    lineas += [f"= 💶 <b>Dinero libre: {euros(libre)}</b>",
               f"   ≈ {euros_cortos(diario)}/día durante {dias} días (hasta el cobro)", "",
               f"🏦 <b>Patrimonio neto: {euros(pat)}</b>",
               f"   lo que tienes {euros_cortos(saldo)} + te deben {euros_cortos(deben)} − debes {euros_cortos(debes)}", "",
               f"📆 Ciclo: día {c['transcurridos']} de ~{c['duracion']} · gastado {euros(c['gastos'])} "
               f"(~{euros_cortos(c['medio'])}/día)"]
    # Comparación con el ciclo anterior y con la media de 3 ciclos, a estas alturas del ciclo
    previos = ciclos(4)[:-1]
    a_estas_alturas = [gastos_periodo(i, min(f, i + timedelta(days=c["transcurridos"]))) for i, f in previos]
    a_estas_alturas = [g for g in a_estas_alturas if g is not None]
    if a_estas_alturas:
        ultimo = a_estas_alturas[-1]
        media = sum(a_estas_alturas) / len(a_estas_alturas)
        partes = []
        if ultimo:
            cambio = (c["gastos"] - ultimo) / ultimo
            partes.append(f"{flecha(cambio)} {pct(abs(cambio))} {'más' if cambio > 0 else 'menos'} que el ciclo anterior")
        if len(a_estas_alturas) > 1 and media:
            cambio = (c["gastos"] - media) / media
            partes.append(f"{flecha(cambio)} {pct(abs(cambio))} {'más' if cambio > 0 else 'menos'} que tu media "
                          f"de {len(a_estas_alturas)} ciclos")
        if partes:
            lineas.append("   A estas alturas: " + " · ".join(partes))
    if c["transcurridos"] >= 3:
        quedaria = round(libre - c["normal"] * max(0, dias - 1), 2)
        icono = "🟢" if quedaria >= 0 else "🔴"
        lineas.append(f"🔮 A tu ritmo normal (~{euros_cortos(c['normal'])}/día), al cobrar te quedarían "
                      f"{icono} <b>{euros(quedaria)}</b>")
    if deben:
        lineas.append(f"🤝 Te deben {euros(deben)} (no cuenta como dinero libre hasta que te paguen)")
    meses_cubiertos = colchon.meses_cubiertos(s["total"])
    if meses_cubiertos is not None:
        que = "tu colchón" if colchon.activo() else "tu dinero libre"
        lineas.append(f"🛟 Con {que} cubrirías {str(meses_cubiertos).replace('.', ',')} meses de gastos")
    lineas += ["", "💡 <i>Qué significa: el dinero libre es lo que de verdad puedes gastar sin tocar pagos ni metas. "
                   "El patrimonio neto es lo que tendrías si todos te pagaran y tú pagaras todo hoy.</i>"]
    pasos = [("Saldo", s["total"], "total")]
    pasos += [(n, v, "salida") for n, v in (("Por pagar", pendiente), ("En metas", en_metas), ("Por apartar", apartar)) if v]
    pasos.append(("Libre", libre, "total"))
    return "\n".join(lineas), [graficos.cascada(pasos, "De tu saldo a tu dinero libre")]


# ---------- 📅 Por meses (ciclos de cobro) ----------

def aviso_datos(lista):
    primero = primer_movimiento()
    if primero and (not lista or lista[0]["parcial"] or len(lista) < 12):
        return f"<i>📭 Datos del banco desde el {fecha_corta(primero)} {primero.year}: los ciclos anteriores no se pueden calcular.</i>"
    return ""


def por_meses():
    lista = historial(12)
    if not lista:
        return ("📅 <b>Por meses</b>\n\nAún no hay datos suficientes: se irán llenando con la actualización diaria.", [])
    presupuesto = config.importe("PRESUPUESTO_CICLO")
    lineas = ["📅 <b>Por meses</b> (cada mes = un ciclo de cobro)", ""]
    for r in reversed(lista):
        icono = "⏳" if r["actual"] else ("🟢" if r["balance"] >= 0 else "🔴")
        texto = f"{icono} <b>{etiqueta(r['inicio'])}</b>{'*' if r['parcial'] else ''}: {euros_cortos(round(r['balance']))}"
        if r["tasa"] is not None:
            texto += f" ({pct(r['tasa'])})"
        texto += f" · {euros_cortos(round(r['diario']))}/día"
        if r["ratio"] is not None:
            texto += f" · deudas {pct(r['ratio'])}"
        if presupuesto and not r["actual"]:
            texto += " · ✅ presup." if r["gastos"] <= presupuesto else f" · ❌ +{euros_cortos(round(r['gastos'] - presupuesto))}"
        lineas.append(texto)
    lineas.append("<i>balance (ingresos − gastos) · tasa de ahorro · gasto al día · % del salario en pagos y deudas</i>")
    completos = cerrados(lista, 12)
    if completos:
        media = sum(r["balance"] for r in completos) / len(completos)
        mejor = max(completos, key=lambda r: r["balance"])
        peor = min(completos, key=lambda r: r["balance"])
        lineas += ["", f"🐷 Ahorro medio por ciclo: <b>{euros(media)}</b>"]
        if len(completos) > 1:
            lineas.append(f"🏆 Mejor: {etiqueta(mejor['inicio'])} ({euros_cortos(round(mejor['balance']))}) · "
                          f"peor: {etiqueta(peor['inicio'])} ({euros_cortos(round(peor['balance']))})")
        if len(completos) >= 2:
            recientes = completos[-3:]
            antiguos = completos[:-3] or completos[:1]
            ahora_d = sum(r["diario"] for r in recientes) / len(recientes)
            antes_d = sum(r["diario"] for r in antiguos) / len(antiguos)
            if antes_d and recientes != antiguos:
                cambio = (ahora_d - antes_d) / antes_d
                lineas.append(f"📉 Gasto diario: {euros_cortos(round(ahora_d))}/día últimamente, "
                              f"{flecha(cambio)} {pct(abs(cambio))} {'más' if cambio > 0 else 'menos'} que antes")
    # Categorías del último ciclo completo frente a la media de los anteriores
    if completos and completos[-1]["categorias"]:
        ultimo = completos[-1]
        anteriores = completos[:-1]
        lineas += ["", f"🧩 <b>En qué gastaste en {etiqueta(ultimo['inicio'])}</b>"]
        for cat, total in ultimo["categorias"][:5]:
            texto = f"{CATEGORIAS.get(cat, cat)} {euros_cortos(round(total))}"
            if anteriores:
                media_cat = sum(dict(r["categorias"]).get(cat, 0.0) for r in anteriores) / len(anteriores)
                if media_cat:
                    cambio = (total - media_cat) / media_cat
                    texto += f" ({flecha(cambio)} {pct(abs(cambio))} vs media)"
            lineas.append(texto)
    if any(r["parcial"] for r in lista):
        lineas.append("<i>* ciclo con datos solo desde mitad de ciclo</i>")
    aviso = aviso_datos(lista)
    if aviso:
        lineas += ["", aviso]
    lineas += ["", "💡 <i>Qué significa: si el balance es verde, ese mes entró más de lo que salió (ahorraste). "
                   "Lo ideal es ahorrar el 20 % o más y no dedicar más del 30 % del salario a pagos y deudas.</i>"]
    enteros = [r for r in lista if not r["parcial"]]
    imagenes = []
    if enteros:
        imagenes.append(graficos.barras_dobles([etiqueta(r["inicio"]) + ("\n(en curso)" if r["actual"] else "") for r in enteros],
                                               [r["ingresos"] for r in enteros], [r["gastos"] for r in enteros],
                                               ("Ingresos", "Gastos"), "Ingresos y gastos por ciclo de cobro"))
    con_ratio = [r for r in enteros if r["ratio"] is not None]
    if con_ratio:
        imagenes.append(graficos.ratio_meses([etiqueta(r["inicio"]) for r in con_ratio], [r["ratio"] for r in con_ratio],
                                             "Ratio de endeudamiento: % del salario en pagos y deudas"))
    return "\n".join(lineas), imagenes


# ---------- 📆 Anual ----------

def anual():
    """Balance del año con los ciclos completos (el ciclo en curso se muestra aparte y se proyecta)."""
    d = hoy()
    lista = historial(24)
    completos = cerrados(lista, 24)
    este = [r for r in completos if r["inicio"].year == d.year]
    pasado = [r for r in completos if r["inicio"].year == d.year - 1]
    en_curso = next((r for r in lista if r["actual"]), None)
    if not este and not en_curso:
        return "📆 <b>Anual</b>\n\nAún no hay datos de este año.", []
    ingresos, gastos = sum(r["ingresos"] for r in este), sum(r["gastos"] for r in este)
    lineas = [f"📆 <b>Balance de {d.year}</b>", ""]
    if este:
        lineas += [f"<i>{len(este)} ciclo{'s' if len(este) != 1 else ''} completo{'s' if len(este) != 1 else ''}, "
                   f"desde el {fecha_corta(este[0]['inicio'])}</i>",
                   f"💶 Ingresos: <b>{euros(ingresos)}</b>", f"💸 Gastos: <b>{euros(gastos)}</b>",
                   f"🐷 Ahorro: <b>{euros(ingresos - gastos, signo=True)}</b>"
                   + (f" ({pct((ingresos - gastos) / ingresos)} de lo que entró)" if ingresos else "")]
    if en_curso and en_curso["inicio"].year == d.year:
        lineas.append(f"⏳ Ciclo en curso ({etiqueta(en_curso['inicio'])}): {euros(en_curso['balance'], signo=True)} hasta hoy")
    if pasado:
        meses_este = {r["inicio"].month for r in este}
        comparables = [r for r in pasado if r["inicio"].month in meses_este]
        if comparables:
            ahorro_antes = sum(r["balance"] for r in comparables)
            lineas.append(f"↔️ Los mismos meses de {d.year - 1}: ahorro {euros(ahorro_antes, signo=True)} "
                          f"({euros(ingresos - gastos - ahorro_antes, signo=True)} de diferencia)")
    else:
        lineas.append(f"<i>Aún no hay datos de {d.year - 1} para comparar.</i>")
    lineas.append("")
    for n in (3, 12):
        grupo = completos[-n:]
        entradas = sum(r["ingresos"] for r in grupo)
        if grupo and entradas and (n == 3 or len(grupo) > 3):
            tasa = sum(r["balance"] for r in grupo) / entradas
            icono = "🟢" if tasa >= TASA_IDEAL else ("🟡" if tasa >= 0.10 else "🔴")
            lineas.append(f"{icono} Tasa de ahorro, últimos {len(grupo)} ciclos: <b>{pct(tasa)}</b> (ideal: 20 % o más)")
    ahorro_medio, _, origen = ahorro_mensual()
    if ahorro_medio is not None:
        c = analisis.datos_ciclo()
        previsto_actual = c["ingresos"] - c["proyeccion"] if en_curso and en_curso["inicio"].year == d.year else 0.0
        restantes = 12 - (en_curso["inicio"].month if en_curso else d.month)
        total_anio = ingresos - gastos + previsto_actual + ahorro_medio * restantes
        lineas.append(f"🔮 A este ritmo ({origen}) acabarás {d.year} habiendo ahorrado ~<b>{euros_cortos(round(total_anio))}</b>")
        lineas.append(f"📅 En 12 meses a este ritmo: ~{euros_cortos(round(ahorro_medio * 12))}")
    plazos, fijos, subs = analisis_deudas.compromiso_mensual()
    if fijos + subs:
        lineas.append(f"🏠 Gastos fijos y suscripciones al año: {euros(round((fijos + subs) * 12, 2))}")
    pagado = analisis_deudas.pagado_en(d.year, "debo")
    if pagado:
        lineas.append(f"🧾 Pagado en deudas y pagos en {d.year}: {euros(pagado)}")
    top = {}
    for r in este:
        for cat, total in r["categorias"]:
            top[cat] = top.get(cat, 0.0) + total
    if top:
        orden = sorted(top.items(), key=lambda x: -x[1])[:3]
        lineas.append("🧩 Donde más gastas: " + " · ".join(f"{CATEGORIAS.get(c, c)} {euros_cortos(round(t))}"
                                                           for c, t in orden))
    lineas += ["", "💡 <i>Qué significa: el ahorro del año es lo que te ha sobrado sumando los ciclos completos. "
                   "La línea del gráfico sube cuando un ciclo ahorras y baja cuando gastas más de lo que entra.</i>"]
    imagenes = []
    if len(este) >= 2:
        fechas, acumulado, total = [este[0]["inicio"]], [0.0], 0.0
        for r in este:
            total += r["balance"]
            fechas.append(r["fin"])
            acumulado.append(round(total, 2))
        series = [(str(d.year), acumulado)]
        if len(pasado) >= len(este):
            total, previo = 0.0, [0.0]
            for r in pasado[:len(este)]:
                total += r["balance"]
                previo.append(round(total, 2))
            series.append((str(d.year - 1), previo))
        imagenes.append(graficos.lineas(fechas, series, f"Ahorro acumulado en {d.year} (ciclos completos)",
                                        desde_cero=True))
    return "\n".join(lineas), imagenes


# ---------- 💧 Flujo de caja ----------

def flujo(atras=0):
    lista = ciclos(atras + 1)
    if len(lista) <= atras:
        atras = len(lista) - 1
    inicio, fin = lista[0]
    r = resumen(inicio, fin)
    titulo = f"{MESES[inicio.month - 1]} {inicio.year} ({fecha_corta(inicio)} – {fecha_corta(fin - timedelta(days=1))})"
    if not r["hay_datos"]:
        return (f"💧 <b>Flujo de caja · {titulo}</b>\n\nNo hay datos del banco de este ciclo.\n{aviso_datos([])}", [])
    entra = r["ingresos"]
    lineas = [f"💧 <b>Flujo de caja · {titulo}</b>"]
    if r["actual"]:
        lineas.append(f"<i>Hasta hoy (día {r['dias']} del ciclo)</i>")
    if r["parcial"]:
        lineas.append(f"<i>Datos solo desde el {fecha_corta(primer_movimiento())}</i>")
    lineas += ["", f"💶 Entró: <b>{euros(entra)}</b>" + (f" (salario {euros_cortos(r['salario'])})" if r["salario"] else "")]

    def linea(icono, nombre, valor, explica):
        if valor:
            parte = f" · {pct(valor / entra)}" if entra else ""
            lineas.append(f"{icono} {nombre}: −{euros(valor)}{parte}  <i>{explica}</i>")

    linea("🏠", "Gastos fijos", r["fijos"], "alquiler, recibos…")
    linea("💳", "Cuotas y deudas", r["cuotas"], "lo que has pagado de deudas")
    linea("📺", "Suscripciones", r["subs"], "cargos de cada mes")
    linea("🛒", "Gasto variable", r["variable"], "el día a día")
    linea("🎯", "A tus metas", r["metas"], "dinero apartado")
    icono = "🟢" if r["queda"] >= 0 else "🔴"
    lineas += ["──────────", f"{icono} <b>Queda: {euros(r['queda'])}</b>"
               + (f" ({pct(r['queda'] / entra)} de lo que entró)" if entra else "")]
    if r["actual"]:
        pendiente = deudas.pendientes()
        por_pagar = round(sum(i["importe"] for i in pendiente), 2)
        por_apartar = round(sum(metas.pendiente_ciclo(m) for m in metas.activas()), 2)
        c = analisis.datos_ciclo()
        resto = max(0, c["duracion"] - c["transcurridos"])
        prevision = round(r["queda"] - por_pagar - por_apartar - c["normal"] * resto, 2)
        if por_pagar:
            lineas.append(f"⏳ Aún por pagar este ciclo: −{euros(por_pagar)} ("
                          + ", ".join(e(i["deuda"]["nombre"]) for i in pendiente[:4]) + ("…" if len(pendiente) > 4 else "") + ")")
        if por_apartar:
            lineas.append(f"⏳ Aún por apartar a metas: −{euros(por_apartar)}")
        lineas.append(f"🔮 Previsión al final del ciclo (gastando ~{euros_cortos(round(c['normal']))}/día): queda "
                      f"{'🟢' if prevision >= 0 else '🔴'} <b>{euros(prevision)}</b>")
    fijo_total = r["fijos"] + r["cuotas"] + r["subs"]
    if r["gastos"]:
        lineas += ["", f"⚖️ Fijo vs variable: {pct(fijo_total / r['gastos'])} fijo · {pct(r['variable'] / r['gastos'])} "
                       "variable (lo variable es lo que puedes recortar)"]
    if r["categorias"]:
        lineas.append("🧩 " + " · ".join(f"{CATEGORIAS.get(c, c)} {euros_cortos(round(t))}" for c, t in r["categorias"][:4]))
    # Suscripciones y gastos hormiga (últimos 30 días), al año
    d = hoy()
    if movimientos.hay_movimientos():
        apuntadas = sum(x["importe"] for x in deudas.activas("debo") if x["tipo"] == "suscripcion")
        categoria = dict(movimientos.por_categoria(d - timedelta(days=29), d + timedelta(days=1))).get("suscripciones", 0.0)
        mensual = max(apuntadas, categoria)
        if mensual:
            lineas.append(f"📺 Suscripciones: {euros(mensual)}/mes = <b>{euros(round(mensual * 12, 2))} al año</b>")
        pequenos = [-m["importe"] for m in movimientos.entre(d - timedelta(days=29), d + timedelta(days=1))
                    if -HORMIGA < m["importe"] < 0]
        if len(pequenos) >= 5:
            total = sum(pequenos)
            lineas.append(f"🐜 Gastos hormiga (menos de {euros_cortos(HORMIGA)}): {len(pequenos)} en 30 días, "
                          f"{euros(total)} → ~<b>{euros_cortos(round(total * 365 / 30))} al año</b>")
    lineas += ["", "💡 <i>Qué significa: de todo lo que entra, cuánto se va en cada cosa y cuánto queda. "
                   "Si «Queda» es verde, ese ciclo ganaste dinero; si es rojo, gastaste más de lo que entró.</i>"]
    pasos = [("Ingresos", entra, "total")]
    pasos += [(n, v, "salida") for n, v in (("Fijos", r["fijos"]), ("Cuotas", r["cuotas"]), ("Suscripc.", r["subs"]),
                                            ("Variable", r["variable"]), ("Metas", r["metas"])) if v > 0]
    if r["metas"] < 0:
        pasos.append(("De metas", -r["metas"], "entrada"))
    pasos.append(("Queda", r["queda"], "total"))
    return "\n".join(lineas), [graficos.cascada(pasos, f"Flujo de caja · ciclo de {MESES[inicio.month - 1]}"
                                                + (" (hasta hoy)" if r["actual"] else ""))]


# ---------- 🎯 Metas ----------

def pantalla_metas():
    lista = metas.activas()
    if not lista:
        return ("🎯 <b>Metas</b>\n\nAún no tienes metas. Créalas en el botón 🎯 Metas del teclado.", [])
    lineas = ["🎯 <b>Progreso de tus metas</b>", ""]
    filas = []
    for m in lista:
        p = metas.progreso(m)
        estimada = metas.fecha_estimada(m)
        ritmo = metas.ritmo_real(m)
        previsto = metas.aporte_previsto(m)
        icono = "🛟" if m["especial"] == "colchon" else "🎯"
        lineas.append(f"{icono} <b>{e(m['nombre'])}</b> · {pct(min(1, p['fraccion']))} · {p['estado']}")
        lineas.append(f"   {euros_cortos(p['ahorrado'])} de {euros_cortos(p['objetivo'])} · faltan {euros_cortos(p['falta'])}")
        if p["falta"] > 0:
            cuando = "sin fecha a tu ritmo actual" if not estimada else f"llegarías en {MESES[estimada.month - 1]} {estimada.year}"
            if m["especial"] != "colchon":
                lineas.append(f"   📅 Objetivo: {MESES[p['limite'].month - 1]} {p['limite'].year} · {cuando}")
            lineas.append(f"   🧮 Necesitas {euros_cortos(p['mensual'])}/mes · pides {euros_cortos(previsto)} este ciclo · "
                          f"ritmo real {euros_cortos(ritmo)}/mes")
            estado = metas.estado_ciclo(m)
            if estado:
                lineas.append(f"   ✅ Este ciclo: {'saltado' if estado['estado'] == 'saltado' else euros_cortos(estado['importe'])}")
        filas.append((m["nombre"], p["ahorrado"], p["objetivo"]))
    normales = [m for m in lista if not m["especial"]]
    if normales:
        objetivo = sum(m["objetivo"] for m in normales)
        llevas = sum(metas.ahorrado(m) for m in normales)
        lineas += ["", f"📊 En total: {euros(llevas)} de {euros(objetivo)} ({pct(llevas / objetivo if objetivo else 1)})"]
    necesario = necesario_metas()
    ahorro_medio, _, origen = ahorro_mensual()
    if necesario:
        lineas.append(f"🧮 Para llegar a tiempo a todas necesitas apartar <b>{euros(necesario)}/mes</b>")
        if ahorro_medio is not None:
            diferencia = ahorro_medio - necesario
            if diferencia >= 0:
                lineas.append(f"🟢 Ahorras ~{euros_cortos(round(ahorro_medio))}/mes ({origen}): te sobran "
                              f"{euros_cortos(round(diferencia))}/mes")
            else:
                lineas.append(f"🔴 Ahorras ~{euros_cortos(round(ahorro_medio))}/mes ({origen}): te faltan "
                              f"{euros_cortos(round(-diferencia))}/mes. Retrasa alguna fecha o baja algún objetivo.")
    hechas = metas.completadas()
    if hechas:
        lineas.append(f"🏆 Metas conseguidas: {len(hechas)}")
    lineas += ["", "💡 <i>Qué significa: «necesitas» es lo justo para llegar a la fecha; «ritmo real» es lo que de verdad "
                   "has ido apartando. Si el ritmo real es menor, la fecha estimada se retrasa.</i>"]
    imagen = graficos.progreso(filas, "Progreso de tus metas", lambda f, x: f"{x * 100:.0f} % · "
                               f"{graficos.euros_enteros(f[1])} de {graficos.euros_enteros(f[2])}")
    return "\n".join(lineas), [imagen]


# ---------- 🩺 Salud financiera ----------

def puntos_entre(valor, cero, cien):
    """0 puntos en `cero`, 100 en `cien`, lineal entre medias."""
    if cien == cero:
        return 100.0
    return max(0.0, min(100.0, (valor - cero) / (cien - cero) * 100))


def salud():
    """{"total", "componentes": [(clave, puntos, detalle, consejo)], "sin_datos": [claves]}."""
    componentes, sin_datos = [], []
    lista = historial(6)
    completos = cerrados(lista, 3)
    # 🐷 Ahorro: % de lo que entra que te sobra (20 % o más = 100 puntos)
    entradas = sum(r["ingresos"] for r in completos)
    tasa = sum(r["balance"] for r in completos) / entradas if entradas else None
    if tasa is None:
        c = analisis.datos_ciclo()
        if c["transcurridos"] >= 7 and c["ingresos"] > 0:
            tasa = (c["ingresos"] - c["proyeccion"]) / c["ingresos"]
            entradas = c["ingresos"]
    if tasa is not None:
        extra = max(0.0, TASA_IDEAL - tasa) * (entradas / max(1, len(completos)))
        componentes.append(("ahorro", puntos_entre(tasa, 0.0, TASA_IDEAL),
                            f"ahorras el {pct(tasa)} de lo que entra (ideal: 20 % o más)",
                            f"Apartar ~{euros_cortos(round(extra))} más al mes te llevaría al 20 %." if extra > 1 else ""))
    else:
        sin_datos.append("ahorro")
    # 💳 Endeudamiento: % del salario en cuotas, gastos fijos y suscripciones (≤ 30 % = 100, ≥ 50 % = 0)
    salario = analisis_deudas.salario_reciente()
    plazos, fijos, subs = analisis_deudas.compromiso_mensual()
    if salario:
        fraccion = (plazos + fijos + subs) / salario
        componentes.append(("endeudamiento", puntos_entre(fraccion, 0.50, 0.30),
                            f"comprometes el {pct(fraccion)} del salario cada mes (ideal: menos del 30 %)",
                            "Terminar la deuda más pequeña o quitar una suscripción baja este porcentaje."))
    else:
        sin_datos.append("endeudamiento")
    # 🛟 Colchón: solo si está activado
    s = analisis.saldo_actual()
    if colchon.activo() and s:
        cubiertos = colchon.meses_cubiertos(s["total"]) or 0.0
        objetivo = colchon.meses_objetivo()
        componentes.append(("colchon", puntos_entre(cubiertos, 0, objetivo),
                            f"tu colchón cubre {str(cubiertos).replace('.', ',')} de {objetivo} meses de gastos",
                            "Sigue con las aportaciones al colchón cada cobro."))
    else:
        sin_datos.append("colchon")
    # 🎯 Presupuesto: gastar lo que te propusiste (pasarte un 25 % = 0 puntos)
    presupuesto = config.importe("PRESUPUESTO_CICLO")
    if presupuesto:
        usos = [r["gastos"] / presupuesto for r in completos]
        if not usos:
            c = analisis.datos_ciclo()
            if c["transcurridos"] >= 7 and c["con_movimientos"]:
                usos = [c["proyeccion"] / presupuesto]
        if usos:
            uso = sum(usos) / len(usos)
            componentes.append(("presupuesto", puntos_entre(uso, 1.25, 1.0),
                                f"gastas el {pct(uso)} de tu presupuesto de {euros_cortos(presupuesto)}",
                                "Revisa 💧 Flujo de caja: el gasto variable es el más fácil de recortar."))
        else:
            sin_datos.append("presupuesto")
    else:
        sin_datos.append("presupuesto")
    # ⏰ Puntualidad: pagos hechos a tiempo
    tuyos = analisis_deudas.puntualidad("debo")
    total_p = sum(sum(v) for v in tuyos.values())
    if total_p:
        a_tiempo = sum(v[0] for v in tuyos.values())
        componentes.append(("puntualidad", a_tiempo / total_p * 100,
                            f"pagas a tiempo el {pct(a_tiempo / total_p)} de tus pagos ({a_tiempo} de {total_p})",
                            "Confirma los pagos el mismo día del recordatorio para no acumular atrasos."))
    else:
        sin_datos.append("puntualidad")
    # 🏁 Metas: cómo vas con tus metas (🟢 100 · 🟡 60 · 🔴 20)
    normales = [m for m in metas.activas() if not m["especial"]]
    if normales:
        valores = []
        for m in normales:
            estado = metas.progreso(m)["estado"]
            valores.append(100 if estado[0] in "✅🟢" else (60 if estado[0] == "🟡" else 20))
        tarde = sum(1 for v in valores if v < 100)
        componentes.append(("metas", sum(valores) / len(valores),
                            f"{len(normales) - tarde} de {len(normales)} metas van al día",
                            "Pulsa «✅ Ya lo moví» cuando apartes el dinero de cada meta." if tarde else ""))
    else:
        sin_datos.append("metas")
    peso = sum(PESOS[c[0]] for c in componentes)
    total = round(sum(PESOS[c[0]] * c[1] for c in componentes) / peso) if peso else None
    return {"total": total, "componentes": componentes, "sin_datos": sin_datos}


def banda(total):
    return "🟢" if total >= 80 else ("🟡" if total >= 50 else "🔴")


def pantalla_salud():
    h = salud()
    if h["total"] is None:
        return ("🩺 <b>Salud financiera</b>\n\nAún no hay datos suficientes para calcular tu índice. "
                "Registra tu cobro y espera unos días de movimientos.", [])
    total = h["total"]
    texto_banda = "bien" if total >= 80 else ("mejorable" if total >= 50 else "hay que actuar")
    lineas = [f"🩺 <b>Índice de salud financiera: {total}/100</b> {banda(total)} ({texto_banda})", "",
              "Es una nota de 0 a 100, como la de un examen, que junta en un número cómo vas en:", ""]
    for clave, puntos, detalle, _ in h["componentes"]:
        lineas.append(f"{banda(puntos)} {NOMBRES[clave]} <b>{round(puntos)}</b>/100 · {detalle}")
    if h["sin_datos"]:
        motivos = {"colchon": "desactivado", "presupuesto": "sin presupuesto o sin datos",
                   "puntualidad": "aún sin pagos registrados", "metas": "sin metas",
                   "ahorro": "aún sin datos", "endeudamiento": "falta registrar el salario"}
        lineas.append("<i>No cuentan: " + ", ".join(f"{NOMBRES[c].split(' ', 1)[1].lower()} ({motivos[c]})"
                                                   for c in h["sin_datos"]) + ".</i>")
    mejoras = sorted((c for c in h["componentes"] if c[1] < 90 and c[3]), key=lambda c: -PESOS[c[0]] * (100 - c[1]))[:2]
    if mejoras:
        lineas += ["", "📈 <b>Lo que más subiría tu nota</b>"]
        lineas += [f"• {NOMBRES[c[0]]}: {c[3]}" for c in mejoras]
    s = analisis.saldo_actual()
    if s:
        cubiertos = colchon.meses_cubiertos(s["total"])
        if cubiertos is not None:
            que = "Tu colchón" if colchon.activo() else "Tu dinero libre"
            lineas.append(f"\n🛟 {que} cubriría {str(cubiertos).replace('.', ',')} meses de gastos"
                          + ("" if colchon.activo() else " (el colchón está desactivado: actívalo en ⚙️ Ajustes cuando quieras)"))
    pesos = " · ".join(f"{NOMBRES[c].split(' ', 1)[1].lower()} {p}" for c, p in PESOS.items())
    lineas += ["", f"💡 <i>Qué significa: 🟢 80–100 vas bien, 🟡 50–79 mejorable, 🔴 menos de 50 hay que actuar. "
                   f"Cada apartado pesa distinto ({pesos}) y solo cuenta lo que tiene datos.</i>"]
    filas = [(NOMBRES[c[0]], c[1], 100) for c in h["componentes"]]
    imagen = graficos.progreso(filas, f"Índice de salud financiera: {total}/100", lambda f, x: f"{round(f[1])} / 100")
    return "\n".join(lineas), [imagen]


# ---------- 🔮 Trayectoria ----------

def trayectoria():
    ahorro_medio, ingreso_medio, origen = ahorro_mensual()
    pat, saldo, deben, debes = patrimonio()
    if ahorro_medio is None:
        return ("🔮 <b>Trayectoria</b>\n\nNecesito al menos una semana de datos de este ciclo (o un ciclo completo) "
                "para calcular tu ritmo de ahorro.", [])
    d = hoy()
    deuda = dict(analisis_deudas.proyeccion(13))
    escenarios = [("A tu ritmo", ahorro_medio),
                  ("+10 % de ahorro", ahorro_medio + 0.10 * (ingreso_medio or 0)),
                  ("+100 €/mes", ahorro_medio + 100)]
    fechas = [d] + [sumar_meses(date(d.year, d.month, 1), m, 1) for m in range(1, 13)]
    pendiente = [debes] + [deuda.get(date(f.year, f.month, 1), 0.0) if deuda else 0.0 for f in fechas[1:]]
    # La deuda solo baja si pagas; tu ahorro medio ya incluye esas cuotas pagadas.
    series = []
    for nombre, mensual in escenarios:
        valores = [round(saldo + deben + mensual * m - pendiente[m], 2) for m in range(13)]
        series.append((nombre, valores))
    lineas = ["🔮 <b>Tu trayectoria</b>", "",
              f"🏦 Patrimonio neto hoy: <b>{euros(pat)}</b>",
              f"🐷 Ahorras ~<b>{euros_cortos(round(ahorro_medio))}/mes</b> ({origen})", ""]
    for nombre, valores in series:
        lineas.append(f"• {nombre}: en 6 meses <b>{euros_cortos(round(valores[6]))}</b> · en 1 año "
                      f"<b>{euros_cortos(round(valores[12]))}</b>")
    if debes:
        libre = [f for f, v in analisis_deudas.proyeccion(36) if v <= 0.004]
        if libre:
            lineas.append(f"\n💳 Sin deudas en {MESES[libre[0].month - 1]} {libre[0].year} si pagas tus cuotas")
    necesario = necesario_metas()
    if necesario:
        lineas.append(f"🎯 Tus metas necesitan {euros_cortos(round(necesario))}/mes"
                      + (f": te sobran {euros_cortos(round(ahorro_medio - necesario))}" if ahorro_medio >= necesario
                         else f": te faltan {euros_cortos(round(necesario - ahorro_medio))}"))
    actual = series[0][1]
    for objetivo in (1000, 2000, 5000, 10000, 20000, 50000):
        if pat >= objetivo:
            continue
        meses = next((m for m, v in enumerate(actual) if v >= objetivo), None)
        if meses is None and ahorro_medio > 0:
            meses = 12 + math.ceil((objetivo - actual[12]) / ahorro_medio)
        if meses is not None:
            llega = sumar_meses(d, meses, 1)
            lineas.append(f"🏁 Llegarías a {euros_cortos(objetivo)} de patrimonio en {meses} meses "
                          f"({MESES[llega.month - 1]} {llega.year})")
        break
    if ahorro_medio <= 0:
        lineas.append("🔴 Ahora mismo gastas más de lo que entra: tu patrimonio baja cada mes.")
    lineas += ["", "💡 <i>Qué significa: es una previsión, no una promesa. Si sigues ahorrando como hasta ahora, "
                   "esto es lo que tendrías (lo que tienes + te deben − debes). Las otras líneas muestran qué pasaría "
                   "si ahorraras un poco más.</i>"]
    return "\n".join(lineas), [graficos.lineas(fechas, series, "Patrimonio neto previsto (12 meses)")]


# ---------- Entrada ----------

def texto_menu():
    h = salud()
    pat = patrimonio()[0]
    lineas = ["🧭 <b>Análisis completo</b>", "Todo junto: saldo, deudas, metas y gastos, por ciclos de cobro.", ""]
    lineas.append(f"🏦 Patrimonio neto: <b>{euros(pat)}</b>")
    libre = dinero_libre()
    if libre is not None:
        lineas.append(f"💶 Dinero libre: <b>{euros(libre)}</b>")
    if h["total"] is not None:
        lineas.append(f"🩺 Salud financiera: <b>{h['total']}/100</b> {banda(h['total'])}")
    lineas += ["", "Elige qué quieres ver (cada pantalla trae su gráfico y lo explica):"]
    return "\n".join(lineas)


def pantalla(nombre, arg=0):
    """(texto HTML, [PNG]) de una pantalla del análisis completo."""
    if nombre == "ahora":
        return ahora()
    if nombre == "meses":
        return por_meses()
    if nombre == "anual":
        return anual()
    if nombre == "flujo":
        return flujo(int(arg or 0))
    if nombre == "metas":
        return pantalla_metas()
    if nombre == "salud":
        return pantalla_salud()
    if nombre == "tray":
        return trayectoria()
    return texto_menu(), []
