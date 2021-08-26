@echo off
start "" "%ProgramFiles%\Git\git-bash.exe" -c "mingw32-make.exe %*; sleep 1"
