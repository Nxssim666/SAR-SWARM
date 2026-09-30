@echo off
rem SAR ground control station, SIMULATION mode: every registered aircraft is simulated.
rem Data is kept in data-sim\ next to this file. The console opens at http://127.0.0.1:8000/
setlocal
cd /d "%~dp0"
set SARGCS_SIMULATION=true
set SARGCS_DATA_DIR=%~dp0data-sim
set SARGCS_LOG_JSON=false
if not exist "%SARGCS_DATA_DIR%\ops.db" (
  echo First start: create the first administrator account.
  SAR-GCS\sar-gcs.exe create-admin --username chief || goto :error
)
start "" http://127.0.0.1:8000/
SAR-GCS\sar-gcs.exe
goto :eof
:error
echo Failed. See the messages above.
pause
