# Gera uma pasta ClipFlow/ com o executável e todas as ferramentas embutidas.
# Precisa de Windows x64 + Python 3.11-3.13 NO COMPUTADOR DE COMPILACAO.
# Em GitHub Actions, as ferramentas são instaladas apenas no runner temporário.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$vendor = Join-Path $root 'vendor'
$tempRoot = if ([string]::IsNullOrWhiteSpace($env:RUNNER_TEMP)) { $env:TEMP } else { $env:RUNNER_TEMP }
$work = Join-Path $tempRoot 'clipflow-tools'
New-Item -ItemType Directory -Force -Path $vendor, $work | Out-Null

function DownloadZip([string] $url, [string] $basename) {
    $archive = Join-Path $work "$basename.zip"
    $destination = Join-Path $work $basename
    Write-Host "Baixando $basename..."
    Invoke-WebRequest -Uri $url -OutFile $archive -MaximumRedirection 10
    Expand-Archive -LiteralPath $archive -DestinationPath $destination -Force
    return $destination
}

$ffmpegFolder = DownloadZip `
  'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' 'ffmpeg'
$ffmpeg = Get-ChildItem $ffmpegFolder -Recurse -File -Filter 'ffmpeg.exe' | Select-Object -First 1
$ffprobe = Get-ChildItem $ffmpegFolder -Recurse -File -Filter 'ffprobe.exe' | Select-Object -First 1
if (-not $ffmpeg -or -not $ffprobe) { throw 'Nao foi possivel encontrar ffmpeg.exe e ffprobe.exe no ZIP.' }
Copy-Item $ffmpeg.FullName (Join-Path $vendor 'ffmpeg.exe') -Force
Copy-Item $ffprobe.FullName (Join-Path $vendor 'ffprobe.exe') -Force

$denoFolder = DownloadZip `
  'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip' 'deno'
$deno = Get-ChildItem $denoFolder -Recurse -File -Filter 'deno.exe' | Select-Object -First 1
if (-not $deno) { throw 'Nao foi possivel encontrar deno.exe no ZIP.' }
Copy-Item $deno.FullName (Join-Path $vendor 'deno.exe') -Force

Write-Host 'Verificando executaveis incorporados...'
& (Join-Path $vendor 'ffmpeg.exe') -version | Select-Object -First 1
& (Join-Path $vendor 'deno.exe') --version | Select-Object -First 1

Write-Host 'Instalando bibliotecas de compilacao na maquina de build...'
python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Falha ao atualizar pip.' }
python -m pip install -r requirements.txt 'pyinstaller>=6.10,<7'
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependencias.' }

$arguments = @(
  '-m', 'PyInstaller',
  '--noconfirm', '--clean', '--onedir', '--console',
  '--name', 'ClipFlow',
  '--collect-all', 'yt_dlp',
  '--collect-all', 'yt_dlp_ejs',
  '--add-data', 'static;static',
  '--add-binary', 'vendor\ffmpeg.exe;vendor',
  '--add-binary', 'vendor\ffprobe.exe;vendor',
  '--add-binary', 'vendor\deno.exe;vendor',
  'desktop.py'
)
Write-Host 'Compilando ClipFlow.exe...'
& python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar o executavel.' }

$exe = Join-Path $root 'dist\ClipFlow\ClipFlow.exe'
if (-not (Test-Path $exe)) { throw 'Executavel esperado nao encontrado.' }
Write-Host "Sucesso! Pasta portatil: $(Join-Path $root 'dist\ClipFlow')"
