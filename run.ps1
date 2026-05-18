$scriptRoot = $PSScriptRoot
$venvPython = Join-Path $scriptRoot '.venv\Scripts\python.exe'
$updateScript = Join-Path $scriptRoot 'update.py'

if (-Not (Test-Path $venvPython)) {
    Write-Error "Cannot find repository virtual environment at $venvPython"
    exit 1
}

& $venvPython $updateScript
