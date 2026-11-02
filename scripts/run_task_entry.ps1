[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PrinterName,
    [string]$Workdir = (Split-Path -Parent $PSScriptRoot),
    [string]$Python = "python",
    [string]$Deadline = "09:05"
)

$ErrorActionPreference = "Stop"
$logDir = Join-Path $Workdir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("guard_{0:yyyy-MM-dd}.log" -f (Get-Date))

function Write-Log([string]$message) {
    "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $message | Add-Content -Path $log
}

function Invoke-Printguard([string[]]$arguments) {
    & $Python -m printguard @arguments --workdir $Workdir --printer spooler --printer-name $PrinterName --event-log 2>&1 |
        Add-Content -Path $log
    return $LASTEXITCODE
}

Write-Log "guard started"
if ((Invoke-Printguard @("check")) -eq 0) {
    Write-Log "today is already confirmed, exiting"
    exit 0
}

$code = Invoke-Printguard @("run")
Write-Log "run exited with $code"

if ($code -ne 0) {
    [void](Invoke-Printguard @("check", "--deadline", $Deadline))
}
exit $code
