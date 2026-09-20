"""
Razorpay integration (TRD Section 5).

Flow:
  1. Student submits registration form -> we create a pending Registration
     and a Razorpay Order (create_razorpay_order).
  2. Frontend opens Razorpay Checkout with that order_id.
  3. Razorpay calls our webhook (/api/webhooks/razorpay/) on success/failure.
  4. We verify the webhook signature (critical — never trust an unverified
     webhook) and update Registration.payment_status accordingly.

The webhook is the source of truth, not the browser's post-payment
redirect — this is what makes the flow replayable/idempotent and avoids
the "payment succeeded but registration wasn't recorded" edge case from
the PRD.
"""

import hashlib
import hmac
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import razorpay
except ImportError:  # pragma: no cover - library may not be installed in dev sandbox
    razorpay = None


class PaymentGatewayError(Exception):
    pass


def get_razorpay_client():
    if razorpay is None:
        raise PaymentGatewayError(
            "razorpay package not installed. Run: pip install razorpay"
        )
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise PaymentGatewayError("Razorpay keys are not configured in the environment.")
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_razorpay_order(*, amount_rupees, receipt, notes=None):
    """
    Creates a Razorpay Order for the given amount (in rupees; Razorpay's
    API wants paise, so we convert). Returns the raw order dict, which
    includes 'id' — store this on the Registration as razorpay_order_id.
    """
    client = get_razorpay_client()
    amount_paise = int(round(amount_rupees * 100))
    order = client.order.create(
        {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "notes": notes or {},
            "payment_capture": 1,
        }
    )
    return order


def verify_webhook_signature(*, request_body: bytes, signature_header: str) -> bool:
    """
    Verifies the X-Razorpay-Signature header against the raw request body
    using the webhook secret (set in the Razorpay dashboard AND in our
    RAZORPAY_WEBHOOK_SECRET env var). Returns True only if they match.
    """
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        logger.error("RAZORPAY_WEBHOOK_SECRET is not configured — refusing to trust webhook.")
        return False
    if not signature_header:
        return False

    expected_signature = hmac.new(
        key=settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        msg=request_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature_header)
