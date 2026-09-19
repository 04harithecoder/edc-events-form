from rest_framework import serializers

from accounts.serializers import UserSerializer
from .models import Event, Registration


class EventSerializer(serializers.ModelSerializer):
    seats_left = serializers.ReadOnlyField()
    is_registered = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id", "title", "tagline", "category", "description",
            "date", "time", "venue", "capacity", "seats_left",
            "is_registered", "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_is_registered(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.registrations.filter(user=request.user).exclude(
            status=Registration.Status.CANCELLED
        ).exists()


class RegistrationSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    event_title = serializers.CharField(source="event.title", read_only=True)

    class Meta:
        model = Registration
        fields = ["id", "event", "event_title", "user", "status", "registered_at"]
        read_only_fields = ["status", "registered_at"]

    def validate_event(self, event):
        if event.seats_left <= 0:
            raise serializers.ValidationError("This event is full.")
        return event

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)
