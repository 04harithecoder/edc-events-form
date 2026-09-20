from django.urls import path

from . import views

urlpatterns = [
    path("events/open/", views.OpenEventListView.as_view(), name="events-open"),
    path("events/past/", views.PastEventListView.as_view(), name="events-past"),
    path("events/<slug:slug>/", views.EventDetailView.as_view(), name="event-detail"),
    path("events/<slug:slug>/register/", views.RegisterView.as_view(), name="event-register"),
    path("webhooks/razorpay/", views.razorpay_webhook, name="razorpay-webhook"),
    path("contact/", views.contact_info, name="contact-info"),
]
