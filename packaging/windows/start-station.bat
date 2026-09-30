@echo off
rem SAR ground control station with REAL aircraft over MAVLink (register each aircraft with
rem its connection, e.g. udpin://0.0.0.0:14550, and its MAVLink system id).
rem Consoles on other devices of the LAN open http://<this computer's address>:8000/
rem Plain HTTP and no video relay: for a field deployment use the Docker stack
rem (docs\runbooks\field-deployment.md), which adds TLS, video and container hardening.
setlocal
cd /d "%~dp0"
set SARGCS_DATA_DIR=%~dp0data
set SARGCS_HOST=0.0.0.0
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
