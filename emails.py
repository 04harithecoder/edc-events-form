"""
Confirmation email sending (PRD: "I receive a confirmation on-screen
and/or email after registering").

Sent on a background thread so the registration HTTP response never
blocks on SMTP/API latency (TRD non-functional requirement: confirm
within ~2-3 seconds). This is intentionally simple — no Celery/Redis —
appropriate at this scale (~250 registrants/event). If email volume or
reliability needs grow, swap this module's send() for a Celery task
without touching call sites.
"""

import logging
import threading

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _send_in_background(subject, message, recipient_list):
    def _send():
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_list,
                fail_silently=False,
            )
        except Exception:
            # Don't crash the request thread; log so an admin can spot
            # delivery failures (TRD Monitoring section flags Sentry as a
            # nice-to-have for exactly this).
            logger.exception("Failed to send confirmation email to %s", recipient_list)

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()


def send_registration_confirmation(registration):
    event = registration.event
    subject = f"You're registered: {event.title}"

    if registration.payment_status == registration.PAYMENT_PAID:
        payment_line = "Your payment has been received."
    elif registration.payment_status == registration.PAYMENT_FREE:
        payment_line = "This is a free event — no payment needed."
    else:
        payment_line = (
            "Note: your payment status is not yet confirmed. If you believe "
            f"you paid but this doesn't update, contact {settings.EDC_CONTACT_EMAIL}."
        )

    message = (
        f"Hi {registration.name},\n\n"
        f"You're registered for \"{event.title}\".\n\n"
        f"Date: {event.event_date.strftime('%d %b %Y, %I:%M %p')}\n"
        f"Venue: {event.venue}\n"
        f"{payment_line}\n\n"
        f"Questions? Reach us at {settings.EDC_CONTACT_EMAIL}.\n\n"
        f"— EDC"
    )

    _send_in_background(subject, message, [registration.email])
    registration.confirmation_email_sent = True
    registration.save(update_fields=["confirmation_email_sent"])
