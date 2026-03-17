#!/bin/bash
# Wrapper para comandos Django con SQLite

# Función para ejecutar comandos Django con SQLite
django_sqlite() {
    DJANGO_SETTINGS_MODULE=config.settings.development_sqlite python3 manage.py "$@"
}

# Exportar la función
export -f django_sqlite

echo "🎯 Función 'django_sqlite' cargada!"
echo "📋 Uso: django_sqlite <comando>"
echo "   Ejemplos:"
echo "     django_sqlite createsuperuser"
echo "     django_sqlite runserver"
echo "     django_sqlite migrate"
echo "     django_sqlite shell"