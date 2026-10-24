# Crea el arranque automatico del bot con Windows (ventana BOT.bat) y los accesos directos del escritorio.
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

Nuevo-Acceso (Join-Path $inicio 'Bot Finanzas.lnk') (Join-Path $dir 'BOT.bat') '' 'Bot Finanzas (se abre al iniciar Windows)'
Nuevo-Acceso (Join-Path $escritorio 'Bot Finanzas.lnk') (Join-Path $dir 'BOT.bat') '' 'Abre la ventana del bot'
Nuevo-Acceso (Join-Path $escritorio 'Bot Finanzas - Actualizar.lnk') (Join-Path $dir 'ACTUALIZAR.bat') '' 'Descarga e instala la ultima version del bot'
Nuevo-Acceso (Join-Path $escritorio 'Bot Finanzas - Reconectar banco.lnk') (Join-Path $dir 'RECONECTAR_BANCO.bat') '' 'Vuelve a autorizar el acceso a N26'
Nuevo-Acceso (Join-Path $escritorio 'Bot Finanzas - Diagnostico.lnk') (Join-Path $dir 'DIAGNOSTICO.bat') '' 'Muestra todo lo que devuelve el banco de cada cuenta'
