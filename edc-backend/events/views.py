from rest_framework import viewsets, permissions, mixins
from rest_framework.exceptions import PermissionDenied

from .models import Event, Registration
from .serializers import EventSerializer, RegistrationSerializer


class IsAdminOrReadOnly(permissions.BasePermission):
    """Anyone can list/retrieve events; only admins can create/edit/delete."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.role == "admin")


class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsAdminOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class RegistrationViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    - Regular users: list/create/cancel their OWN registrations.
    - Admins: list ALL registrations (optionally filtered by ?event=<id>),
      used for the "Registrants" screen.
    """
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Registration.objects.select_related("event", "user")
        if user.role == "admin":
            event_id = self.request.query_params.get("event")
            return qs.filter(event_id=event_id) if event_id else qs
        return qs.filter(user=user)

    def perform_destroy(self, instance):
        # Users can only cancel their own registration; admins can cancel any.
        if instance.user != self.request.user and self.request.user.role != "admin":
            raise PermissionDenied("You can only cancel your own registration.")
        instance.delete()
