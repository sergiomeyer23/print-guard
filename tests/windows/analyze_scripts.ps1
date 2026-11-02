Install-Module PSScriptAnalyzer -Force -Scope CurrentUser -SkipPublisherCheck
$results = Invoke-ScriptAnalyzer -Path scripts -Severity Error, Warning
foreach ($r in $results) {
    $name = Split-Path $r.ScriptPath -Leaf
    Write-Host "::warning file=scripts/$name,line=$($r.Line)::$($r.RuleName): $($r.Message)"
}
Write-Host "PSScriptAnalyzer: $(@($results).Count) findings"
if (@($results | Where-Object Severity -eq "Error").Count -gt 0) { exit 1 }
