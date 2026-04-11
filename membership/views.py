from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
import json
import logging

from academies.models import Academy

from .serializers import (EnrollmentSerializer, MembershipPlanSerializer, SubscriptionSerializer,
                         StripePaymentMethodSerializer, StripeSubscriptionSerializer, StripePaymentSerializer,
                         AttachPaymentMethodSerializer, StripeEnrollmentSerializer,
                         SeminarStripePaymentSerializer, CreatePaymentIntentSerializer,
                         # Stripe Connect serializers
                         StripeConnectedAccountSerializer, PlatformCommissionSerializer, MarketplaceTransactionSerializer,
                         AcademyEarningsSerializer, CreateConnectedAccountSerializer, CreateOnboardingLinkSerializer,
                         MarketplaceEnrollmentSerializer, MarketplaceSeminarPaymentSerializer,
                         EarningsSummarySerializer, CommissionConfigurationSerializer)
from .models import (Subscription, Seminar, StripePaymentMethod, StripeSubscription,
                    StripeConnectedAccount, MarketplaceTransaction, AcademyEarnings)
from .services import (EnrollmentService, LeaveAcademyService, SubscriptionService,
                      StripePaymentMethodService, StripeSubscriptionService, StripePaymentService,
                      StripeWebhookService, SeminarService,
                      # Stripe Connect services
                      StripeConnectService, PlatformCommissionService, MarketplacePaymentService,
                      MarketplaceAnalyticsService)

logger = logging.getLogger(__name__)


class EnrollView(APIView):
    """
    Join an academy and subscribe to one of its membership plans.

    Creates an AcademyMembership (STUDENT role), an AthleteProfile if the user
    does not have one yet, and a Subscription to the chosen plan.

    Request body:
        academy  — int, ID of the academy to join
        plan     — int, ID of an active MembershipPlan belonging to that academy
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        academy = serializer.validated_data["academy"]
        plan = serializer.validated_data["plan"]

        try:
            result = EnrollmentService.enroll(
                user=request.user, academy=academy, plan=plan
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(
            {
                "academy_id": result["membership"].academy_id,
                "role": result["membership"].role,
                "subscription": SubscriptionSerializer(result["subscription"]).data,
            },
            status=201,
        )


class LeaveAcademyView(APIView):
    """
    Leave an academy voluntarily.

    Deactivates the caller's AcademyMembership and cancels any active
    subscriptions at that academy.  OWNER role cannot leave — they must
    transfer ownership first.

    POST /api/membership/{academy_id}/leave/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, academy_id):
        try:
            academy = Academy.objects.get(pk=academy_id)
        except Academy.DoesNotExist:
            return Response({"detail": "Academy not found."}, status=404)

        try:
            LeaveAcademyService.leave(user=request.user, academy=academy)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response({"detail": "You have left the academy."}, status=200)


