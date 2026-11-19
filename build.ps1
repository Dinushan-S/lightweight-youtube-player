# Builds dist\LightweightYouTubePlayer.exe (one file, mpv bundled inside).
# Needs: the project venv (.venv) with requirements.txt + pyinstaller installed, and bin\mpv.exe present.
Set-Location $PSScriptRoot

if (-not (Test-Path "bin\mpv.exe")) { throw "bin\mpv.exe is missing. See README > Build from source." }

# PyInstaller logs to stderr; judge success by its exit code, not by stderr output.
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name LightweightYouTubePlayer `
    --icon assets\icon.ico `
    --add-binary "bin\mpv.exe;bin" `
    --add-binary "bin\vulkan-1.dll;bin" `
    --add-data "assets\icon.ico;assets" `
    --collect-data customtkinter `
    main.py 2>&1 | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }

Write-Host "Built: $(Resolve-Path dist\LightweightYouTubePlayer.exe)"
