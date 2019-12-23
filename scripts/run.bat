echo off

CD %~p0..
:Begin
choice /C:AWBLC /M:"run: Active Env[A] Worker[W] Beat[B] Local Tasks[L] Cancel[C]"
echo "input is :" %errorlevel%
if errorlevel 5 goto End
if errorlevel 4 goto LocalTasks
if errorlevel 3 goto Beat
if errorlevel 2 goto Worker
if errorlevel 1 goto Active
goto Begin

:Active
.\venv\Scripts\activate.bat
goto End

:Worker
celery -A tasks worker --loglevel=info -c 1 -P eventlet
goto End

:Beat
celery beat -A tasks
goto End

:LocalTasks
Python.exe -m tasks.__init__
goto End

:End

echo on
echo bye bye
