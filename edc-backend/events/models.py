from django.conf import settings
from django.db import models


class Event(models.Model):
    title = models.CharField(max_length=200)
    tagline = models.CharField(max_length=250, blank=True)
    category = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    date = models.DateField()
    time = models.CharField(max_length=40)  # display string, e.g. "10:00 AM" — see note below
    venue = models.CharField(max_length=200)
    capacity = models.PositiveIntegerField(default=50)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="events_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.title} ({self.date})"

    @property
    def seats_left(self):
        return max(0, self.capacity - self.registrations.count())


class Registration(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        PENDING_PAYMENT = "pending_payment", "Pending payment"
        CANCELLED = "cancelled", "Cancelled"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="registrations")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "user")  # one registration per user per event
        ordering = ["-registered_at"]

    def __str__(self):
        return f"{self.user} -> {self.event} [{self.status}]"
