$failed = $false
foreach ($file in Get-ChildItem -Path scripts -Filter *.ps1) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    foreach ($err in $errors) {
        Write-Host "::error file=scripts/$($file.Name),line=$($err.Extent.StartLineNumber)::$($err.Message)"
        $failed = $true
    }
    Write-Host "$($file.Name): $($errors.Count) parse errors (PowerShell $($PSVersionTable.PSVersion))"
}
if ($failed) { exit 1 }
