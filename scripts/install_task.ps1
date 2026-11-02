[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PrinterName,
    [string]$Workdir = (Split-Path -Parent $PSScriptRoot),
    [string]$Python = "python",
    [string]$TaskName = "printguard"
)

$ErrorActionPreference = "Stop"
$Python = (Get-Command $Python).Source
$entry = Join-Path $PSScriptRoot "run_task_entry.ps1"
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$entry`" -PrinterName `"$PrinterName`" -Workdir `"$Workdir`" -Python `"$Python`""

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $Workdir

$repeating = New-ScheduledTaskTrigger -Once -At "08:00" `
    -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Hours 1 -Minutes 5)
$daily = New-ScheduledTaskTrigger -Daily -At "08:00"
$daily.Repetition = $repeating.Repetition

$boot = New-ScheduledTaskTrigger -AtStartup
$boot.Delay = "PT5M"

$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

if (-not [System.Diagnostics.EventLog]::SourceExists("printguard")) {
    try {
        New-EventLog -LogName Application -Source "printguard"
    } catch {
        Write-Warning "Could not register the 'printguard' event source (needs an elevated prompt). Alerts will still be written to files."
    }
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($daily, $boot) `
    -Settings $settings -Description "Prints the daily report and confirms the job" -Force | Out-Null
Write-Output "Registered task '$TaskName' (08:00 daily, every 5 min until 09:05, plus boot +5 min)."
