# Finanzas personales — Bot de Telegram

Bot de Telegram para llevar tus finanzas con N26 (3 cuentas), con conexión bancaria de solo
lectura vía Enable Banking (PSD2/AIS). Solo te habla a ti.

**El banco se consulta una vez al día** (00:00 por defecto, en silencio, sin notificaciones):
saldos y movimientos de todas tus cuentas. Todo lo demás se calcula al momento con esos datos,
así que pulsar botones nunca gasta consultas. Tu saldo es la suma de tus cuentas.

| Botón | Qué hace |
|---|---|
| 💰 **Saldo** | Total y desglose por cuenta, **saldo neto** (saldo − lo que te toca pagar este ciclo; de las deudas a plazos solo la cuota) y cuánto puedes gastar al día hasta el cobro. Registrar cobro. Últimos movimientos. |
| 📊 **Análisis** | Ciclo actual (ingresos, gasto, proyección, tasa de ahorro, comparación), presupuesto con semáforo, categorías (gráfico), evolución del saldo (gráfico), semana, suscripciones detectadas (apúntalas con un toque) y corregir categorías. |
| 💳 **Deudas** | **Lo que debes** (pago único con fecha, pago único al cobrar, a plazos, gasto fijo, suscripción) y **lo que te deben** (con día de pago, a plazos o sin fecha). A plazos: pones el **total** y la cuota (o el nº de cuotas) y lo ya pagado; cada cuota un día fijo, **al cobrar** o (si te deben) sin día fijo. «Otra cantidad» recalcula las cuotas. Si una cuota no se paga: pasarla al mes siguiente o pagar las dos juntas (nunca cuenta como pagada). Recordatorios entre las 08:00 y las 14:00 que piden confirmación y se repiten hasta que la des. Lo que te deben no se suma al saldo neto. **Análisis de deudas** con % del salario comprometido, libre de deudas en…, calendario, puntualidad y gráfico. |
| 🎯 **Metas** | Metas de ahorro con barra de progreso, cuánto ahorrar al mes y si vas bien. Manuales o vinculadas a una cuenta (p. ej. un Espacio). |
| ⏰ **Recordatorios** | El del cobro insiste hasta que registres el salario (y propone la nómina si la ve en el banco). Recordatorios propios: una vez, diario, semanal o mensual. |
| ⚙️ **Ajustes** | Límite de consultas, hora de actualización, días de cobro, presupuesto, aviso de saldo bajo, avisos on/off, «Actualizar ahora», exportar a Excel. |

El «mes» del presupuesto es el **ciclo de cobro**: empieza el día en que cobras y dura hasta el
siguiente cobro (por defecto se espera entre el día 3 y el 7).

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
| `deudas.py`, `metas.py`, `ciclo.py`, `movimientos.py` | Lógica de deudas, metas, ciclo de cobro y gastos |
| `bot_deudas.py`, `analisis_deudas.py` | Interfaz y análisis de deudas |
| `avisos.py` | Recordatorios y avisos (nunca a las 00:00) |
| `datos.py`, `exportar.py` | Base de datos local, copias y Excel |
| `autenticacion.py`, `configurar.py`, `banco.py`, `consultas.py`, `contador.py` | N26, configuración y límite de consultas |
| `config.py`, `consola.py`, `formato.py` | Utilidades |

- [Política de privacidad](PRIVACIDAD.md)
- [Términos de uso](TERMINOS.md)
