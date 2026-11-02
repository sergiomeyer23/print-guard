$ErrorActionPreference = "Stop"
$name = "printguard-ci-task"
$python = (Get-Command python).Source

function Assert-Equal($actual, $expected, $label) {
    if ($actual -ne $expected) {
        Write-Host "::error::$label expected '$expected' but was '$actual'"
        $script:failed = $true
    } else {
        Write-Host "ok: $label = $actual"
    }
}

$failed = $false
try {
    & .\scripts\install_task.ps1 -PrinterName "printguard-ci" -Python $python -TaskName $name
    $task = Get-ScheduledTask -TaskName $name
    Assert-Equal @($task.Triggers).Count 2 "trigger count"
    $daily = @($task.Triggers | Where-Object { $_.CimClass.CimClassName -eq "MSFT_TaskDailyTrigger" })[0]
    $boot = @($task.Triggers | Where-Object { $_.CimClass.CimClassName -eq "MSFT_TaskBootTrigger" })[0]
    Assert-Equal ([datetime]$daily.StartBoundary).ToString("HH:mm") "08:00" "daily start"
    Assert-Equal $daily.Repetition.Interval "PT5M" "repetition interval"
    Assert-Equal $daily.Repetition.Duration "PT1H5M" "repetition duration"
    Assert-Equal $boot.Delay "PT5M" "boot delay"
    Assert-Equal $task.Settings.WakeToRun $true "WakeToRun"
    Assert-Equal $task.Settings.StartWhenAvailable $true "StartWhenAvailable"
    Assert-Equal "$($task.Settings.MultipleInstances)" "IgnoreNew" "MultipleInstances"
    Write-Host "action: $($task.Actions[0].Execute) $($task.Actions[0].Arguments)"
} finally {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
if ($failed) { exit 1 }
