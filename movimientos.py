"""Movimientos del banco: importación, categorías, transferencias internas, nómina y suscripciones.

Los movimientos se descargan una vez al día (con la actualización de las 00:00) y todo lo demás
se calcula aquí sobre lo guardado, sin volver a preguntar al banco.
"""
import hashlib
import re
import unicodedata
from collections import defaultdict
from datetime import date, timedelta

import config
import datos

# Categorías de gasto (en este orden se muestran cuando hay empate).
CATEGORIAS = {
    "supermercado": "🛒 Supermercado",
    "comida": "🍔 Comida fuera",
    "transporte": "🚗 Transporte",
    "hogar": "🏠 Hogar y facturas",
    "suscripciones": "📺 Suscripciones",
    "compras": "🛍️ Compras",
    "salud": "💊 Salud",
    "ocio": "🎉 Ocio",
    "viajes": "✈️ Viajes",
    "transferencias": "💸 Bizum y transferencias",
    "efectivo": "🏧 Efectivo",
    "comisiones": "🏦 Comisiones",
    "otros": "📦 Otros",
}
INGRESO = "ingreso"

# Códigos de comercio (ISO 18245) que envía el banco.
MCC = {
    "supermercado": {5411, 5412, 5422, 5441, 5451, 5462, 5499},
    "comida": {5811, 5812, 5813, 5814},
    "transporte": {4111, 4112, 4121, 4131, 4784, 4789, 5541, 5542, 5983, 7523, 7512, 7538, 7542},
    "hogar": {4814, 4899, 4900, 5200, 5211, 5251, 5712, 5722},
    "suscripciones": {5815, 5816, 5817, 5818, 4816},
    "salud": {5912, 5975, 5976, 8011, 8021, 8031, 8041, 8042, 8043, 8049, 8050, 8062, 8071, 8099},
    "ocio": {5813, 7832, 7922, 7929, 7932, 7933, 7941, 7991, 7992, 7993, 7994, 7996, 7997, 7998, 7999, 5945},
    "viajes": {4411, 4511, 4582, 4722, 7011, 7012},
    "efectivo": {6010, 6011},
    "comisiones": {6012, 6300},
}

PALABRAS = [  # separadas por comas; cada una puede tener varias palabras
    ("supermercado", "mercadona, carrefour, lidl, aldi, alcampo, eroski, supermercado, supermercados dia, "
                     "hipercor, consum, bonpreu, caprabo, condis, ahorramas, gadis, froiz, spar, coviran, masymas"),
    ("comida", "restaurante, bar, cafeteria, cafe, glovo, just eat, justeat, uber eats, ubereats, deliveroo, "
               "mcdonald, mcdonalds, burger king, telepizza, dominos, kfc, starbucks, foster, vips, goiko, "
               "taberna, pizzeria"),
    ("transporte", "uber, cabify, bolt, renfe, metro, emt, alsa, blablacar, repsol, cepsa, galp, petronor, "
                   "gasolinera, estacion de servicio, parking, aparcamiento, peaje, taxi, tmb, ouigo, iryo"),
    ("hogar", "endesa, iberdrola, naturgy, totalenergies, holaluz, movistar, vodafone, orange, digi, masmovil, "
              "yoigo, pepephone, jazztel, lowi, ikea, leroy merlin, alquiler, comunidad de propietarios, "
              "mapfre, mutua"),
    ("suscripciones", "netflix, spotify, hbo, disney plus, disney, prime video, amazon prime, apple.com, icloud, "
                      "youtube premium, google one, google storage, dazn, filmin, chatgpt, openai, "
                      "playstation, xbox"),
    ("compras", "amazon, aliexpress, zara, primark, shein, mango, pull bear, bershka, decathlon, el corte ingles, "
                "mediamarkt, media markt, fnac, pccomponentes, temu, wallapop"),
    ("salud", "farmacia, clinica, dentista, hospital, optica, fisioterapia"),
    ("ocio", "cine, cines, teatro, ticketmaster, entradas, steam, gimnasio, gym, concierto"),
    ("viajes", "ryanair, vueling, iberia, booking.com, booking, airbnb, hotel, easyjet"),
    ("transferencias", "bizum, transferencia, transfer"),
    ("efectivo", "cajero, atm, retirada, reintegro"),
    ("comisiones", "comision"),
]
PALABRAS_NOMINA = ("nomina", "nómina", "salario", "payroll", "sueldo", "haberes")
MINIMO_NOMINA = 300.0


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9. ]", " ", texto)).strip()


