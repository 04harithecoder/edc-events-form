import csv

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils.html import format_html

from .models import Event, Registration


class RegistrationInline(admin.TabularInline):
    """Quick glance at registrants directly on the Event page."""

    model = Registration
    extra = 0
    fields = ("name", "email", "phone", "college_name", "payment_status", "created_at")
    readonly_fields = fields
    can_delete = False
    show_change_link = True
    max_num = 0  # view-only here; full list is on the Registration admin page

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """
    This is the "no-code" event management panel the PRD asks for.
    A committee member creates/edits events here — no code touched.
    """

    list_display = (
        "title",
        "event_date",
        "status",
        "fee_display",
        "registrations_vs_capacity",
        "registration_deadline",
    )
    list_filter = ("status",)
    search_fields = ("title", "venue")
    readonly_fields = ("slug", "created_at", "updated_at", "registrations_vs_capacity")
    inlines = [RegistrationInline]
    actions = ["mark_as_open", "mark_as_closed", "mark_as_past", "soft_delete_events"]

    fieldsets = (
        (None, {"fields": ("title", "slug", "description", "banner_image", "co_host_note")}),
        ("Logistics", {"fields": ("venue", "event_date", "registration_deadline", "capacity", "fee")}),
        ("Status", {"fields": ("status", "registrations_vs_capacity")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def fee_display(self, obj):
        return "Free" if obj.is_free else f"₹{obj.fee}"
    fee_display.short_description = "Fee"

    def registrations_vs_capacity(self, obj):
        # PRD: "As an admin, I can see registration count vs. capacity at
        # a glance, so I know if an event is filling up."
        if not obj.pk:
            return "—"
        count = obj.confirmed_registrations_count
        color = "red" if obj.is_full else ("orange" if count >= obj.capacity * 0.8 else "green")
        return format_html(
            '<span style="color: {};">{} / {}</span>', color, count, obj.capacity
        )
    registrations_vs_capacity.short_description = "Registrations"

    # --- Soft delete instead of hard delete (TRD risk mitigation) ---------

    def get_queryset(self, request):
        # Hide soft-deleted events from the default admin list entirely.
        return super().get_queryset(request).exclude(status=Event.STATUS_DELETED)

    def has_delete_permission(self, request, obj=None):
        # Disable Django's hard-delete UI; use the soft-delete action instead.
        return False

    @admin.action(description="Mark selected events as Open")
    def mark_as_open(self, request, queryset):
        updated = queryset.update(status=Event.STATUS_OPEN)
        self.message_user(request, f"{updated} event(s) marked Open.", messages.SUCCESS)

    @admin.action(description="Close registration for selected events")
    def mark_as_closed(self, request, queryset):
        updated = queryset.update(status=Event.STATUS_CLOSED)
        self.message_user(request, f"{updated} event(s) closed.", messages.SUCCESS)

    @admin.action(description="Mark selected events as Past")
    def mark_as_past(self, request, queryset):
        updated = queryset.update(status=Event.STATUS_PAST)
        self.message_user(request, f"{updated} event(s) marked Past.", messages.SUCCESS)

    @admin.action(description="Soft-delete selected events (safe — keeps registrant data)")
    def soft_delete_events(self, request, queryset):
        updated = queryset.update(status=Event.STATUS_DELETED)
        self.message_user(
            request,
            f"{updated} event(s) soft-deleted. Registrant data was NOT removed.",
            messages.WARNING,
        )


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    """
    Registrant list + CSV export per event (PRD: "view and export the
    list of registrants for a given event, including payment status").
    """

    list_display = ("name", "email", "event", "payment_status", "college_name", "created_at")
    list_filter = ("event", "payment_status")
    search_fields = ("name", "email", "phone", "college_name")
    readonly_fields = (
        "event", "name", "email", "phone", "college_name", "year_branch",
        "razorpay_order_id", "payment_gateway_ref_id", "confirmation_email_sent",
        "created_at", "updated_at",
    )
    actions = ["export_as_csv"]

    def has_add_permission(self, request):
        # Registrations are only ever created via the public registration
        # flow, never hand-typed by an admin.
        return False

    @admin.action(description="Export selected registrants as CSV")
    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="registrants.csv"'
        writer = csv.writer(response)
        writer.writerow(
            ["Name", "Email", "Phone", "College", "Year/Branch",
             "Event", "Payment Status", "Payment Ref ID", "Registered At"]
        )
        for reg in queryset.select_related("event"):
            writer.writerow(
                [
                    reg.name, reg.email, reg.phone, reg.college_name, reg.year_branch,
                    reg.event.title, reg.get_payment_status_display(),
                    reg.payment_gateway_ref_id or "", reg.created_at,
                ]
            )
        return response
