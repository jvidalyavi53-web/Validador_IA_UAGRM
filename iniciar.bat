@echo off
title Validador IA UAGRM - Orquestador
color 0b

echo ===============================================================
echo      SISTEMA DE VALIDACION IA - ARQUITECTURA DESACOPLADA
echo ===============================================================
echo.

echo [1/3] Verificando entorno virtual...
if not exist "venv\Scripts\activate.bat" (
    echo ERROR: No se encontro el entorno virtual en la carpeta venv.
    pause
    exit
)

echo [2/3] Encendiendo Motor Logico (Backend FastAPI)...
:: El comando 'start' abre un proceso paralelo independiente.
:: Esto evita que la terminal se quede congelada esperando al backend.
start "UAGRM Backend API (FastAPI)" cmd /k "call venv\Scripts\activate & python backend/main.py"

echo.
echo Esperando 4 segundos para que la API encienda correctamente...
timeout /t 4 /nobreak > nul

echo.
echo [3/3] Encendiendo Interfaz de Usuario (Frontend Streamlit)...
:: Ejecutamos Streamlit en esta misma ventana principal
call venv\Scripts\activate
streamlit run frontend/app.py

pause