def clave_regla(movimiento):
    """Clave con la que se recuerda la categoría que elige el usuario (contraparte o concepto)."""
    base = normalizar(movimiento.get("contraparte")) or normalizar(movimiento.get("descripcion"))
    return re.sub(r"\d+", "", base)[:40].strip()


def categorizar(movimiento, reglas=None):
    if movimiento["importe"] > 0:
        return INGRESO
    reglas = reglas if reglas is not None else {r["clave"]: r["categoria"] for r in datos.todos("SELECT * FROM reglas")}
    clave = clave_regla(movimiento)
    if clave and clave in reglas:
        return reglas[clave]
    try:
        mcc = int(movimiento.get("mcc") or 0)
    except ValueError:
        mcc = 0
    for categoria, codigos in MCC.items():
        if mcc in codigos:
            return categoria
    texto = f" {normalizar(movimiento.get('contraparte'))} {normalizar(movimiento.get('descripcion'))} "
    for categoria, palabras in PALABRAS:
        for palabra in palabras.split(","):
            palabra = normalizar(palabra)
            if palabra and (f" {palabra} " in texto or (len(palabra) > 5 and palabra in texto)):
                return categoria
    if 5200 <= mcc <= 5999:
        return "compras"
    return "otros"


# ---------- Importación ----------

def desde_cuando(uid, hoy, dias_primera_vez=89):
    """Desde qué fecha pedir movimientos: unos días antes del último guardado (por si llegan tarde)."""
    ultima = datos.valor("SELECT MAX(fecha) FROM movimientos WHERE uid = ?", uid)
    if ultima:
        return date.fromisoformat(ultima) - timedelta(days=5)
    return hoy - timedelta(days=dias_primera_vez)


def desde_banco(uid, t):
    """Convierte un movimiento de Enable Banking a nuestro formato (None si está pendiente)."""
    if t.get("status") not in (None, "", "BOOK"):
        return None
    importe = float(t["transaction_amount"]["amount"])
    if t.get("credit_debit_indicator") == "DBIT":
        importe = -abs(importe)
    elif t.get("credit_debit_indicator") == "CRDT":
        importe = abs(importe)
    fecha = t.get("booking_date") or t.get("value_date") or t.get("transaction_date")
    if not fecha:
        return None
    otra = (t.get("creditor") if importe < 0 else t.get("debtor")) or {}
    concepto = t.get("remittance_information") or []
    descripcion = " ".join(concepto) if isinstance(concepto, list) else str(concepto)
    ident = t.get("entry_reference") or t.get("transaction_id")
    if not ident:
        ident = hashlib.sha1(f"{uid}|{fecha}|{importe}|{descripcion}|{otra.get('name')}".encode()).hexdigest()[:20]
    return {
        "id": f"{uid}:{ident}", "uid": uid, "fecha": fecha[:10], "importe": round(importe, 2),
        "moneda": t["transaction_amount"].get("currency", "EUR"), "descripcion": descripcion.strip()[:200],
        "contraparte": (otra.get("name") or "").strip()[:100], "mcc": str(t.get("merchant_category_code") or ""),
    }


