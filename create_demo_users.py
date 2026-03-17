#!/usr/bin/env python
"""
Script para crear usuarios de ejemplo en FlowRoll
"""
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development_sqlite')
django.setup()

from django.contrib.auth.models import User
from academies.models import Academy
from core.models import AcademyMembership
from athletes.models import AthleteProfile

def create_demo_data():
    print("🏛️  Creando datos de ejemplo...")

    # Crear academia de ejemplo
    academy, created = Academy.objects.get_or_create(
        name="Demo BJJ Academy",
        defaults={'city': 'Demo City'}
    )
    if created:
        print("✅ Academia 'Demo BJJ Academy' creada")
    else:
        print("ℹ️  Academia 'Demo BJJ Academy' ya existe")

    # Crear usuarios de ejemplo
    users_data = [
        ('profesor1', 'profesor1@demo.com', 'Profesor', 'Demo', 'PROFESSOR', 'black'),
        ('estudiante1', 'estudiante1@demo.com', 'Estudiante', 'Uno', 'STUDENT', 'white'),
        ('estudiante2', 'estudiante2@demo.com', 'Estudiante', 'Dos', 'STUDENT', 'blue'),
        ('estudiante3', 'estudiante3@demo.com', 'Estudiante', 'Tres', 'STUDENT', 'purple'),
    ]

    for username, email, first_name, last_name, role, belt in users_data:
        # Crear usuario
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
        else:
            print(f"ℹ️  Usuario '{username}' ya existe")

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
                'belt': belt,
                'stripes': 0,
                'weight': 75.0,
                'role': role
            }
        )
        if created:
            print(f"✅ Perfil de atleta para '{username}' creado ({belt} belt)")

    print("\n🎉 ¡Datos de ejemplo creados exitosamente!")

if __name__ == '__main__':
    create_demo_data()