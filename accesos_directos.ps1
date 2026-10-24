# Crea el arranque con Windows y los accesos directos del escritorio, y borra los que ya no se usan.
# Todos abren el bot a traves de lanzador.py, que nunca abre una segunda ventana.
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
$pythonw = Join-Path $dir '.venv\Scripts\pythonw.exe'
$lanzador = '"' + (Join-Path $dir 'lanzador.py') + '"'

Nuevo-Acceso (Join-Path $inicio 'Bot Finanzas.lnk') $pythonw $lanzador 'Bot Finanzas (se abre al iniciar Windows)'
Nuevo-Acceso (Join-Path $escritorio 'Bot Finanzas.lnk') $pythonw $lanzador 'Abre la ventana del bot'
Nuevo-Acceso (Join-Path $escritorio 'Bot Finanzas - Actualizar.lnk') (Join-Path $dir 'ACTUALIZAR.bat') '' 'Actualiza el bot y lo arranca en la misma ventana'

foreach ($viejo in 'Bot Finanzas - Reconectar banco.lnk', 'Bot Finanzas - Diagnostico.lnk') {
    $ruta = Join-Path $escritorio $viejo
    if (Test-Path $ruta) { Remove-Item $ruta -Force }
}