def guardar(nuevos):
    """Guarda los movimientos que no estaban; devuelve los nuevos (ya categorizados)."""
    if not nuevos:
        return []
    existentes = {fila["id"] for fila in datos.todos(
        f"SELECT id FROM movimientos WHERE id IN ({','.join('?' * len(nuevos))})", *[m["id"] for m in nuevos])}
    reglas = {r["clave"]: r["categoria"] for r in datos.todos("SELECT * FROM reglas")}
    ahora = config.ahora().isoformat()
    realmente_nuevos = []
    for m in nuevos:
        if m["id"] in existentes:
            continue
        m["categoria"] = categorizar(m, reglas)
        realmente_nuevos.append(m)
        existentes.add(m["id"])
    datos.varios("INSERT OR IGNORE INTO movimientos (id, uid, fecha, importe, moneda, descripcion, contraparte, mcc, "
                 "categoria, interno, importado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                 [(m["id"], m["uid"], m["fecha"], m["importe"], m["moneda"], m["descripcion"], m["contraparte"],
                   m["mcc"], m["categoria"], ahora) for m in realmente_nuevos])
    marcar_internos()
    return realmente_nuevos


def marcar_internos():
    """Una salida de una cuenta tuya y una entrada del mismo importe en otra tuya (±1 día) son un traspaso."""
    candidatos = datos.todos("SELECT id, uid, fecha, importe FROM movimientos WHERE interno = 0 AND fecha >= ?",
                             (config.ahora().date() - timedelta(days=120)).isoformat())
    entradas = defaultdict(list)
    for m in candidatos:
        if m["importe"] > 0:
            entradas[round(m["importe"], 2)].append(m)
    internos = []
    usados = set()
    for salida in (m for m in candidatos if m["importe"] < 0):
        for entrada in entradas.get(round(-salida["importe"], 2), []):
            if entrada["id"] in usados or entrada["uid"] == salida["uid"]:
                continue
            if abs((date.fromisoformat(entrada["fecha"]) - date.fromisoformat(salida["fecha"])).days) <= 1:
                usados.update((entrada["id"], salida["id"]))
                internos += [entrada["id"], salida["id"]]
                break
    if internos:
        datos.varios("UPDATE movimientos SET interno = 1 WHERE id = ?", [(i,) for i in internos])


def cambiar_categoria(movimiento_id, categoria):
    """Guarda la categoría elegida como regla y la aplica a todos los movimientos parecidos."""
    m = datos.uno("SELECT * FROM movimientos WHERE id = ?", movimiento_id)
    if not m:
        return 0
    clave = clave_regla(m)
    if clave:
        datos.ejecutar("INSERT OR REPLACE INTO reglas (clave, categoria) VALUES (?, ?)", clave, categoria)
    cambiados = [x["id"] for x in datos.todos("SELECT * FROM movimientos WHERE importe < 0")
                 if x["id"] == movimiento_id or (clave and clave_regla(x) == clave)]
    datos.varios("UPDATE movimientos SET categoria = ? WHERE id = ?", [(categoria, i) for i in cambiados])
    return len(cambiados)


# ---------- Consultas para el análisis ----------

def hay_movimientos():
    return datos.valor("SELECT COUNT(*) FROM movimientos") > 0


def entre(desde, hasta):
    """Movimientos (sin traspasos internos) con desde <= fecha < hasta."""
    return datos.todos("SELECT * FROM movimientos WHERE interno = 0 AND fecha >= ? AND fecha < ? ORDER BY fecha",
                       desde.isoformat(), hasta.isoformat())


def gastos_e_ingresos(desde, hasta):
    gastos = ingresos = 0.0
    for m in entre(desde, hasta):
        if m["importe"] < 0:
            gastos += -m["importe"]
        else:
            ingresos += m["importe"]
    return round(gastos, 2), round(ingresos, 2)


def por_categoria(desde, hasta):
    """[(categoría, total gastado)] de mayor a menor."""
    totales = defaultdict(float)
    for m in entre(desde, hasta):
        if m["importe"] < 0:
            totales[m["categoria"] or "otros"] += -m["importe"]
    orden = list(CATEGORIAS)
    return sorted(((c, round(t, 2)) for c, t in totales.items()),
                  key=lambda x: (-x[1], orden.index(x[0]) if x[0] in orden else 99))


