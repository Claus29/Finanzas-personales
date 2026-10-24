# Cierra el bot que este funcionando (de esta version o de cualquier anterior) y su ventana.
# Nunca cierra la ventana desde la que se ejecuta este script.
$ErrorActionPreference = 'SilentlyContinue'
$yo = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId
$todos = Get-CimInstance Win32_Process
$porId = @{}
foreach ($p in $todos) { $porId[[int]$p.ProcessId] = $p }

$bots = $todos | Where-Object {
    $_.Name -like 'python*' -and (
        $_.CommandLine -like '*FinanzasBot*principal.py*' -or
        $_.CommandLine -like '*FinanzasBot*\bot.py*')
}
foreach ($bot in $bots) {
    # Python del entorno virtual -> python real -> ventana (cmd) que lo ejecuta
    $padre = $porId[[int]$bot.ParentProcessId]
    if ($padre -and $padre.Name -like 'python*') { $padre = $porId[[int]$padre.ParentProcessId] }
    if ($padre -and $padre.Name -eq 'cmd.exe' -and [int]$padre.ProcessId -ne [int]$yo) {
        Stop-Process -Id $padre.ProcessId -Force
    }
    Stop-Process -Id $bot.ProcessId -Force
}
