from django.urls import path
from . import views

urlpatterns = [
    # Public
    path("", views.landing, name="landing"),
    path("c/<slug:slug>/", views.public_complaint, name="public_complaint"),

    # Auth
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("signup/", views.signup_view, name="signup"),
    path("try-demo/", views.try_demo, name="try_demo"),

    # Owner pages
    path("dashboard/", views.dashboard, name="dashboard"),
    path("rooms/", views.rooms, name="rooms"),
    path("complaints/", views.complaints, name="complaints"),

    # Actions
    path("tenants/<int:tenant_id>/paid/", views.mark_paid, name="mark_paid"),
    path("complaints/<int:complaint_id>/resolve/", views.resolve_complaint, name="resolve_complaint"),
    path("tenants/<int:tenant_id>/deactivate/", views.deactivate_tenant, name="deactivate_tenant"),

    # Optional
    path("weekly-summary/", views.weekly_summary, name="weekly_summary"),
]
