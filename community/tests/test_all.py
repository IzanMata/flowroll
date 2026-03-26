"""
Comprehensive test suite for the community app.

This file imports all test modules to provide a single entry point for running
all community app tests. Run with: python manage.py test community.tests.test_all
"""

# Import all test modules
from .test_models import *
from .test_services import *
from .test_selectors import *
from .test_serializers import *


# Test summary for documentation
"""
Community App Test Coverage:

Models (test_models.py):
- Achievement: creation, validation, string representation, constraints
- AthleteAchievement: creation, uniqueness, cascading deletes, timestamps
- OpenMatSession: creation, ordering, property methods, indexes
- OpenMatRSVP: creation, constraints, status validation, cascade behavior

Services (test_services.py):
- AchievementService: automatic evaluation/awarding, manual awarding, trigger logic
- StatsAggregationService: streak calculation, stats aggregation
- OpenMatService: RSVP management, transaction handling

Selectors (test_selectors.py):
- get_upcoming_open_mats: filtering, annotation, performance optimization
- get_achievements_for_athlete: filtering, select_related optimization

Serializers (test_serializers.py):
- AchievementSerializer: serialization/deserialization, validation
- AthleteAchievementSerializer: nested serialization, read-only fields
- OpenMatSessionSerializer: annotated fields, optional parameters
- OpenMatRSVPSerializer: source field mapping, status validation
- AthleteStatsSerializer: read-only stats validation

Total test count: ~80+ individual test methods covering:
- Model behavior and constraints
- Business logic and edge cases
- Database performance optimizations
- API serialization/deserialization
- Error handling and validation
"""