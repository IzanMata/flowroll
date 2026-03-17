#!/bin/bash
# FlowRoll - Quick Start Script
# Configura la aplicación para desarrollo rápido con SQLite

set -e

echo "🚀 FlowRoll - Quick Start Setup"
echo "================================"

# Activar entorno virtual
echo "📦 Activando entorno virtual..."
source venv/bin/activate

# Configurar variables de entorno para SQLite
echo "⚙️  Configurando variables de entorno..."
export DJANGO_SETTINGS_MODULE=config.settings.development_sqlite
export DEBUG=True

# Crear base de datos y ejecutar migraciones
echo "🗄️  Creando base de datos SQLite y ejecutando migraciones..."
python manage.py migrate

# Crear datos de catálogo (cinturones, técnicas)
echo "📚 Cargando datos de catálogo..."
python manage.py loaddata fixtures/belts.json 2>/dev/null || echo "   ⚠️  Archivo belts.json no encontrado, creando cinturones básicos..."

# Crear cinturones básicos si no existen
python manage.py shell << 'EOF'
from core.models import Belt

# Crear cinturones básicos si no existen
belt_data = [
    ('white', 'White Belt', 1),
    ('blue', 'Blue Belt', 2),
    ('purple', 'Purple Belt', 3),
    ('brown', 'Brown Belt', 4),
    ('black', 'Black Belt', 5),
]

for color, description, order in belt_data:
    belt, created = Belt.objects.get_or_create(
        color=color,
        defaults={'description': description, 'order': order}
    )
    if created:
        print(f"✅ Cinturón {description} creado")
EOF

# Crear superusuario
echo ""
echo "👨‍💼 Creando superusuario..."
echo "   Usa estos datos para acceder al admin:"
echo "   - Username: admin"
echo "   - Email: admin@flowroll.com"
echo "   - Password: admin123"
echo ""

python manage.py shell << 'EOF'
from django.contrib.auth.models import User

# Crear superusuario si no existe
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser(
        username='admin',
        email='admin@flowroll.com',
        password='admin123'
    )
    print("✅ Superusuario 'admin' creado exitosamente")
else:
    print("ℹ️  Superusuario 'admin' ya existe")
EOF

# Crear academia y usuarios de ejemplo
echo ""
echo "🏛️  Creando datos de ejemplo..."

python manage.py shell << 'EOF'
from django.contrib.auth.models import User
from academies.models import Academy
from core.models import AcademyMembership
from athletes.models import AthleteProfile

# Crear academia de ejemplo
academy, created = Academy.objects.get_or_create(
    name="Demo BJJ Academy",
    defaults={'city': 'Demo City'}
)
if created:
    print("✅ Academia 'Demo BJJ Academy' creada")

# Crear usuarios de ejemplo
users_data = [
    ('profesor1', 'profesor1@demo.com', 'Profesor', 'Demo', 'PROFESSOR'),
    ('estudiante1', 'estudiante1@demo.com', 'Estudiante', 'Uno', 'STUDENT'),
    ('estudiante2', 'estudiante2@demo.com', 'Estudiante', 'Dos', 'STUDENT'),
]

for username, email, first_name, last_name, role in users_data:
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            'email': email,
            'first_name': first_name,
            'last_name': last_name
        }
    )
    if created:
        user.set_password('demo123')
        user.save()
        print(f"✅ Usuario '{username}' creado")

    # Crear membresía en academia
    membership, created = AcademyMembership.objects.get_or_create(
        user=user,
        academy=academy,
        defaults={'role': role}
    )
    if created:
        print(f"✅ Membresía de '{username}' creada como {role}")

    # Crear perfil de atleta
    profile, created = AthleteProfile.objects.get_or_create(
        user=user,
        defaults={
            'academy': academy,
            'belt': 'white' if role == 'STUDENT' else 'black',
            'stripes': 0 if role == 'STUDENT' else 0,
            'weight': 75.0,
            'role': role
        }
    )
    if created:
        print(f"✅ Perfil de atleta para '{username}' creado")
EOF

echo ""
echo "🎉 ¡Configuración completada!"
echo "================================"
echo ""
echo "📝 Usuarios creados:"
echo "   👨‍💼 Admin:       admin / admin123"
echo "   👨‍🏫 Profesor:    profesor1 / demo123"
echo "   👨‍🎓 Estudiante:  estudiante1 / demo123"
echo "   👩‍🎓 Estudiante:  estudiante2 / demo123"
echo ""
echo "🌐 Para iniciar el servidor:"
echo "   export DJANGO_SETTINGS_MODULE=config.settings.development_sqlite"
echo "   python manage.py runserver"
echo ""
echo "📱 URLs importantes:"
echo "   🏠 Aplicación: http://localhost:8000/"
echo "   ⚙️  Admin:      http://localhost:8000/admin/"
echo "   📚 API Docs:   http://localhost:8000/api/docs/"
echo ""