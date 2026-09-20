from rest_framework import serializers

from .models import Event, Registration


class EventListSerializer(serializers.ModelSerializer):
    """Used for the Current/Open and Past Events list views (PRD 4)."""

    is_free = serializers.BooleanField(read_only=True)
    spots_remaining = serializers.IntegerField(read_only=True)
    is_full = serializers.BooleanField(read_only=True)
    is_registration_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "slug",
            "banner_image",
            "venue",
            "event_date",
            "registration_deadline",
            "fee",
            "is_free",
            "status",
            "spots_remaining",
            "is_full",
            "is_registration_open",
        ]


class EventDetailSerializer(EventListSerializer):
    """Full description for the event detail + registration page."""

    class Meta(EventListSerializer.Meta):
        fields = EventListSerializer.Meta.fields + ["description", "capacity", "co_host_note"]


class RegistrationCreateSerializer(serializers.ModelSerializer):
    """
    Validates and creates a guest registration. Capacity + duplicate checks
    happen in the view (inside a DB transaction), not here, because they
    need row-level locking on the Event — see events/views.py.
    """

    class Meta:
        model = Registration
        fields = ["name", "email", "phone", "college_name", "year_branch"]

    def validate_email(self, value):
        return value.strip().lower()


class RegistrationAdminSerializer(serializers.ModelSerializer):
    """Read-only representation used by the admin registrants-list API."""

    class Meta:
        model = Registration
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "college_name",
            "year_branch",
            "payment_status",
            "payment_gateway_ref_id",
            "created_at",
        ]
