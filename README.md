# Finanzas personales — Bot de Telegram

Bot de Telegram para llevar la contabilidad personal, con conexión bancaria de solo lectura
vía Enable Banking (PSD2/AIS).

**Ahora mismo hace una sola cosa:** cada día a las 00:00 consulta el saldo de tu cuenta N26
(una única petición al banco al día) y te lo envía por Telegram. Solo te habla a ti.
Si a las 00:00 el ordenador estaba apagado o sin internet, te lo envía en cuanto vuelve.

## Instalación en Windows (un clic)

1. Descarga [INSTALAR.bat](https://github.com/Claus29/Finanzas-personales/raw/refs/heads/claude/sweet-thompson-41bsdc/INSTALAR.bat)
   y ábrelo con doble clic. Si Windows avisa ("Windows protegió su PC"), pulsa
   **Más información → Ejecutar de todas formas**.
2. El instalador:
   - instala Python si no lo tienes,
   - descarga el bot en `%LOCALAPPDATA%\FinanzasBot`,
   - te guía para conectar Telegram, tu clave `.pem` de Enable Banking y N26,
   - deja el bot funcionando en la ventana **Bot Finanzas**, que se abre sola al encender el PC
     (no la cierres; puedes minimizarla),
   - crea en el escritorio **Bot Finanzas** (vuelve a abrir la ventana), **Bot Finanzas - Actualizar**
     y **Bot Finanzas - Reconectar banco**.

Necesitas tener a mano: Telegram abierto y el archivo `.pem` de Enable Banking.

### Actualizar

Doble clic en **Bot Finanzas - Actualizar** (escritorio). Descarga la última versión de GitHub,
la instala y reinicia el bot. Tu configuración, tu clave y la conexión con el banco se conservan.

### Cuando caduque el permiso del banco (máximo 6 meses)

El propio mensaje diario te avisa 15 días antes. Doble clic en **Bot Finanzas - Reconectar banco**.

## Archivos

| Archivo | Qué hace |
|---|---|
| `INSTALAR.bat` | Instala, configura y arranca todo (también sirve para reparar) |
| `BOT.bat` | Ventana donde funciona el bot (se reinicia solo si se detiene) |
| `ACTUALIZAR.bat` | Descarga la última versión y la instala |
| `RECONECTAR_BANCO.bat` | Vuelve a autorizar el acceso a N26 |
| `bot.py` | Bot de Telegram con el envío diario del saldo |
| `saldo.py` | Consulta del saldo y control de "una vez al día" |
| `banco.py` | Cliente de la API de Enable Banking |
| `configurar.py` | Asistente de configuración |
| `accesos_directos.ps1` | Arranque automático y accesos directos del escritorio |

El registro del bot está en `%LOCALAPPDATA%\FinanzasBot\bot.log`.

- [Política de privacidad](PRIVACIDAD.md)
- [Términos de uso](TERMINOS.md)
