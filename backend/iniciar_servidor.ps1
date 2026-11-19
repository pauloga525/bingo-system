# Inicia el servidor del Bingo (API + tablero del juego).
# Carga la configuración de .env (si existe) y ejecuta app.py con el entorno virtual.
#
# Uso (desde PowerShell, en esta carpeta):
#     .\iniciar_servidor.ps1
# Si Windows bloquea el script la primera vez:
#     powershell -ExecutionPolicy Bypass -File .\iniciar_servidor.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        $line = $line.Trim()
        if ($line -eq "" -or $line.StartsWith("#") -or -not $line.Contains("=")) { continue }
        $name, $value = $line.Split("=", 2)
        Set-Item -Path "Env:$($name.Trim())" -Value $value.Trim()
    }
    Write-Host "Configuración cargada desde .env"
} else {
    Write-Warning "No existe .env: se usan los valores por defecto (copie .env.example como .env)."
}

$python = Join-Path $PSScriptRoot "env\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "No se encontró el entorno virtual (env). Instálelo con: python -m venv env; env\Scripts\pip install -r requirements.txt"
}

& $python (Join-Path $PSScriptRoot "app.py")