class CancelSubscriptionView(APIView):
    """
    Cancel an active subscription.

    POST /api/membership/subscriptions/{id}/cancel/
    Returns 200 with the updated subscription.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, subscription_id):
        try:
            subscription = Subscription.objects.select_related("athlete__user").get(
                pk=subscription_id
            )
        except Subscription.DoesNotExist:
            return Response({"detail": "Subscription not found."}, status=404)

        try:
            updated = SubscriptionService.cancel(subscription, user=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(SubscriptionSerializer(updated).data, status=200)


# ---------------------------------------------------------------------------
# Stripe Payment Views
# ---------------------------------------------------------------------------


class StripeEnrollView(APIView):
    """
    Join an academy with Stripe billing for recurring plans.

    For monthly/annual plans, creates Stripe subscription.
    For class passes/drop-ins, falls back to standard enrollment.

    POST /api/membership/stripe-enroll/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = StripeEnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        academy = serializer.validated_data["academy"]
        plan = serializer.validated_data["plan"]
        payment_method_id = serializer.validated_data.get("payment_method_id")
        trial_days = serializer.validated_data.get("trial_days", 0)

        try:
            result = EnrollmentService.enroll_with_stripe(
                user=request.user,
                academy=academy,
                plan=plan,
                payment_method_id=payment_method_id,
                trial_days=trial_days
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        response_data = {
            "academy_id": result["membership"].academy_id,
            "role": result["membership"].role,
            "subscription": SubscriptionSerializer(result["subscription"]).data,
        }

        if result.get("stripe_subscription"):
            response_data["stripe_subscription"] = StripeSubscriptionSerializer(
                result["stripe_subscription"]
            ).data

        if result.get("client_secret"):
            response_data["client_secret"] = result["client_secret"]

        return Response(response_data, status=201)


class AttachPaymentMethodView(APIView):
    """
    Attach a payment method to the authenticated user's Stripe customer.

    POST /api/membership/payment-methods/attach/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AttachPaymentMethodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment_method_id = serializer.validated_data["payment_method_id"]
        set_as_default = serializer.validated_data["set_as_default"]

        try:
            payment_method = StripePaymentMethodService.attach_payment_method(
                user=request.user,
                payment_method_id=payment_method_id,
                set_as_default=set_as_default
            )
        except Exception as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(
            StripePaymentMethodSerializer(payment_method).data,
            status=201
        )


class PaymentMethodListView(APIView):
    """
    List payment methods for the authenticated user.

    GET /api/membership/payment-methods/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        payment_methods = StripePaymentMethod.objects.filter(
            stripe_customer__user=request.user,
            is_active=True
        ).order_by("-is_default", "-created_at")

        serializer = StripePaymentMethodSerializer(payment_methods, many=True)
        return Response(serializer.data)


class DetachPaymentMethodView(APIView):
    """
    Detach a payment method from the user's account.

    DELETE /api/membership/payment-methods/{payment_method_id}/
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, payment_method_id):
        try:
            StripePaymentMethodService.detach_payment_method(
                user=request.user,
                payment_method_id=payment_method_id
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except Exception as exc:
            return Response({"detail": "Failed to detach payment method."}, status=500)

        return Response({"detail": "Payment method detached successfully."}, status=200)


class StripeSubscriptionListView(APIView):
    """
    List Stripe subscriptions for the authenticated user.

    GET /api/membership/stripe-subscriptions/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscriptions = StripeSubscription.objects.filter(
            stripe_customer__user=request.user
        ).select_related("subscription", "subscription__plan").order_by("-created_at")

        serializer = StripeSubscriptionSerializer(subscriptions, many=True)
        return Response(serializer.data)


class CancelStripeSubscriptionView(APIView):
    """
    Cancel a Stripe subscription.

    POST /api/membership/stripe-subscriptions/{subscription_id}/cancel/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, subscription_id):
        try:
            stripe_subscription = StripeSubscriptionService.cancel_subscription(
                user=request.user,
                subscription_id=subscription_id
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except Exception as exc:
            logger.error(f"Failed to cancel subscription {subscription_id}: {exc}")
            return Response({"detail": "Failed to cancel subscription."}, status=500)

        return Response(
            StripeSubscriptionSerializer(stripe_subscription).data,
            status=200
        )


class SeminarStripePaymentView(APIView):
    """
    Register for a seminar with Stripe payment.

    POST /api/membership/seminars/stripe-register/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SeminarStripePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        seminar = serializer.validated_data["seminar"]

        try:
            athlete = request.user.profile
        except AttributeError:
            return Response({"detail": "User must have an athlete profile."}, status=400)

        try:
            result = SeminarService.register_with_stripe_payment(
                athlete=athlete,
                seminar=seminar,
                user=request.user
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        response_data = {
            "registration": {
                "id": result["registration"].id,
                "status": result["registration"].status,
                "payment_status": result["registration"].payment_status
            }
        }

        if result.get("stripe_payment"):
            response_data["stripe_payment"] = StripePaymentSerializer(
                result["stripe_payment"]
            ).data
            response_data["client_secret"] = result["stripe_payment"].stripe_payment_intent_id

        return Response(response_data, status=201)


class CreatePaymentIntentView(APIView):
    """
    Create a payment intent for one-time payments.

    POST /api/membership/create-payment-intent/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreatePaymentIntentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payment = StripePaymentService.create_payment_intent(
                user=request.user,
                amount=serializer.validated_data["amount"],
                payment_type=serializer.validated_data["payment_type"],
                description=serializer.validated_data["description"],
                academy=serializer.validated_data["academy"],
                metadata=serializer.validated_data.get("metadata", {})
            )
        except Exception as exc:
            logger.error(f"Failed to create payment intent: {exc}")
            return Response({"detail": "Failed to create payment intent."}, status=500)

        return Response({
            "payment_id": payment.id,
            "client_secret": payment.stripe_payment_intent_id,
            "amount": payment.amount,
            "currency": payment.currency
        }, status=201)


# ---------------------------------------------------------------------------
# Stripe Webhooks
# ---------------------------------------------------------------------------


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def stripe_webhook_view(request):
    """
    Handle Stripe webhook events.

    POST /api/membership/stripe-webhook/
    """
    try:
        event_data = json.loads(request.body)

        # Process the webhook
        processed = StripeWebhookService.process_webhook(event_data)

        if processed:
            logger.info(f"Processed webhook event: {event_data.get('type')} - {event_data.get('id')}")
            return HttpResponse("Webhook processed", status=200)
        else:
            logger.info(f"Webhook already processed: {event_data.get('id')}")
            return HttpResponse("Already processed", status=200)

    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        return HttpResponse("Invalid JSON", status=400)
    except Exception as exc:
        logger.error(f"Webhook processing failed: {exc}")
        return HttpResponse("Webhook processing failed", status=500)


# ---------------------------------------------------------------------------
# Stripe Connect (Marketplace) Views
# ---------------------------------------------------------------------------


class CreateConnectedAccountView(APIView):
    """
    Create a Stripe Connect account for an academy.

    POST /api/v1/membership/connect/create-account/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateConnectedAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        academy = serializer.validated_data["academy"]
        country = serializer.validated_data["country"]

        # Check if user has permission to manage this academy
        from core.permissions import IsAcademyOwner
        if not IsAcademyOwner().has_object_permission(request, self, academy):
            return Response({"detail": "Only academy owners can set up Stripe Connect."}, status=403)

        try:
            connected_account = StripeConnectService.create_connected_account(
                academy=academy,
                country=country
            )
        except Exception as exc:
            logger.error(f"Failed to create connected account: {exc}")
            return Response({"detail": "Failed to create Stripe account."}, status=500)

        return Response(
            StripeConnectedAccountSerializer(connected_account).data,
            status=201
        )


class CreateOnboardingLinkView(APIView):
    """
    Create an onboarding link for academy to complete Stripe setup.

    POST /api/v1/membership/connect/onboarding-link/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateOnboardingLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return_url = serializer.validated_data["return_url"]
        refresh_url = serializer.validated_data["refresh_url"]

        # Get academy from query params
        academy_id = request.query_params.get("academy")
        if not academy_id:
            return Response({"detail": "Academy ID required in query params."}, status=400)

        try:
            academy = Academy.objects.get(pk=academy_id)
        except Academy.DoesNotExist:
            return Response({"detail": "Academy not found."}, status=404)

        # Check permissions
        from core.permissions import IsAcademyOwner
        if not IsAcademyOwner().has_object_permission(request, self, academy):
            return Response({"detail": "Only academy owners can manage Stripe setup."}, status=403)

        # Get connected account
        connected_account = StripeConnectService.get_connected_account_for_academy(academy)
        if not connected_account:
            return Response({"detail": "No Stripe Connect account found. Create one first."}, status=400)

        try:
            onboarding_url = StripeConnectService.create_onboarding_link(
                connected_account=connected_account,
                return_url=return_url,
                refresh_url=refresh_url
            )
        except Exception as exc:
            logger.error(f"Failed to create onboarding link: {exc}")
            return Response({"detail": "Failed to create onboarding link."}, status=500)

        return Response({"onboarding_url": onboarding_url}, status=200)


class ConnectedAccountStatusView(APIView):
    """
    Get connected account status for an academy.

    GET /api/v1/membership/connect/status/?academy={academy_id}
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        academy_id = request.query_params.get("academy")
        if not academy_id:
            return Response({"detail": "Academy ID required in query params."}, status=400)

        try:
            academy = Academy.objects.get(pk=academy_id)
        except Academy.DoesNotExist:
            return Response({"detail": "Academy not found."}, status=404)

        # Check permissions
        from core.permissions import IsAcademyMember
        if not IsAcademyMember().has_object_permission(request, self, academy):
            return Response({"detail": "Access denied."}, status=403)

        connected_account = StripeConnectService.get_connected_account_for_academy(academy)
        if not connected_account:
            return Response({"connected": False}, status=200)

        # Sync status with Stripe
        try:
            StripeConnectService.sync_account_status(connected_account)
        except Exception as exc:
            logger.warning(f"Failed to sync account status: {exc}")

        return Response(
            StripeConnectedAccountSerializer(connected_account).data,
            status=200
        )


class CreateDashboardLinkView(APIView):
    """
    Create a dashboard link for academy to access Stripe dashboard.

    POST /api/v1/membership/connect/dashboard-link/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        academy_id = request.query_params.get("academy")
        if not academy_id:
            return Response({"detail": "Academy ID required in query params."}, status=400)

        try:
            academy = Academy.objects.get(pk=academy_id)
        except Academy.DoesNotExist:
            return Response({"detail": "Academy not found."}, status=404)

        # Check permissions
        from core.permissions import IsAcademyOwner
        if not IsAcademyOwner().has_object_permission(request, self, academy):
            return Response({"detail": "Only academy owners can access dashboard."}, status=403)

        connected_account = StripeConnectService.get_connected_account_for_academy(academy)
        if not connected_account:
            return Response({"detail": "No Stripe Connect account found."}, status=400)

        try:
            dashboard_url = StripeConnectService.create_dashboard_link(connected_account)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except Exception as exc:
            logger.error(f"Failed to create dashboard link: {exc}")
            return Response({"detail": "Failed to create dashboard link."}, status=500)

        return Response({"dashboard_url": dashboard_url}, status=200)


class MarketplaceEnrollView(APIView):
    """
    Join an academy with marketplace Stripe Connect payments.

    POST /api/v1/membership/marketplace-enroll/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MarketplaceEnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        academy = serializer.validated_data["academy"]
        plan = serializer.validated_data["plan"]
        payment_method_id = serializer.validated_data.get("payment_method_id")

        try:
            result = EnrollmentService.enroll_with_marketplace(
                user=request.user,
                academy=academy,
                plan=plan,
                payment_method_id=payment_method_id
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except Exception as exc:
            logger.error(f"Marketplace enrollment failed: {exc}")
            return Response({"detail": "Enrollment failed."}, status=500)

        response_data = {
            "academy_id": result["membership"].academy_id,
            "role": result["membership"].role,
            "subscription": SubscriptionSerializer(result["subscription"]).data,
        }

        if result.get("marketplace_transaction"):
            response_data.update({
                "marketplace_transaction": MarketplaceTransactionSerializer(
                    result["marketplace_transaction"]
                ).data,
                "client_secret": result["client_secret"],
                "platform_fee": result["platform_fee"],
                "academy_receives": result["academy_receives"]
            })

        return Response(response_data, status=201)


class MarketplaceSeminarPaymentView(APIView):
    """
    Register for a seminar with marketplace Stripe payment.

    POST /api/v1/membership/marketplace-seminars/register/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MarketplaceSeminarPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        seminar = serializer.validated_data["seminar"]

        try:
            athlete = request.user.profile
        except AttributeError:
            return Response({"detail": "User must have an athlete profile."}, status=400)

        try:
            result = SeminarService.register_with_stripe_payment(
                athlete=athlete,
                seminar=seminar,
                user=request.user
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except Exception as exc:
            logger.error(f"Marketplace seminar registration failed: {exc}")
            return Response({"detail": "Registration failed."}, status=500)

        response_data = {
            "registration": {
                "id": result["registration"].id,
                "status": result["registration"].status,
                "payment_status": result["registration"].payment_status
            }
        }

        if result.get("marketplace_transaction"):
            response_data.update({
                "marketplace_transaction": MarketplaceTransactionSerializer(
                    result["marketplace_transaction"]
                ).data,
                "client_secret": result["client_secret"],
                "platform_fee": result["platform_fee"],
                "academy_receives": result["academy_receives"]
            })

        return Response(response_data, status=201)


class AcademyEarningsView(APIView):
    """
    Get earnings summary for an academy.

    GET /api/v1/membership/earnings/?academy={academy_id}&year={year}&month={month}
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        academy_id = request.query_params.get("academy")
        if not academy_id:
            return Response({"detail": "Academy ID required in query params."}, status=400)

        try:
            academy = Academy.objects.get(pk=academy_id)
        except Academy.DoesNotExist:
            return Response({"detail": "Academy not found."}, status=404)

        # Check permissions - academy members can view earnings
        from core.permissions import IsAcademyMember
        if not IsAcademyMember().has_object_permission(request, self, academy):
            return Response({"detail": "Access denied."}, status=403)

        year = request.query_params.get("year")
        month = request.query_params.get("month")

        try:
            if year:
                year = int(year)
            if month:
                month = int(month)
        except ValueError:
            return Response({"detail": "Invalid year or month."}, status=400)

        try:
            if month:
                # Monthly summary
                summary = MarketplaceAnalyticsService.get_academy_earnings_summary(
                    academy=academy,
                    year=year,
                    month=month
                )
            else:
                # Yearly summary
                summary = MarketplaceAnalyticsService.get_academy_yearly_summary(
                    academy=academy,
                    year=year
                )
        except Exception as exc:
            logger.error(f"Failed to get earnings summary: {exc}")
            return Response({"detail": "Failed to get earnings data."}, status=500)

        serializer = EarningsSummarySerializer(summary)
        return Response(serializer.data, status=200)


class MarketplaceTransactionListView(APIView):
    """
    List marketplace transactions for an academy.

    GET /api/v1/membership/marketplace-transactions/?academy={academy_id}
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        academy_id = request.query_params.get("academy")
        if not academy_id:
            return Response({"detail": "Academy ID required in query params."}, status=400)

        try:
            academy = Academy.objects.get(pk=academy_id)
        except Academy.DoesNotExist:
            return Response({"detail": "Academy not found."}, status=404)

        # Check permissions
        from core.permissions import IsAcademyMember
        if not IsAcademyMember().has_object_permission(request, self, academy):
            return Response({"detail": "Access denied."}, status=403)

        transactions = MarketplaceTransaction.objects.filter(
            academy=academy
        ).select_related(
            "stripe_customer__user", "academy"
        ).order_by("-created_at")

        serializer = MarketplaceTransactionSerializer(transactions, many=True)
        return Response(serializer.data, status=200)


class ConfigureCommissionView(APIView):
    """
    Configure platform commission for an academy or globally.

    POST /api/v1/membership/configure-commission/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CommissionConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        academy = serializer.validated_data.get("academy")
        commission_type = serializer.validated_data["commission_type"]
        percentage_rate = serializer.validated_data.get("percentage_rate")
        fixed_amount = serializer.validated_data.get("fixed_amount")
        effective_from = serializer.validated_data.get("effective_from")

        # Check permissions
        if academy:
            from core.permissions import IsAcademyOwner
            if not IsAcademyOwner().has_object_permission(request, self, academy):
                return Response({"detail": "Only academy owners can configure commission."}, status=403)
        else:
            # Global configuration - only superusers
            if not request.user.is_superuser:
                return Response({"detail": "Only superusers can configure global commission."}, status=403)

        try:
            commission = PlatformCommissionService.create_academy_commission(
                academy=academy,
                commission_type=commission_type,
                percentage_rate=percentage_rate,
                fixed_amount=fixed_amount,
                effective_from=effective_from
            )
        except Exception as exc:
            logger.error(f"Failed to configure commission: {exc}")
            return Response({"detail": "Failed to configure commission."}, status=500)

        return Response(
            PlatformCommissionSerializer(commission).data,
            status=201
        )
