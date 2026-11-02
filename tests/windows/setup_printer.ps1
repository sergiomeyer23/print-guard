$ErrorActionPreference = "Stop"
trap {
    Write-Host "::error::$($_.Exception.Message) at line $($_.InvocationInfo.ScriptLineNumber)"
    exit 1
}
$name = "printguard-ci"
Write-Host "::notice::drivers: $((Get-PrinterDriver | Select-Object -ExpandProperty Name) -join '; ')"
$port = Join-Path $env:RUNNER_TEMP "printguard-ci.pdf"
Add-PrinterPort -Name $port
Add-Printer -Name $name -DriverName "Microsoft Print To PDF" -PortName $port
Get-CimInstance Win32_Printer -Filter "Name='$name'" | Invoke-CimMethod -MethodName Pause | Out-Null
Write-Host "printer: $((Get-Printer -Name $name | Format-List Name, DriverName, PortName, PrinterStatus | Out-String).Trim())"
"PRINTGUARD_TEST_PRINTER=$name" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8
