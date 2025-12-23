# 🥋 FlowRoll --- Tu plataforma inteligente de Jiu-Jitsu

FlowRoll es una aplicación diseñada para **organizar, visualizar y
estudiar técnicas de Jiu-Jitsu** de forma clara, modular y escalable.\
Construida con **Django** en el backend y preparada para integrarse con
cualquier frontend moderno (*Next.js, React, mobile apps, etc.*).

## 🚀 Características principales

-   **📚 Base de datos de técnicas** Técnicas, variaciones, enlaces
    entre ellas y estructura tipo *grapheado*.
-   **🧬 Sistema de cinturones** Gestión de técnicas según nivel (Blanco
    → Negro).
-   **🔗 Relación de técnicas como nodos** Cada técnica puede actuar
    como nodo conectado a otras (transiciones, counters, combos).
-   **🛠 API REST** Endpoints para listar, filtrar y expandir técnicas.
-   **⚡ Importación automática de datos** Script que importa técnicas y
    variaciones desde JSON mediante Django ORM.

## 🏗️ Tecnologías

-   Python 3.x
-   Django 5
-   Django REST Framework (DRF)
-   PostgreSQL (o SQLite para desarrollo)
-   Docker (opcional)

## 📁 Estructura del proyecto

    flowroll/
     ├── config/              # Configuración de Django
     ├── techniques/          # App principal: modelos, views, urls, serializers
     ├── scripts/             # Scripts externos (importadores JSON, etc.)
     ├── requirements.txt
     └── README.md

## 🧩 Modelos principales

### `Belt`

Representa los cinturones del Jiu-Jitsu.

### `Technique`

El núcleo del sistema. Cada técnica es un *nodo* con: - nombre -
descripción - cinturón recomendado - conexiones/transiciones

### `TechniqueVariation`

Variaciones específicas de una técnica base.

## 🔌 API Endpoints (ejemplo)

    GET /api/techniques/             # Lista de técnicas
    GET /api/techniques/<id>/        # Detalle de técnica
    GET /api/techniques/<id>/graph   # Nodos conectados
    GET /api/belts/                  # Cinturones

## 📦 Instalación

``` bash
git clone https://github.com/tuusuario/flowroll.git
cd flowroll

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## 📥 Importar técnicas desde JSON

``` bash
python scripts/import_techniques.py
```

El script: - carga Django - lee un `.json` con técnicas - crea técnicas
y variaciones - evita duplicados

## 🎯 Roadmap

-   [ ] Visualización gráfica tipo *grappling tree*
-   [ ] Sistema de usuarios y progresión
-   [ ] Recomendación de técnicas según nivel
-   [ ] Tags dinámicos tipo "no-gi", "gi", "takedown", etc.
-   [ ] Modo entrenamiento (listas y orden del día)

## 🤝 Contribuir

1.  Haz un fork\
2.  Crea una rama\
3.  Propón mejoras o nuevas técnicas\
4.  Pull request 🤜🤛

## 🐉 Licencia

MIT. Haz lo que quieras, pero entrena fuerte.