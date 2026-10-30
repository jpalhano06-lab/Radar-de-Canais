# Liga a fábrica junto com o Radar: o LIGAR-RADAR.bat chama este arquivo antes de subir o Radar.
#
# Sem isto, o Radar subia sozinho e a página mostrava "Fábrica desligada": era preciso ir até a pasta da fábrica e
# clicar no LIGAR-TIPLABS.bat. Aqui só se liga a fábrica (porta 8080) quando ela não está no ar — nada de git pull,
# stash, túnel, vigia ou painel: isso continua sendo trabalho do LIGAR-TIPLABS.bat, que o usuário roda quando quiser
# atualizar a fábrica.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'

$RADAR = $PSScriptRoot
$PORTA = 8080

# a pasta da fábrica é a mesma que o Radar usa: RADAR_FABRICA no .env dele, ou a pasta de cima
$FABRICA = $null
$env_ = Join-Path $RADAR '.env'
if (Test-Path $env_) {
    $linha = Select-String -Path $env_ -Pattern '^\s*RADAR_FABRICA\s*=\s*(.+?)\s*$' | Select-Object -First 1
    if ($linha) { $FABRICA = $linha.Matches[0].Groups[1].Value.Trim('"', "'") }
}
if (-not $FABRICA) { $FABRICA = Split-Path $RADAR -Parent }
if (-not (Test-Path (Join-Path $FABRICA 'fabrica'))) {
    Write-Host "  A fábrica não está em $FABRICA. O Radar liga sem ela." -ForegroundColor Yellow
    exit
}

# Diz se a fábrica está viva. O 401 conta como viva: é ela recusando por falta de token, não ausência dela.
function FabricaResponde {
    try {
        Invoke-WebRequest "http://127.0.0.1:$PORTA/" -UseBasicParsing -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        return $null -ne $_.Exception.Response
    }
}

if (FabricaResponde) {
    Write-Host '  Fábrica já estava ligada.' -ForegroundColor Green
    exit
}

# porta presa por um processo velho que não responde: a fábrica nova nem sobe enquanto ele estiver lá
Get-NetTCPConnection -LocalPort $PORTA -State Listen |
    Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force }

$uv = (Get-Command uv).Source
if (-not $uv) { $uv = "$env:USERPROFILE\.local\bin\uv.exe" }

# o editor que a própria fábrica serve em http://localhost:8080, do mesmo jeito que o LIGAR-TIPLABS procura
$frente = @()
$acima = Split-Path $FABRICA -Parent
foreach ($p in @((Join-Path $FABRICA 'front-editor'), (Join-Path $acima 'front-editor'), (Join-Path $acima 'tiplabs\front-editor'))) {
    if (Test-Path (Join-Path $p 'index.html')) { $frente = @('--frontend', $p); break }
}

# --no-sync: o uv reinstalaria a fábrica e tentaria reescrever o Scripts\fabrica.exe, que o Windows trava quando
# outro fabrica.exe (o MCP, por exemplo) está rodando. Quem atualiza o ambiente é o LIGAR-TIPLABS.bat.
$log = Join-Path $FABRICA 'fabrica.log'
Write-Host '  Ligando a fábrica (escondida, sem janela)...' -ForegroundColor Yellow
Start-Process -FilePath $uv `
    -ArgumentList (@('run', '--no-sync', 'fabrica', 'servidor', '--porta', "$PORTA") + $frente) `
    -WorkingDirectory $FABRICA `
    -WindowStyle Hidden `
    -RedirectStandardOutput $log `
    -RedirectStandardError "$log.erros"

foreach ($i in 1..40) {
    Start-Sleep -Seconds 1
    if (FabricaResponde) { Write-Host '  Fábrica no ar.' -ForegroundColor Green; exit }
}
Write-Host '  A fábrica não subiu. Veja o fabrica.log ou rode o LIGAR-TIPLABS.bat na pasta dela.' -ForegroundColor Red
