# Crea el arranque automatico del bot con Windows y los accesos directos del escritorio.
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$shell = New-Object -ComObject WScript.Shell

function Nuevo-Acceso($ruta, $destino, $argumentos, $descripcion) {
    $acceso = $shell.CreateShortcut($ruta)
    $acceso.TargetPath = $destino
    $acceso.Arguments = $argumentos
    $acceso.WorkingDirectory = $dir
    $acceso.Description = $descripcion
    $acceso.Save()
}

$inicio = [Environment]::GetFolderPath('Startup')
$escritorio = [Environment]::GetFolderPath('Desktop')

Nuevo-Acceso (Join-Path $inicio 'Bot Finanzas.lnk') (Join-Path $dir '.venv\Scripts\pythonw.exe') ('"' + (Join-Path $dir 'bot.py') + '"') 'Bot Finanzas (se inicia con Windows)'
Nuevo-Acceso (Join-Path $escritorio 'Bot Finanzas - Actualizar.lnk') (Join-Path $dir 'ACTUALIZAR.bat') '' 'Descarga e instala la ultima version del bot'
Nuevo-Acceso (Join-Path $escritorio 'Bot Finanzas - Reconectar banco.lnk') (Join-Path $dir 'RECONECTAR_BANCO.bat') '' 'Vuelve a autorizar el acceso a N26'
