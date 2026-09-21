# Instala el agente del botón del móvil en este PC.
#
# QUÉ HACE
# --------
# Deja una tarea programada que arranca el agente al iniciar sesión, sin ventana y en segundo
# plano. El agente es el que recibe las órdenes de apagar/reiniciar/suspender que se piden desde
# el móvil (ver `pc/agente_boton.py`).
#
# POR QUÉ HACE FALTA UNA TAREA PROGRAMADA Y NO UN SERVICIO
# --------------------------------------------------------
# Porque suspender el equipo desde un servicio de Windows no funciona (los servicios corren en
# otra sesión y no pueden pedir la suspensión), y porque apagar tampoco necesita privilegios:
# lo hace el propio usuario. Además, la tarea se crea **sin permisos de administrador**, que es
# justo lo que se busca: nada de esto debería necesitarlos.
#
# Uso:
#   .\instalar-agente-boton.ps1            # crea y arranca la tarea
#   .\instalar-agente-boton.ps1 -Quitar    # la borra
#   .\instalar-agente-boton.ps1 -Estado    # dice si está y cómo va

param(
    [switch]$Quitar,
    [switch]$Estado
)

$ErrorActionPreference = 'Stop'
$TAREA = 'RadioPV boton (PC)'
$RAIZ = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$PYTHONW = Join-Path $RAIZ '.venv\Scripts\pythonw.exe'
$AGENTE = Join-Path $RAIZ 'pc\agente_boton.py'

if ($Estado) {
    $t = Get-ScheduledTask -TaskName $TAREA -ErrorAction SilentlyContinue
    if (-not $t) { Write-Host 'La tarea NO está creada.' -ForegroundColor Yellow; exit 0 }
    $info = Get-ScheduledTaskInfo -TaskName $TAREA
    Write-Host ("Tarea: {0}" -f $t.State)
    Write-Host ("Última vez: {0}  resultado: {1}" -f $info.LastRunTime, $info.LastTaskResult)
    $log = Join-Path $RAIZ '_pc_data\boton_pc.log'
    if (Test-Path $log) {
        Write-Host "`nÚltimas líneas del registro:" -ForegroundColor Cyan
        Get-Content $log -Tail 8
    }
    exit 0
}

if ($Quitar) {
    Unregister-ScheduledTask -TaskName $TAREA -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Tarea «$TAREA» borrada." -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $PYTHONW)) { throw "No encuentro $PYTHONW (¿está el entorno virtual?)" }
if (-not (Test-Path $AGENTE)) { throw "No encuentro $AGENTE" }

$accion = New-ScheduledTaskAction -Execute $PYTHONW -Argument "`"$AGENTE`"" -WorkingDirectory $RAIZ
$disparo = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$ajustes = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TAREA -Action $accion -Trigger $disparo -Settings $ajustes `
    -Principal $principal -Description 'Agente del boton del movil: apagar, reiniciar y suspender el PC.' `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TAREA
Start-Sleep -Seconds 3

$t = Get-ScheduledTask -TaskName $TAREA
Write-Host ("Tarea «{0}»: {1}" -f $TAREA, $t.State) -ForegroundColor Green
Write-Host ''
Write-Host 'Comprobación:' -ForegroundColor Cyan
Write-Host '   .venv\Scripts\python.exe pc\agente_boton.py --una-vez    # una consulta y sale'
Write-Host '   .\instalar-agente-boton.ps1 -Estado                     # estado y registro'
Write-Host ''
Write-Host 'Y desde el móvil, la página del botón (servidor:8099) ya tiene los botones de apagar.' -ForegroundColor Cyan
