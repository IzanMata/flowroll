import json
import os
import sys

import django

# Añadir la carpeta del proyecto al path
sys.path.append("/media/DebianShare/Projects/flowroll")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

# Imports de modelos
from techniques.models import Technique, TechniqueVariation

# Abrir el JSON
with open("techniques_variations.json", "r") as f:
    data = json.load(f)

for technique_name, details in data.items():
    # Crear o recuperar la técnica
    tech, created = Technique.objects.get_or_create(
        name=technique_name, defaults={"url": details.get("url", "")}
    )

    for var in details.get("variations", []):
        # Crear variación solo si no existe
        variation, created_var = TechniqueVariation.objects.get_or_create(
            technique=tech, title=var.get("title", "")
        )
        # Actualizar los videos si hay nuevos
        existing_videos = set(variation.videos or [])
        new_videos = set(var.get("videos", []))
        if new_videos - existing_videos:
            variation.videos = list(existing_videos | new_videos)
            variation.save()

print("¡Datos insertados correctamente en Flowroll!")
