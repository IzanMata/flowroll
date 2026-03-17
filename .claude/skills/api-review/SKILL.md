---
name: api-review
triggers: ["api review", "endpoint", "viewset", "serializer", "permission", "auth", "jwt", "openapi", "swagger", "schema", "drf", "rest"]
description: "Invoke when reviewing, designing, or documenting API endpoints."
---

# API Review

## Auth

```
POST /api/auth/token/          # obtain: username + password → access (1h) + refresh (7d)
POST /api/auth/token/refresh/  # rotate refresh token (old token blacklisted)
```

All endpoints require `Authorization: Bearer <access_token>` except the token endpoints.

## URL structure

```
/api/<app>/          # list + create
/api/<app>/<id>/     # retrieve + update + destroy
/api/<app>/<id>/<action>/   # custom actions
/api/schema/         # OpenAPI 3.1 JSON
/api/docs/           # Swagger UI
/api/redoc/          # ReDoc
```

## Multi-tenancy requirement

Every list endpoint **must** accept `?academy=<id>` and return `.none()` when absent:

```python
def get_queryset(self):
    academy_id = self.request.query_params.get("academy")
    if not academy_id:
        return MyModel.objects.none()
    # verify membership before leaking data
    if not request.user.is_superuser:
        if not AcademyMembership.objects.filter(user=..., academy_id=academy_id, is_active=True).exists():
            return MyModel.objects.none()
    return MyModel.objects.filter(academy_id=academy_id)
```

## Permission checklist

- Default: `IsAuthenticated` (set globally in DRF settings)
- Read-only data (class schedules, techniques): `IsAcademyMember`
- Write operations (create classes, check-ins): `IsAcademyProfessor`
- Academy config changes: `IsAcademyOwner`
- Use `get_permissions()` to differentiate by action:

```python
def get_permissions(self):
    if self.action == "create":
        return [IsAcademyProfessor()]
    return [IsAcademyMember()]
```

## ViewSet conventions

- Always `serializer.is_valid(raise_exception=True)` — never check the return value manually
- Thin viewsets: validate → call service/selector → return Response
- `swagger_fake_view` guard in `get_queryset` for drf-spectacular schema generation:

```python
if getattr(self, "swagger_fake_view", False):
    return MyModel.objects.none()
```

- `basename` required when viewset has no `queryset` class attribute:

```python
router.register("", MyViewSet, basename="mymodel")
```

## @extend_schema usage

```python
from drf_spectacular.utils import extend_schema

@extend_schema(
    request=InputSerializer,
    responses=OutputSerializer,
    summary="One-line description",
    description="Longer markdown description.",
)
@action(detail=True, methods=["post"])
def my_action(self, request, pk=None):
    ...
```

## Serializer conventions

- `read_only_fields` for auto-managed fields (`created_at`, `status`, `billed`)
- Convenience display fields via `source=`: `plan_name = CharField(source="plan.name", read_only=True)`
- Separate input/output serializers for complex actions (e.g. `ManualCheckInSerializer` vs `CheckInSerializer`)

## Security checklist for new endpoints

- [ ] Queryset scoped to `academy` param
- [ ] Membership verified before returning data
- [ ] Winner/participant IDs validated against the specific record (not just any valid FK)
- [ ] Integer inputs clamped to safe ranges (e.g. `expiry_minutes`)
- [ ] `select_for_update()` inside `transaction.atomic` for concurrency-sensitive writes
