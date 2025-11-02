from rest_framework.routers import DefaultRouter

from .views import BeltViewSet, TechniqueCategoryViewSet, TechniqueViewSet

router = DefaultRouter()
router.register(r"techniques", TechniqueViewSet)
router.register(r"categories", TechniqueCategoryViewSet)
router.register(r"belts", BeltViewSet)
urlpatterns = router.urls
