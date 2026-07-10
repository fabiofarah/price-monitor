@echo off
cd /d "%~dp0"
echo Inicializando repositorio git...
git init
git remote add origin https://github.com/fabiofarah/price-monitor.git
git add .
git status
echo.
echo Arquivos acima serao commitados. Pressione qualquer tecla para continuar...
pause > nul
git commit -m "feat: monitor de precos 1001festas e concorrentes"
git branch -M main
git push -u origin main
echo.
echo Pronto! Agora rode na VCP:
echo   git clone https://github.com/fabiofarah/price-monitor.git
pause
