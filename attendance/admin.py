from django.contrib import admin

from .models import CheckIn, DropInVisitor, QRCode, TrainingClass


@admin.register(TrainingClass)
class TrainingClassAdmin(admin.ModelAdmin):
    list_display = ["title", "academy", "class_type", "scheduled_at", "duration_minutes"]
    list_filter = ["class_type", "academy"]
    search_fields = ["title"]


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = ["athlete", "training_class", "method", "checked_in_at"]
    list_filter = ["method"]


@admin.register(QRCode)
class QRCodeAdmin(admin.ModelAdmin):
    list_display = ["training_class", "token", "expires_at", "is_active"]


@admin.register(DropInVisitor)
class DropInVisitorAdmin(admin.ModelAdmin):
    list_display = ["first_name", "last_name", "email", "academy", "status", "expires_at"]
    list_filter = ["status", "academy"]
