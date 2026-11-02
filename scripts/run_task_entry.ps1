[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PrinterName,
    [string]$Workdir = (Split-Path -Parent $PSScriptRoot),
    [string]$Python = "python",
    [string]$Deadline = "09:05",
    [int]$ConfirmTimeout = 120
)

$ErrorActionPreference = "Stop"
$logDir = Join-Path $Workdir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("guard_{0:yyyy-MM-dd}.log" -f (Get-Date))

function Write-GuardLog([string]$message) {
    "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $message | Add-Content -Path $log
}

$commonArguments = @(
    "--workdir", $Workdir,
    "--printer", "spooler",
    "--printer-name", $PrinterName,
    "--confirm-timeout", $ConfirmTimeout,
    "--event-log"
)

function Invoke-Printguard([string]$Executable, [string[]]$Arguments) {
    # Windows PowerShell 5.1 turns native stderr lines into terminating errors under
    # "Stop", and printguard logs to stderr.
    $ErrorActionPreference = "Continue"
    & $Executable -m printguard @Arguments 2>&1 | Add-Content -Path $log
    return $LASTEXITCODE
}

Write-GuardLog "guard started"
if ((Invoke-Printguard $Python (@("check") + $commonArguments)) -eq 0) {
    Write-GuardLog "today is already confirmed, exiting"
    exit 0
}

$code = Invoke-Printguard $Python (@("run") + $commonArguments)
Write-GuardLog "run exited with $code"

if ($code -eq 3) {
    Write-GuardLog "another instance is running, leaving it alone"
    exit 0
}

if ($code -ne 0) {
    [void](Invoke-Printguard $Python (@("check", "--deadline", $Deadline) + $commonArguments))
}
exit $code
