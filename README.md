# Finanzas personales — Bot de Telegram

Bot de Telegram para consultar el saldo de N26, con conexión bancaria de solo lectura vía
Enable Banking (PSD2/AIS). Solo te habla a ti.

- **💰 Ver saldo**: tu saldo cuando quieras, con el nombre de cada cuenta.
- **⚙️ Ajustes**: límite de consultas al día (4 por defecto), hora del saldo automático
  (00:00 por defecto) y activarlo o desactivarlo.
- **Contador**: cada respuesta dice cuántas consultas llevas hoy. Al llegar al límite no se
  pregunta al banco y se muestra el último saldo conocido. Pulsar varias veces seguidas
  (10 minutos) repite el último saldo sin gastar consulta.
- **Saldo automático** a la hora elegida; si el PC estaba apagado, en cuanto vuelve.

## Instalación en Windows (un clic)

1. Descarga [INSTALAR.bat](https://github.com/Claus29/Finanzas-personales/raw/refs/heads/claude/sweet-thompson-41bsdc/INSTALAR.bat)
   y ábrelo con doble clic. Si Windows avisa ("Windows protegió su PC"), pulsa
   **Más información → Ejecutar de todas formas**.
2. Todo ocurre en esa misma ventana: instala Python si hace falta, descarga el bot, te guía
   (Telegram, clave `.pem` de Enable Banking y autenticación con N26) y la ventana pasa a ser
   la del bot.

En el escritorio quedan **Bot Finanzas** (abre la ventana del bot o la trae al frente si ya está
abierta; nunca abre dos) y **Bot Finanzas - Actualizar**.

### Actualizar

Doble clic en **Bot Finanzas - Actualizar**: descarga la última versión, cierra el bot, la instala
y esa misma ventana pasa a ser la del bot. Se conservan la configuración, la clave y la conexión.

### Permiso de N26

La primera vez y cada vez que el permiso caduca o se desvincula, la ventana del bot te guía para
renovarlo (y Telegram te avisa). La dirección de vuelta se detecta sola al copiarla.
**No pulses "Unlink" en Enable Banking**: corta el acceso al momento.

## Archivos

| Archivo | Qué hace |
|---|---|
| `INSTALAR.bat` | Instala, repara y actualiza; al terminar arranca el bot en la misma ventana |
| `ACTUALIZAR.bat` | Descarga el último `INSTALAR.bat` y lo ejecuta en la misma ventana |
| `BOT.bat` | Ventana del bot (lo reinicia si se detiene) |
| `lanzador.py` | Accesos directos: abre la ventana del bot o la trae al frente |
| `principal.py` | Una sola instancia; configuración, autenticación y bot en un mismo proceso |
| `bot.py` | Bot de Telegram: botones, Ajustes y saldo automático |
| `consultas.py` | Consulta del saldo, último saldo conocido y mensajes |
| `contador.py` | Contador diario de consultas al banco |
| `autenticacion.py` | Conexión con N26 a prueba de errores |
| `configurar.py` | Asistente inicial (Telegram y clave de Enable Banking) |
| `banco.py` | Cliente de la API de Enable Banking |
| `config.py`, `consola.py`, `instancia.py` | Configuración, utilidades de la ventana e instancia única |
| `parar_bot.ps1`, `accesos_directos.ps1` | Cerrar el bot antes de actualizar; accesos directos |

El registro detallado está en `%LOCALAPPDATA%\FinanzasBot\bot.log`.

- [Política de privacidad](PRIVACIDAD.md)
- [Términos de uso](TERMINOS.md)
