@echo off
rem SAR ground control station, SIMULATION mode: every registered aircraft is simulated.
rem Data is kept in data-sim\ next to this file. The console opens at http://127.0.0.1:8000/
rem once the station answers (another port: set SARGCS_PORT before starting).
setlocal
cd /d "%~dp0"
set SARGCS_SIMULATION=true
set SARGCS_DATA_DIR=%~dp0data-sim
set SARGCS_TERRAIN_DIR=%~dp0terrain
set SARGCS_LOG_JSON=false
set SARGCS_OPEN_BROWSER=true
if not exist "%SARGCS_DATA_DIR%\ops.db" (
  echo First start: create the first administrator account.
  SAR-GCS\sar-gcs.exe create-admin --username chief || goto :error
)
SAR-GCS\sar-gcs.exe || goto :error
goto :eof
:error
echo.
echo The station did not start or stopped with an error. See the messages above.
pause
