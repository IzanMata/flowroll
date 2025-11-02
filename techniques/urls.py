from rest_framework.routers import DefaultRouter

from .views import (BeltViewSet, TechniqueCategoryViewSet,
                    TechniqueVariationViewSet, TechniqueViewSet)

router = DefaultRouter()
router.register(r"techniques", TechniqueViewSet)
router.register(r"categories", TechniqueCategoryViewSet)
router.register(r"belts", BeltViewSet)
router.register(r"variations", TechniqueVariationViewSet)
urlpatterns = router.urls
