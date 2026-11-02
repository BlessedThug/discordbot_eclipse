@echo off
chcp 65001 >nul
:menu
cls
echo =========================================
echo     Управление GitHub репозиторием
echo =========================================
echo 1. Отправить изменения (Push)
echo 2. Скачать изменения (Pull)
echo 3. Статус репозитория (Status)
echo 4. Выход
echo =========================================
set /p choice="Выберите действие (1-4): "

if "%choice%"=="1" goto push
if "%choice%"=="2" goto pull
if "%choice%"=="3" goto status
if "%choice%"=="4" exit
goto menu

:push
cls
echo Добавление файлов...
git add .
echo.
set /p msg="Введите сообщение коммита (например, 'Добавил игры'): "
if "%msg%"=="" set msg="Автоматическое обновление"
git commit -m "%msg%"
echo.
echo Отправка на GitHub...
git push origin main
echo.
echo =========================================
echo Готово! Изменения отправлены.
echo =========================================
pause
goto menu

:pull
cls
echo Скачивание изменений с GitHub...
git pull origin main
echo.
echo =========================================
echo Готово!
echo =========================================
pause
goto menu

:status
cls
git status
echo.
pause
goto menu