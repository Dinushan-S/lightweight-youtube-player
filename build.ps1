# Builds dist\LightweightYouTubePlayer.exe (one file, mpv bundled inside).
# Needs: the project venv (.venv) with requirements.txt + pyinstaller installed, and bin\mpv.exe present.
Set-Location $PSScriptRoot

if (-not (Test-Path "bin\mpv.exe")) { throw "bin\mpv.exe is missing. See README > Build from source." }

# Google sign-in is only offered when a Google OAuth client file (client_secret*.json) is next to this script
$google = @(Get-ChildItem client_secret*.json | Select-Object -First 1 | ForEach-Object { "--add-data"; "$($_.Name);." })
if ($google) { Write-Host "Bundling Google client: $($google[1])" } else { Write-Host "No client_secret*.json: Google sign-in left out" }

# PyInstaller logs to stderr; judge success by its exit code, not by stderr output.
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name LightweightYouTubePlayer `
    --icon assets\icon.ico `
    --add-binary "bin\mpv.exe;bin" `
    --add-binary "bin\vulkan-1.dll;bin" `
    --add-data "assets\icon.ico;assets" `
    --collect-data customtkinter `
    --hidden-import pystray._win32 `
    @google `
    main.py 2>&1 | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }

Write-Host "Built: $(Resolve-Path dist\LightweightYouTubePlayer.exe)"
