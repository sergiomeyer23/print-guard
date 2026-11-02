$ErrorActionPreference = "Continue"
$python = (Get-Command python).Source
$work = Join-Path $env:RUNNER_TEMP "guardian"
New-Item -ItemType Directory -Force -Path $work | Out-Null

& $python -m printguard seed --workdir $work 2>&1 | Out-Host
& powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_task_entry.ps1 `
    -PrinterName "printguard-ci" -Workdir $work -Python $python -ConfirmTimeout 6
$code = $LASTEXITCODE
Write-Host "guardian exit code: $code"

$log = Get-ChildItem -Path (Join-Path $work "logs") -Filter "guard_*.log" | Select-Object -First 1
$text = if ($log) { Get-Content $log.FullName -Raw } else { "" }
Write-Host "---- guard log ----"
Write-Host $text
$alert = Get-ChildItem -Path (Join-Path $work "out") -Filter "ALERTA_*.txt" -ErrorAction SilentlyContinue
if ($alert) { Write-Host "---- alert ----"; Get-Content $alert.FullName | Out-Host }

$ran = $text -match "guard started" -and $text -match "run exited with (\d+)"
if (-not $ran) { Write-Host "::error::guardian did not run to the end"; exit 1 }
$runCode = [int]$Matches[1]
if ($runCode -ne 0 -and -not $alert) { Write-Host "::error::run failed without leaving an alert"; exit 1 }
Write-Host "guardian completed, run exit code $runCode"
