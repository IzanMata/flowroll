#!/bin/bash
# Script para configurar aliases permanentes de FlowRoll

echo "🔧 Configurando aliases para FlowRoll..."

# Agregar aliases al .bashrc si no existen
if ! grep -q "# FlowRoll aliases" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# FlowRoll aliases" >> ~/.bashrc
    echo "alias flowroll='cd ~/Code/flowroll && unset DJANGO_SETTINGS_MODULE && python3 manage.py'" >> ~/.bashrc
    echo "alias flowroll-server='cd ~/Code/flowroll && unset DJANGO_SETTINGS_MODULE && python3 manage.py runserver 0.0.0.0:8080'" >> ~/.bashrc
    echo "alias flowroll-clean='cd ~/Code/flowroll && ./start_flowroll.sh'" >> ~/.bashrc
    echo "✅ Aliases agregados a ~/.bashrc"
else
    echo "ℹ️ Aliases ya existen en ~/.bashrc"
fi

echo ""
echo "🎯 Aliases disponibles:"
echo "  flowroll <comando>     - Ejecutar comandos Django (con entorno limpio)"
echo "  flowroll-server        - Iniciar servidor en puerto 8080"
echo "  flowroll-clean         - Usar script con entorno completamente limpio"
echo ""
echo "Para usar ahora mismo:"
echo "  source ~/.bashrc"
echo "  flowroll-server"