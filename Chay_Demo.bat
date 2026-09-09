@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   Cong cu doc & sang loc nhanh dien tam do (demo) - BV Bach Mai
echo ============================================================
echo.

rem ---- Buoc 1: kiem tra / cai dat Python ----
set "PYEXE=python"
where python >nul 2>nul
if not %errorlevel%==0 (
    echo [1/4] Khong tim thay Python tren may nay.
    echo       Dang tai Python 3.11 ve de tu cai dat cho tai khoan hien tai
    echo       ^(khong can quyen quan tri may^)... viec nay can ket noi mang.
    echo.
    set "PY_INSTALLER=%TEMP%\python-installer-ecgdemo.exe"
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '!PY_INSTALLER!'"
    if not exist "!PY_INSTALLER!" (
        echo.
        echo LOI: Khong tai duoc Python ^(co the may khong co mang, hoac mang benh
        echo vien chan tai file^). Vui long nho IT cai san Python 3.10 tro len
        echo ^(tick "Add python.exe to PATH" khi cai^), roi chay lai file nay.
        echo.
        pause
        exit /b 1
    )
    echo       Dang cai dat Python, vui long doi ^(khoang 1-2 phut^)...
    "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
    set "PYEXE=%LocalAppData%\Programs\Python\Python311\python.exe"
    if not exist "!PYEXE!" (
        echo.
        echo LOI: Cai Python khong thanh cong. Vui long tu cai Python 3.10 tro len
        echo tu https://www.python.org/downloads/ ^(nho tick "Add to PATH"^), roi
        echo chay lai file nay.
        echo.
        pause
        exit /b 1
    )
    echo       Da cai xong Python.
) else (
    echo [1/4] Da tim thay Python tren may - bo qua buoc cai dat.
)
echo.

rem ---- Buoc 2: tao moi truong ao (.venv) neu chua co ----
if not exist ".venv\Scripts\python.exe" (
    echo [2/4] Dang tao moi truong rieng cho cong cu ^(lan dau, vai chuc giay^)...
    "!PYEXE!" -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo LOI: Khong tao duoc moi truong ao. Vui long lien he ho tro ky thuat.
        pause
        exit /b 1
    )
) else (
    echo [2/4] Moi truong rieng da co san - bo qua.
)
set "VENV_PY=.venv\Scripts\python.exe"
echo.

rem ---- Buoc 3: cai thu vien can thiet (chi lan dau) ----
if not exist ".venv\installed.flag" (
    echo [3/4] Dang cai cac thu vien can thiet ^(chi lam 1 lan, co the mat
    echo       vai phut tuy toc do mang - vui long doi, dung tat cua so^)...
    "!VENV_PY!" -m pip install --upgrade pip --quiet
    "!VENV_PY!" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo LOI: Cai thu vien khong thanh cong. Kiem tra lai ket noi mang roi
        echo chay lai file nay ^(cac buoc da xong se khong phai lam lai^).
        echo.
        pause
        exit /b 1
    )
    echo ok > ".venv\installed.flag"
    echo       Da cai xong thu vien.
) else (
    echo [3/4] Thu vien da duoc cai tu truoc - bo qua ^(chay nhanh^).
)
echo.

rem ---- Buoc 4: chay giao dien demo ----
echo [4/4] Dang mo giao dien demo tren trinh duyet ^(dia chi mac dinh:
echo       http://localhost:8501 ^)... Dong cua so nay se tat cong cu.
echo.
"!VENV_PY!" -m streamlit run "app.py"

pause
