param(
    [string]$RunDirectory,
    [switch]$TrustBundledTests
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $TrustBundledTests) {
    throw "Use -TrustBundledTests for this bundled native Windows demo. For isolated tests, run the launcher in WSL as described in docs/harness/windows.md."
}
if (-not $RunDirectory) {
    $RunDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("advisor-demo-" + [guid]::NewGuid().ToString("N"))
}
$RunDirectory = [System.IO.Path]::GetFullPath($RunDirectory)
if (Test-Path -LiteralPath $RunDirectory) {
    throw "Choose a new run directory."
}

$Fixture = Join-Path $Repo "examples/harness/project"
$Workspace = Join-Path $RunDirectory "project"
$OriginalPolicy = Join-Path $Repo "examples/harness/policy.json"
$PolicyPath = Join-Path $RunDirectory "policy.json"
$Db = Join-Path $RunDirectory "state.db"
New-Item -ItemType Directory -Path $Workspace | Out-Null
Copy-Item -LiteralPath (Join-Path $Fixture "calculator.py"), (Join-Path $Fixture "test_calculator.py") -Destination $Workspace
$Policy = Get-Content -LiteralPath $OriginalPolicy -Raw | ConvertFrom-Json
foreach ($entry in $Policy.checks.PSObject.Properties) {
    if ($entry.Value.kind -eq "command") {
        $entry.Value | Add-Member -NotePropertyName execution -NotePropertyValue "trusted"
        $entry.Value | Add-Member -NotePropertyName replayable -NotePropertyValue $true
    }
}
[System.IO.File]::WriteAllText($PolicyPath, ($Policy | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding($false)))

$Launcher = Get-Command "py.exe" -ErrorAction SilentlyContinue
$PythonArguments = @()
if ($Launcher) {
    $PythonArguments += "-3"
} else {
    $Launcher = Get-Command "python.exe" -ErrorAction Stop
}
$PythonArguments += @(
    "-B", "-m", "advisor_harness", "--db", $Db, "start", "--workspace", $Workspace,
    "--policy", $PolicyPath, "--provider", "mock", "--allow-trusted-tests",
    "--goal", "Repair the calculator addition and preserve its old label and test files."
)
Push-Location $Repo
try {
    & $Launcher.Source @PythonArguments
    $ResultCode = $LASTEXITCODE
} finally {
    Pop-Location
}
Write-Host "Evidence database $Db"
exit $ResultCode
