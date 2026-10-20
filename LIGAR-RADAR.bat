@echo off
rem Liga o Radar de Canais em http://127.0.0.1:8400 e abre o navegador.
cd /d "%~dp0"
rem Um Radar antigo ainda aberto segura a porta 8400 e o novo não sobe (a página ficava com o código velho):
rem fecha o que estiver ouvindo nela antes de ligar.
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8400 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue; Write-Host 'Fechei o Radar que ja estava aberto.' }"
rem O servidor leva uns segundos para subir: o navegador só abre quando o Radar já responde (antes abria cedo
rem demais e mostrava "não é possível acessar este site").
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for ($i = 0; $i -lt 90; $i++) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8400/ | Out-Null; Start-Process 'http://127.0.0.1:8400'; break } catch { Start-Sleep -Seconds 1 } }"
echo Ligando o Radar... o navegador abre sozinho quando ele estiver pronto.
uv run python -m radar servidor
pause
