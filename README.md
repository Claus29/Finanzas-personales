# Finanzas personales — Bot de Telegram

Bot de Telegram para llevar tus finanzas con N26 (3 cuentas), con conexión bancaria de solo
lectura vía Enable Banking (PSD2/AIS). Solo te habla a ti.

**El banco se consulta una vez al día** (00:00 por defecto, en silencio, sin notificaciones):
saldos y movimientos de todas tus cuentas. Todo lo demás se calcula al momento con esos datos,
así que pulsar botones nunca gasta consultas. Tu saldo es la suma de tus cuentas.

Tu dinero, siempre en el mismo orden: **1️⃣ pagos** (deudas, cuotas, gastos fijos y suscripciones: no se mueven)
→ **2️⃣ tu libre** (la cantidad que eliges) → **3️⃣ metas** (solo lo que sobra). Si a mitad de mes falta dinero,
las metas ceden primero.

| Botón | Qué hace |
|---|---|
| 🏠 **Inicio** | Lo esencial de hoy: lo que hay en el banco, los pagos de antes del cobro (✅ ya pagado / 💶 con el cobro), lo guardado en tus metas y **tu libre** hasta el cobro (y cuánto sería si te pagan lo que te deben). |
| 💳 **Deudas** | **Cuánto debes en total** y cuándo terminas, qué pagas antes del cobro y qué con el cobro, cada deuda en una línea, los gastos fijos aparte y lo que te deben. Apuntar (pago único, al cobrar, a plazos, gasto fijo, suscripción; o lo que te deben), marcar pagado, «💶 con el cobro» (todo el plan se mueve), cambiar entre día fijo y «en cuanto cobro». Ficha corta de cada deuda y «📊 Detalles» con todo lo de antes. Recordatorios entre las 08:00 y las 14:00 que piden confirmación. |
| 🎯 **Metas** | En orden de prioridad: cuánto llevas, **cuándo llegas** (con lo que sobra de cada cobro) y qué mover este ciclo y a qué cuenta. El bot nunca mueve dinero: te lo recuerda hasta que lo confirmes. |
| 📈 **Próximos meses** | Una tabla cobro a cobro (entra, deudas, fijos, tu libre, metas), la conclusión (🟢 cuadra / 🟡 / 🔴 no llega), cuándo terminas las deudas y cuándo llega cada meta. Lo que te deben va aparte. Soluciones si no cuadra y la proyección detallada de antes en «📊 Más detalles». |
| 📊 **Gráfico** | En cada pantalla, bajo demanda: gráficos detallados en tema oscuro (cascada de tu dinero hasta el cobro, pagos, deudas deuda a deuda, pagos por cobro, metas y su evolución, reparto de cada cobro y deuda frente a metas), con fuente y supuestos. |
| ☰ **Más** | Recordatorios, Ajustes, Registrar cobro, Movimientos, Exportar a Excel, Actualizar ahora y **📊 Más datos**: todo lo avanzado (saldo por cuenta y saldo neto, 🧭 análisis completo con índice de salud, ciclo, presupuesto, categorías, evolución, proyección detallada con propuestas y análisis de deudas). |

El «mes» del presupuesto es el **ciclo de cobro**: empieza el día en que cobras y dura hasta el
siguiente cobro (por defecto se espera entre el día 3 y el 7). Al registrar el cobro llega el
**plan en tres pasos**: 1️⃣ pagos, 2️⃣ tu libre y 3️⃣ lo que mover a cada meta (y «📋 Plan detallado»).

## Instalación en Windows (un clic)

1. Descarga [INSTALAR.bat](https://github.com/Claus29/Finanzas-personales/raw/refs/heads/claude/sweet-thompson-41bsdc/INSTALAR.bat)
   y ábrelo con doble clic. Si Windows avisa, pulsa **Más información → Ejecutar de todas formas**.
2. Todo ocurre en esa ventana: instala Python si hace falta, descarga el bot, te guía (Telegram,
   clave `.pem`, N26) y la ventana pasa a ser la del bot.

En el escritorio: **Bot Finanzas** (abre la ventana o la trae al frente; nunca dos) y
**Bot Finanzas - Actualizar** (actualiza y arranca el bot en la misma ventana, conservando tu
configuración, tu permiso de N26 y tus datos).

Si el permiso de N26 caduca, el bot sigue funcionando con los últimos datos y la ventana te guía
para renovarlo. **No pulses "Unlink" en Enable Banking.**

## Tus datos

Todo queda en `%LOCALAPPDATA%\FinanzasBot`: `datos.db` (saldos, movimientos, cobros, deudas, metas,
recordatorios), con una copia de seguridad diaria en `copias\` (14 días), y el registro en `bot.log`.

## Archivos

| Archivo | Qué hace |
|---|---|
| `INSTALAR.bat` / `ACTUALIZAR.bat` / `BOT.bat` | Instalar o actualizar en una sola ventana; ventana del bot |
| `principal.py`, `lanzador.py`, `instancia.py` | Un solo bot y una sola ventana |
| `bot.py` | Telegram: botones, menús, pasos guiados y tareas programadas |
| `actualizacion.py` | La única consulta diaria al banco (saldos y movimientos) |
| `analisis.py`, `graficos.py` | Métricas y gráficos |
| `analisis_completo.py` | Análisis completo: 7 pantallas e índice de salud financiera |
| `deudas.py`, `metas.py`, `ciclo.py`, `movimientos.py` | Lógica de deudas, metas, ciclo de cobro y gastos |
| `bot_deudas.py`, `analisis_deudas.py` | Interfaz y análisis de deudas |
| `bot_metas.py`, `colchon.py` | Interfaz de metas y colchón de emergencia |
| `reparto.py` | Reparto automático: tu libre fijo y todo lo que sobra a tus metas |
| `resumen.py`, `vistas.py`, `graficos_resumen.py` | Pantallas sencillas (v13): el cálculo único (pagos → libre → metas), sus textos y sus gráficos |
| `proyeccion.py`, `bot_proyeccion.py`, `graficos_oscuro.py` | Proyección cobro a cobro, su interfaz y sus gráficos (tema oscuro) |
| `avisos.py` | Recordatorios y avisos (nunca a las 00:00) |
| `datos.py`, `exportar.py` | Base de datos local, copias y Excel |
| `autenticacion.py`, `configurar.py`, `banco.py`, `consultas.py`, `contador.py` | N26, configuración y límite de consultas |
| `config.py`, `consola.py`, `formato.py` | Utilidades |

- [Política de privacidad](PRIVACIDAD.md)
- [Términos de uso](TERMINOS.md)
