#!/bin/bash
# Script para activar FlowRoll con configuración SQLite

echo "🚀 Activando entorno FlowRoll..."

# Activar entorno virtual
source venv/bin/activate

# Configurar Django para usar SQLite
export DJANGO_SETTINGS_MODULE=config.settings.development_sqlite

echo "✅ Entorno activado!"
echo ""
echo "📋 Comandos disponibles:"
echo "  python manage.py runserver      # Iniciar servidor"
echo "  python manage.py createsuperuser # Crear admin"
echo "  python manage.py shell          # Consola Django"
echo "  python manage.py migrate        # Aplicar migraciones"
echo ""
echo "🌐 URLs:"
echo "  Admin: http://localhost:8000/admin/"
echo "  API:   http://localhost:8000/api/docs/"
echo ""

# Mantener el shell activo con las variables configuradas
bash