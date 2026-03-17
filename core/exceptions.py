"""
Common exception classes for consistent error handling across the FlowRoll application.
Eliminates inconsistent error handling patterns identified in code review.
"""

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError


class FlowRollException(APIException):
    """Base exception class for all FlowRoll-specific errors."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A business logic error occurred."
    default_code = "business_logic_error"


class AcademyMembershipError(FlowRollException):
    """Raised when user is not a member of the required academy."""
    default_detail = "You are not a member of the required academy."
    default_code = "academy_membership_required"


class AcademyPermissionError(FlowRollException):
    """Raised when user lacks permission to perform action in academy."""
    default_detail = "You do not have permission to perform this action."
    default_code = "academy_permission_denied"


class ResourceNotFoundError(FlowRollException):
    """Raised when a required resource is not found in the academy context."""
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "The requested resource was not found."
    default_code = "resource_not_found"


class BusinessLogicError(FlowRollException):
    """Raised when business logic constraints are violated."""
    default_detail = "Business logic constraint violation."
    default_code = "business_logic_violation"


class ServiceError(FlowRollException):
    """Raised when a service operation fails due to invalid state or constraints."""
    default_detail = "Service operation failed due to invalid state."
    default_code = "service_error"


def standardize_service_error(exc):
    """
    Convert common service exceptions to standardized API exceptions.

    Usage:
        try:
            some_service_call()
        except ValueError as exc:
            raise standardize_service_error(exc)
    """
    if isinstance(exc, ValueError):
        return ServiceError(detail=str(exc))
    elif isinstance(exc, KeyError):
        return ResourceNotFoundError(detail=f"Required resource not found: {str(exc)}")
    elif isinstance(exc, TypeError):
        return ValidationError(detail=f"Invalid data type: {str(exc)}")
    else:
        # For unknown exceptions, wrap in generic business logic error
        return BusinessLogicError(detail=str(exc))
