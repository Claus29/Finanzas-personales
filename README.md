# Finanzas personales — Bot de Telegram

Bot de Telegram para llevar la contabilidad personal, con conexión bancaria de solo lectura
vía Enable Banking (PSD2/AIS).

**Ahora mismo hace una sola cosa:** cada día a las 00:00 consulta el saldo de tu cuenta N26
(una única petición al banco al día) y te lo envía por Telegram. Solo responde a tu chat.

## Puesta en marcha

1. Instala las dependencias (Python 3.10 o superior):
   ```bash
   pip install -r requirements.txt
   ```
2. Copia `.env.example` como `.env` y rellena `TELEGRAM_TOKEN`, `EB_APP_ID` y `EB_KEY_PATH`.
   Copia tu archivo `.pem` de Enable Banking en esta carpeta.
3. Conecta N26 (guarda `EB_SESSION_ID` en el `.env` automáticamente):
   ```bash
   python conectar_banco.py
   ```
4. Arranca el bot, escríbele `/start` en Telegram, copia tu chat ID en `TELEGRAM_CHAT_ID`
   y reinícialo:
   ```bash
   python bot.py
   ```

El bot tiene que estar encendido a las 00:00 para enviar el saldo. Cuando el permiso del
banco esté a punto de caducar (máximo 6 meses), el propio mensaje diario te avisará para que
vuelvas a ejecutar `conectar_banco.py`.

## Archivos

| Archivo | Qué hace |
|---|---|
| `bot.py` | Bot de Telegram con el envío diario del saldo |
| `banco.py` | Cliente de la API de Enable Banking |
| `conectar_banco.py` | Autoriza el acceso a N26 y guarda la sesión |

- [Política de privacidad](PRIVACIDAD.md)
- [Términos de uso](TERMINOS.md)
