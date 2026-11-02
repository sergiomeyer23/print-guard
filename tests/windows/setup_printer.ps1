$ErrorActionPreference = "Stop"
$name = "printguard-ci"
$port = Join-Path $env:RUNNER_TEMP "printguard-ci.prn"
Write-Host "drivers: $((Get-PrinterDriver | Select-Object -ExpandProperty Name) -join '; ')"
Add-PrinterPort -Name $port
Add-Printer -Name $name -DriverName "Generic / Text Only" -PortName $port
Get-CimInstance Win32_Printer -Filter "Name='$name'" | Invoke-CimMethod -MethodName Pause | Out-Null
Write-Host "printer: $((Get-Printer -Name $name | Format-List Name, DriverName, PortName, PrinterStatus | Out-String).Trim())"
"PRINTGUARD_TEST_PRINTER=$name" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8
