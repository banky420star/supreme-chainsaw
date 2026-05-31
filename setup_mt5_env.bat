@echo off
REM ===== SupremeChainsaw MT5 Demo Account Setup =====
REM Run this as Administrator to set persistent environment variables
echo Setting MT5 Demo Account environment variables...
echo.
REM These are persisted as system-wide environment variables (/M flag)
setx MT5_LOGIN "435656990" /M
setx MT5_PASSWORD "Fuckyou2/" /M
setx MT5_SERVER "Exness-MT5Trial9" /M
echo.
echo Done! Please restart your terminal for changes to take effect.
echo.
echo To verify: echo %%MT5_LOGIN%%  %%MT5_PASSWORD%%  %%MT5_SERVER%%
pause
