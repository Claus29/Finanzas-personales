"""Acceso directo «Bot Finanzas» y arranque con Windows (se ejecuta con pythonw, sin ventana).

Si el bot ya está funcionando, trae su ventana al frente; si no, abre la ventana del bot.
Así nunca hay dos ventanas del bot.
"""
import subprocess

import instancia
from config import BASE

if instancia.en_marcha():
    instancia.traer_al_frente()
else:
    subprocess.Popen(["cmd.exe", "/c", str(BASE / "BOT.bat")], cwd=BASE,
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
