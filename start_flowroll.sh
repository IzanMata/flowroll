#!/bin/bash
# Script para iniciar FlowRoll con entorno limpio
# Uso: ./start_flowroll.sh [comando]

echo "🚀 Iniciando FlowRoll con entorno limpio..."

if [ "$#" -eq 0 ]; then
    # Sin argumentos: iniciar servidor
    echo "🌐 Iniciando servidor en http://localhost:8080"
    env -i bash -c "source venv/bin/activate && python3 manage.py runserver 0.0.0.0:8080"
else
    # Con argumentos: ejecutar comando específico
    echo "📋 Ejecutando: manage.py $*"
    env -i bash -c "source venv/bin/activate && python3 manage.py $*"
fi