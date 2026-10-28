@echo off
rem A barra de carregamento da fabrica na barra de tarefas do Windows: uma janelinha com a porcentagem,
rem e o icone dela na barra de tarefas vai enchendo conforme o video anda (igual o Chrome baixando arquivo).
rem Minimize a janela e esqueca: a barrinha continua la embaixo.
rem
rem O "pythonw" e' o Python sem a janela preta: so a janelinha aparece.
rem O Radar precisa estar ligado (LIGAR-RADAR.bat).
cd /d "%~dp0"
start "" uv run pythonw -m radar barra
