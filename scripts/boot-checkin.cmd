@echo off
rem ==============================================================================
rem WorkBuddy Boot & Network-Ready Auto Check-in Gate (Windows)
rem https://github.com/FlapPearLabs/workbuddy-toolkit
rem ==============================================================================

setlocal enabledelayedexpansion

set "WORKBUDDY_DIR=%USERPROFILE%\.workbuddy"
set "LOG_DIR=%WORKBUDDY_DIR%\logs"
set "LOG_FILE=%LOG_DIR%\boot_checkin.log"
set "FLAG_FILE=%WORKBUDDY_DIR%\.last_boot_checkin"

if not exist "%WORKBUDDY_DIR%" mkdir "%WORKBUDDY_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

rem 1. 获取当前日期 (YYYY-MM-DD)
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd" 2^>nul') do set "TODAY=%%i"
if "%TODAY%"=="" set "TODAY=%date:~0,10%"

rem 2. 幂等防护：如果今日已签到，直接静默退出
if exist "%FLAG_FILE%" (
    set /p LAST_DATE=<"%FLAG_FILE%"
    if "!LAST_DATE!"=="!TODAY!" exit /b 0
)

rem 3. 循环等待网络就绪 (最多等待 90 秒，每次检测间隔 2 秒)
set /a MAX_RETRIES=45
set /a COUNT=0
set "CONNECTED=0"

:CHECK_NET
rem 双重探测：curl 探测 https 连通，回退 ping 公共 DNS
curl -I -s --connect-timeout 2 "https://copilot.tencent.com" >nul 2>&1
if !errorlevel! equ 0 (
    set "CONNECTED=1"
    goto NET_READY
)
ping -n 1 -w 1500 223.5.5.5 >nul 2>&1
if !errorlevel! equ 0 (
    set "CONNECTED=1"
    goto NET_READY
)

set /a COUNT+=1
if !COUNT! geq !MAX_RETRIES! goto NET_TIMEOUT
timeout /t 2 /nobreak >nul 2>&1 || ping 127.0.0.1 -n 3 >nul
goto CHECK_NET

:NET_TIMEOUT
echo [%TODAY% %time%] [WorkBuddy Boot Gate] 超过 90 秒未检测到网络就绪，退出执行。>> "%LOG_FILE%"
exit /b 1

:NET_READY
rem 4. 连上网后稳定等待 5 秒 (规避网卡握手抖动)
timeout /t 5 /nobreak >nul 2>&1 || ping 127.0.0.1 -n 6 >nul

rem 5. 定位并调用 wb-checkin
set "CHECKIN_BIN="
if exist "%USERPROFILE%\.local\bin\wb-checkin.cmd" (
    set "CHECKIN_BIN=%USERPROFILE%\.local\bin\wb-checkin.cmd"
) else if exist "%USERPROFILE%\.workbuddy\toolkit\bin\wb-checkin.cmd" (
    set "CHECKIN_BIN=%USERPROFILE%\.workbuddy\toolkit\bin\wb-checkin.cmd"
) else (
    where wb-checkin >nul 2>&1
    if !errorlevel! equ 0 set "CHECKIN_BIN=wb-checkin"
)

if "%CHECKIN_BIN%"=="" (
    echo [%TODAY% %time%] [WorkBuddy Boot Gate] ✖ 未找到 wb-checkin 命令。>> "%LOG_FILE%"
    exit /b 1
)

echo [%TODAY% %time%] [WorkBuddy Boot Gate] 网络已就绪，正在触发自动签到与保活对话...>> "%LOG_FILE%"
call "%CHECKIN_BIN%" >> "%LOG_FILE%" 2>&1
if !errorlevel! equ 0 (
    echo !TODAY!> "%FLAG_FILE%"
    echo [%TODAY% %time%] [WorkBuddy Boot Gate] ✔ 今日签到流程执行完成，已写入单日防重标记。>> "%LOG_FILE%"
    exit /b 0
) else (
    echo [%TODAY% %time%] [WorkBuddy Boot Gate] ▲ 签到命令退出异常。>> "%LOG_FILE%"
    exit /b !errorlevel!
)
