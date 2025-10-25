from django.urls import path
from . import views

urlpatterns = [
    path("techniques/", views.TechniqueListView.as_view(), name="technique-list"),
    path("techniques/<int:pk>/", views.TechniqueDetailView.as_view(), name="technique-detail"),
    path("categories/", views.TechniqueCategoryListView.as_view(), name="category-list"),
]
