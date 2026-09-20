from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Event(models.Model):
    """
    An EDC event. Status drives which section of the public site it shows
    in (PRD 4: Current/Open vs Past Events).

    STATUS CHOICES:
      draft   - being set up by admin, not visible on public site yet
      open    - visible, accepting registrations
      closed  - visible, registration cut off (deadline passed or admin
                closed it manually), but not yet "past"
      past    - event date has passed; shown in event history
      deleted - soft-deleted (TRD risk: "non-technical admin accidentally
                deletes an event with live registrants" -> never hard-delete
                an event that has registrations)
    """

    STATUS_DRAFT = "draft"
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_PAST = "past"
    STATUS_DELETED = "deleted"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
        (STATUS_PAST, "Past"),
        (STATUS_DELETED, "Deleted"),
    ]

    # Statuses that should still appear on the public site.
    PUBLIC_STATUSES = [STATUS_OPEN, STATUS_CLOSED, STATUS_PAST]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField()
    banner_image = models.ImageField(upload_to="event_banners/", blank=True, null=True)

    venue = models.CharField(max_length=255)
    event_date = models.DateTimeField(help_text="When the event itself happens.")
    registration_deadline = models.DateTimeField(
        help_text="Registrations are rejected after this time."
    )

    capacity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Max number of confirmed registrations (free or paid).",
    )
    fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="0 = free event.",
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    # Optional co-branding note for multicollege events (PRD edge case).
    co_host_note = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-event_date"]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    @property
    def is_free(self):
        return self.fee <= 0

    @property
    def confirmed_registrations_count(self):
        """
        Registrations that actually hold a capacity slot: free ones (which
        are confirmed on save) and paid ones confirmed by the Razorpay
        webhook. Pending/failed paid registrations do NOT hold a slot —
        this is the fix for the PRD's "ghost bookings holding capacity"
        edge case.
        """
        return self.registrations.filter(
            payment_status__in=[Registration.PAYMENT_FREE, Registration.PAYMENT_PAID]
        ).count()

    @property
    def spots_remaining(self):
        return max(self.capacity - self.confirmed_registrations_count, 0)

    @property
    def is_full(self):
        return self.spots_remaining <= 0

    @property
    def is_registration_open(self):
        return (
            self.status == self.STATUS_OPEN
            and timezone.now() <= self.registration_deadline
            and not self.is_full
        )

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            base_slug = slugify(self.title)[:200]
            slug = base_slug
            n = 1
            while Event.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base_slug}-{n}"
            self.slug = slug
        super().save(*args, **kwargs)


class Registration(models.Model):
    """
    A single guest registration for an Event. No user account — PRD
    explicitly excludes student login for MVP. Linked to Event by FK only.
    """

    PAYMENT_FREE = "free"
    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_FAILED = "failed"

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_FREE, "Free (no payment needed)"),
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_FAILED, "Failed"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")

    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    college_name = models.CharField(
        max_length=200,
        help_text="Dropdown of common colleges + 'Other' handled on the frontend; "
        "stored here as plain text either way (TRD 4).",
    )
    year_branch = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g. '3rd Year, CSE'. Optional depending on final form fields.",
    )

    payment_status = models.CharField(
        max_length=10, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_FREE
    )
    payment_gateway_ref_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Razorpay order_id / payment_id, logged for manual reconciliation "
        "if a webhook is ever missed (TRD risk table).",
    )
    razorpay_order_id = models.CharField(max_length=255, blank=True, null=True)

    confirmation_email_sent = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # PRD/TRD decision: block duplicate registrations by email per
            # event, enforced at the DB level (cheaper than de-duping later).
            models.UniqueConstraint(fields=["event", "email"], name="unique_registration_per_event_email"),
        ]
        indexes = [
            models.Index(fields=["event", "payment_status"]),
        ]

    def __str__(self):
        return f"{self.name} <{self.email}> — {self.event.title}"

    def clean(self):
        if self.event_id and self.event.fee > 0 and self.payment_status == self.PAYMENT_FREE:
            raise ValidationError("Paid events cannot have a 'free' payment status registration.")

    def holds_capacity_slot(self):
        return self.payment_status in (self.PAYMENT_FREE, self.PAYMENT_PAID)
