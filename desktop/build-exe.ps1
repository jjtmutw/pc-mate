param(
  [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$distDir = Join-Path $projectRoot "dist"
$workDir = Join-Path $projectRoot "build"

Write-Host "Building pc-mate listener.exe from listener.py ..."

Push-Location $projectRoot
try {
  & $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name pc-mate-listener `
    --distpath $distDir `
    --workpath $workDir `
    (Join-Path $scriptDir "listener.py")
}
finally {
  Pop-Location
}

Write-Host ""
Write-Host "Build finished."
Write-Host "EXE output:" (Join-Path $distDir "pc-mate-listener.exe")