def ultimos(cantidad=10, solo_gastos=False):
    filtro = "AND importe < 0" if solo_gastos else ""
    return datos.todos(f"SELECT * FROM movimientos WHERE interno = 0 {filtro} ORDER BY fecha DESC, importado DESC "
                       "LIMIT ?", cantidad)


def candidato_nomina(hoy):
    """Un ingreso que parece la nómina del mes y que aún no se ha registrado como cobro."""
    desde_dia, hasta_dia = config.dias_cobro()
    inicio = date(hoy.year, hoy.month, 1) - timedelta(days=3)
    registrados = {i["movimiento_id"] for i in datos.todos("SELECT movimiento_id FROM ingresos WHERE movimiento_id IS NOT NULL")}
    descartados = {d["clave"][len("nomina_no:"):] for d in datos.todos("SELECT clave FROM enviados WHERE clave LIKE 'nomina_no:%'")}
    anterior = datos.uno("SELECT m.contraparte FROM ingresos i JOIN movimientos m ON m.id = i.movimiento_id "
                         "WHERE i.tipo = 'salario' ORDER BY i.fecha DESC LIMIT 1")
    for m in reversed(entre(inicio, hoy + timedelta(days=1))):
        if m["importe"] < MINIMO_NOMINA or m["id"] in registrados or m["id"] in descartados:
            continue
        texto = normalizar(f"{m['descripcion']} {m['contraparte']}")
        misma_empresa = anterior and anterior["contraparte"] and anterior["contraparte"] == m["contraparte"]
        dia = date.fromisoformat(m["fecha"]).day
        if any(p in texto for p in PALABRAS_NOMINA) or misma_empresa or desde_dia - 3 <= dia <= hasta_dia + 3:
            return m
    return None


def suscripciones(hoy, meses=3):
    """Cargos que se repiten cada mes (mismo comercio, importe parecido) en los últimos meses."""
    desde = hoy - timedelta(days=31 * meses + 5)
    grupos = defaultdict(list)
    for m in entre(desde, hoy + timedelta(days=1)):
        if m["importe"] < 0:
            grupos[clave_regla(m)].append(m)
    encontradas = []
    for clave, lista in grupos.items():
        meses_distintos = {m["fecha"][:7] for m in lista}
        if not clave or len(meses_distintos) < 2:
            continue
        importes = [-m["importe"] for m in lista]
        media = sum(importes) / len(importes)
        if media > 0 and all(abs(x - media) <= max(2.0, media * 0.15) for x in importes):
            ultimo = max(lista, key=lambda m: m["fecha"])
            encontradas.append({"nombre": ultimo["contraparte"] or ultimo["descripcion"] or clave,
                                "importe": round(media, 2), "veces": len(meses_distintos), "ultimo": ultimo["fecha"]})
    return sorted(encontradas, key=lambda s: -s["importe"])


def umbral_gasto_grande():
    """Un gasto es «grande» si es al menos 4 veces la mediana de tus gastos (y como mínimo 150 €)."""
    hoy = config.ahora().date()
    importes = sorted(-m["importe"] for m in datos.todos(
        "SELECT importe FROM movimientos WHERE interno = 0 AND importe < 0 AND fecha >= ?",
        (hoy - timedelta(days=90)).isoformat()))
    mediana = importes[len(importes) // 2] if importes else 0
    return max(150.0, mediana * 4)


def gastos_grandes(lista, excluir=()):
    """De `lista`, los gastos recientes (4 días) muy por encima de lo normal, sin los pagos ya apuntados."""
    hoy = config.ahora().date()
    umbral = umbral_gasto_grande()
    return [m for m in lista if m["importe"] <= -umbral and m["id"] not in excluir
            and m["fecha"] >= (hoy - timedelta(days=4)).isoformat()]
