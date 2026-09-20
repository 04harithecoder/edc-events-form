import json
import logging

from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .emails import send_registration_confirmation
from .models import Event, Registration
from .payments import PaymentGatewayError, create_razorpay_order, verify_webhook_signature
from .serializers import (
    EventDetailSerializer,
    EventListSerializer,
    RegistrationCreateSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public: events
# ---------------------------------------------------------------------------

class OpenEventListView(ListAPIView):
    """Current/open events — PRD Events page 'Current/Open' section."""

    serializer_class = EventListSerializer

    def get_queryset(self):
        return Event.objects.filter(status=Event.STATUS_OPEN).order_by("event_date")


class PastEventListView(ListAPIView):
    """Past events — PRD Events page 'Past Events' section."""

    serializer_class = EventListSerializer

    def get_queryset(self):
        return Event.objects.filter(status=Event.STATUS_PAST).order_by("-event_date")


class EventDetailView(RetrieveAPIView):
    """Full detail view for a single event's registration page."""

    serializer_class = EventDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return Event.objects.filter(status__in=Event.PUBLIC_STATUSES)


# ---------------------------------------------------------------------------
# Public: registration
# ---------------------------------------------------------------------------

class RegisterView(APIView):
    """
    Creates a guest registration for an event.

    Handles both flows from TRD Section 5:
      - Free event: registration is confirmed immediately, email sent.
      - Paid event: registration created as 'pending', a Razorpay Order is
        created, and the order details are returned so the frontend can
        open Razorpay Checkout. The registration is only confirmed later,
        by the webhook.

    Capacity + duplicate-email checks happen inside a DB transaction with
    select_for_update() on the Event row, so two near-simultaneous
    submissions for the last slot can't both succeed (TRD edge case:
    capacity race condition must be atomic, not UI-side).
    """

    def post(self, request, slug):
        event = get_object_or_404(
            Event.objects.filter(status__in=Event.PUBLIC_STATUSES), slug=slug
        )

        serializer = RegistrationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not event.is_registration_open:
            return Response(
                {"detail": "Registration is closed for this event (deadline passed, "
                           "event closed, or it is full)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                # Lock the Event row so concurrent submissions serialize here.
                locked_event = Event.objects.select_for_update().get(pk=event.pk)

                if locked_event.is_full:
                    return Response(
                        {"detail": "This event just reached capacity."},
                        status=status.HTTP_409_CONFLICT,
                    )

                if locked_event.fee and locked_event.fee > 0:
                    registration = Registration.objects.create(
                        event=locked_event,
                        payment_status=Registration.PAYMENT_PENDING,
                        **data,
                    )
                else:
                    registration = Registration.objects.create(
                        event=locked_event,
                        payment_status=Registration.PAYMENT_FREE,
                        **data,
                    )
        except IntegrityError:
            # Unique (event, email) constraint — duplicate registration.
            return Response(
                {"detail": "This email is already registered for this event."},
                status=status.HTTP_409_CONFLICT,
            )

        if registration.payment_status == Registration.PAYMENT_FREE:
            send_registration_confirmation(registration)
            return Response(
                {
                    "registration_id": registration.id,
                    "payment_status": registration.payment_status,
                    "message": "Registration confirmed.",
                },
                status=status.HTTP_201_CREATED,
            )

        # Paid event: create the Razorpay order and hand it to the frontend.
        try:
            order = create_razorpay_order(
                amount_rupees=event.fee,
                receipt=f"reg-{registration.id}",
                notes={"event_id": event.id, "registration_id": registration.id},
            )
        except PaymentGatewayError as exc:
            logger.error("Razorpay order creation failed: %s", exc)
            return Response(
                {"detail": "Payment gateway is temporarily unavailable. "
                           "Please try again shortly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        registration.razorpay_order_id = order["id"]
        registration.save(update_fields=["razorpay_order_id"])

        return Response(
            {
                "registration_id": registration.id,
                "payment_status": registration.payment_status,
                "razorpay_order_id": order["id"],
                "razorpay_key_id": _razorpay_key_id_for_frontend(),
                "amount": order["amount"],
                "currency": order["currency"],
            },
            status=status.HTTP_201_CREATED,
        )


def _razorpay_key_id_for_frontend():
    from django.conf import settings

    return settings.RAZORPAY_KEY_ID


# ---------------------------------------------------------------------------
# Razorpay webhook — the source of truth for payment confirmation.
# ---------------------------------------------------------------------------

@csrf_exempt
def razorpay_webhook(request):
    """
    POST /api/webhooks/razorpay/

    Verifies the signature, then updates the matching Registration's
    payment_status. Idempotent: replays of the same event just re-apply
    the same status, so a retried webhook (e.g. after a transient error)
    is safe.
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    signature = request.headers.get("X-Razorpay-Signature", "")
    body = request.body

    if not verify_webhook_signature(request_body=body, signature_header=signature):
        logger.warning("Rejected Razorpay webhook with invalid signature.")
        return HttpResponse(status=400)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event_type = payload.get("event", "")
    payment_entity = (
        payload.get("payload", {}).get("payment", {}).get("entity", {})
    )
    order_id = payment_entity.get("order_id")
    payment_id = payment_entity.get("id")

    if not order_id:
        return HttpResponse(status=200)  # nothing actionable, ack anyway

    try:
        with transaction.atomic():
            registration = (
                Registration.objects.select_for_update()
                .select_related("event")
                .get(razorpay_order_id=order_id)
            )

            if event_type == "payment.captured":
                if registration.payment_status != Registration.PAYMENT_PAID:
                    registration.payment_status = Registration.PAYMENT_PAID
                    registration.payment_gateway_ref_id = payment_id
                    registration.save(
                        update_fields=["payment_status", "payment_gateway_ref_id", "updated_at"]
                    )
                    send_registration_confirmation(registration)
            elif event_type == "payment.failed":
                registration.payment_status = Registration.PAYMENT_FAILED
                registration.payment_gateway_ref_id = payment_id
                registration.save(
                    update_fields=["payment_status", "payment_gateway_ref_id", "updated_at"]
                )
    except Registration.DoesNotExist:
        # Log for manual reconciliation (TRD risk table) — a webhook
        # arrived for an order_id we don't recognize.
        logger.error(
            "Razorpay webhook for unknown order_id=%s (event=%s, payment_id=%s)",
            order_id, event_type, payment_id,
        )

    return HttpResponse(status=200)


# ---------------------------------------------------------------------------
# Contact info — PRD Contacts page (single EDC email)
# ---------------------------------------------------------------------------

def contact_info(request):
    from django.conf import settings

    return JsonResponse({"email": settings.EDC_CONTACT_EMAIL})
