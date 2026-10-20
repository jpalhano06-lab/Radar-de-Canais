@echo off
rem Sobe o Radar de Canais para o GitHub como repositorio PRIVADO.
cd /d "%~dp0"
where git >nul 2>nul || (echo Git nao esta instalado. Baixe em https://git-scm.com/download/win e rode de novo. & pause & exit /b 1)
if not exist .git (git init -b main)
git add -A
git -c user.name="Palhano" -c user.email="jpalhano34@gmail.com" commit -m "Radar de Canais" || echo Nada novo para commitar.
where gh >nul 2>nul && (
  gh auth status >nul 2>nul || gh auth login --web
  git remote get-url origin >nul 2>nul || gh repo create radar-de-canais --private --source . --remote origin
  git push -u origin main
  echo. & echo Pronto! & pause & exit /b 0
)
git remote get-url origin >nul 2>nul || (
  echo Crie um repositorio VAZIO e PRIVADO em https://github.com/new chamado radar-de-canais
  set /p URL=Cole aqui o endereco dele ^(https://github.com/.../radar-de-canais.git^): 
  call git remote add origin %%URL%%
)
git push -u origin main
echo. & echo Pronto! & pause
