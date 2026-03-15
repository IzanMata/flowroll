from rest_framework.routers import DefaultRouter

from .views import MatchViewSet

router = DefaultRouter()
router.register("", MatchViewSet)
urlpatterns = router.urls
