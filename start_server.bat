@echo off
cd /d "c:\Users\bert-\OneDrive\Documenten\automation"
:loop
python server.py
echo Server gestopt, herstart over 5 seconden...
timeout /t 5 /nobreak >nul
goto loop
