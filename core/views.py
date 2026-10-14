"""
PGDesk core views.
- Every owner query is scoped by property (multi-tenant safety).
- Dashboard uses select_related to avoid N+1 queries.
"""
import logging
from datetime import date
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .models import Complaint, Property, RentPayment, Room, Tenant

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────
def _get_property(user):
    """Get the first property of the logged-in owner."""
    return Property.objects.filter(owner=user).first()


def _current_month():
    return date.today().replace(day=1)


# ─── Auth ─────────────────────────────────────────────────────
def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "Invalid username or password.")
    return render(request, "core/login.html")


def logout_view(request):
    logout(request)
    return redirect("landing")


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        password2 = request.POST.get("password2", "")
        prop_name = request.POST.get("property_name", "").strip()
        city = request.POST.get("city", "").strip()

        errors = []
        if not username or not password:
            errors.append("Username and password are required.")
        if password != password2:
            errors.append("Passwords don't match.")
        if User.objects.filter(username=username).exists():
            errors.append("Username already taken.")
        if not prop_name:
            errors.append("Property name is required.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "core/signup.html")

        user = User.objects.create_user(username=username, password=password)
        Property.objects.create(owner=user, name=prop_name, city=city or "Unknown")
        login(request, user)
        messages.success(request, f"Welcome! '{prop_name}' has been created.")
        return redirect("dashboard")
    return render(request, "core/signup.html")


def try_demo(request):
    """Log in as the seeded demo owner automatically."""
    user = authenticate(request, username="demo", password="demo12345")
    if user:
        login(request, user)
        messages.info(request, "You're exploring the demo. Data resets periodically.")
        return redirect("dashboard")
    messages.error(request, "Demo account not found. Run the seed_demo command first.")
    return redirect("landing")


# ─── Landing ──────────────────────────────────────────────────
def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "core/landing.html")


# ─── Dashboard ────────────────────────────────────────────────
@login_required
def dashboard(request):
    prop = _get_property(request.user)
    if not prop:
        messages.warning(request, "Create a property first.")
        return redirect("rooms")

    tenants = (
        Tenant.objects.filter(property=prop, is_active=True)
        .select_related("room")  # avoid N+1
    )

    # Compute statuses
    tenant_data = []
    for t in tenants:
        status = t.rent_status()
        tenant_data.append({"tenant": t, "status": status})

    # Filter
    filter_tab = request.GET.get("filter", "all").lower()
    if filter_tab in ("overdue", "due", "paid"):
        cap = filter_tab.capitalize()
        tenant_data = [d for d in tenant_data if d["status"] == cap]

    # Stats
    total_beds = sum(r.beds for r in Room.objects.filter(property=prop))
    occupied_beds = tenants.count()
    cm = _current_month()
    collected = (
        RentPayment.objects.filter(tenant__property=prop, month=cm)
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )
    overdue_tenants = [d for d in tenant_data if d["status"] == "Overdue"] if filter_tab == "all" else []
    # Recalculate overdue amount from all active tenants (not just filtered)
    all_tenant_data = [{"tenant": t, "status": t.rent_status()} for t in Tenant.objects.filter(property=prop, is_active=True)]
    overdue_amount = sum(d["tenant"].rent_amount for d in all_tenant_data if d["status"] == "Overdue")

    ctx = {
        "prop": prop,
        "tenant_data": tenant_data,
        "filter_tab": filter_tab,
        "total_beds": total_beds,
        "occupied_beds": occupied_beds,
        "collected": collected,
        "overdue_amount": overdue_amount,
    }
    return render(request, "core/dashboard.html", ctx)


# ─── Mark Paid ────────────────────────────────────────────────
@login_required
def mark_paid(request, tenant_id):
    prop = _get_property(request.user)
    tenant = get_object_or_404(Tenant, pk=tenant_id, property=prop, is_active=True)
    cm = _current_month()
    _, created = RentPayment.objects.get_or_create(
        tenant=tenant,
        month=cm,
        defaults={"amount": tenant.rent_amount, "paid_on": date.today()},
    )
    if created:
        messages.success(request, f"✅ {tenant.name}'s payment for {cm:%B %Y} recorded.")
    else:
        messages.info(request, f"{tenant.name} was already marked as paid.")
    return redirect("dashboard")


# ─── Rooms & Tenants ─────────────────────────────────────────
@login_required
def rooms(request):
    prop = _get_property(request.user)
    if not prop:
        messages.warning(request, "Create a property first.")
        return render(request, "core/rooms.html", {"prop": None, "rooms_list": [], "tenants": []})

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_room":
            number = request.POST.get("number", "").strip()
            floor = request.POST.get("floor", 1)
            beds = request.POST.get("beds", 1)
            rent = request.POST.get("rent_per_bed", 0)
            if number:
                Room.objects.create(
                    property=prop, number=number,
                    floor=int(floor), beds=int(beds), rent_per_bed=int(rent),
                )
                messages.success(request, f"Room {number} added.")
            else:
                messages.error(request, "Room number is required.")

        elif action == "add_tenant":
            room_id = request.POST.get("room_id")
            name = request.POST.get("name", "").strip()
            phone = request.POST.get("phone", "").strip()
            rent_amount = request.POST.get("rent_amount", 0)
            due_day = request.POST.get("due_day", 1)
            room = get_object_or_404(Room, pk=room_id, property=prop)
            if name and phone:
                Tenant.objects.create(
                    property=prop, room=room, name=name, phone=phone,
                    rent_amount=int(rent_amount), due_day=int(due_day),
                )
                messages.success(request, f"Tenant {name} added to Room {room.number}.")
            else:
                messages.error(request, "Name and phone are required.")

        return redirect("rooms")

    rooms_list = Room.objects.filter(property=prop).prefetch_related("tenants")
    active_tenants = Tenant.objects.filter(property=prop, is_active=True).select_related("room")
    ctx = {
        "prop": prop,
        "rooms_list": rooms_list,
        "tenants": active_tenants,
    }
    return render(request, "core/rooms.html", ctx)


@login_required
def deactivate_tenant(request, tenant_id):
    prop = _get_property(request.user)
    tenant = get_object_or_404(Tenant, pk=tenant_id, property=prop)
    tenant.is_active = False
    tenant.save()
    messages.success(request, f"{tenant.name} has been deactivated.")
    return redirect("rooms")


# ─── Complaints (Owner Inbox) ────────────────────────────────
@login_required
def complaints(request):
    prop = _get_property(request.user)
    if not prop:
        messages.warning(request, "Create a property first.")
        return render(request, "core/complaints.html", {"prop": None, "complaints_list": []})

    tab = request.GET.get("tab", "open").lower()
    if tab not in ("open", "resolved"):
        tab = "open"

    complaints_list = Complaint.objects.filter(property=prop, status=tab)
    ctx = {
        "prop": prop,
        "complaints_list": complaints_list,
        "tab": tab,
    }
    return render(request, "core/complaints.html", ctx)


@login_required
def resolve_complaint(request, complaint_id):
    prop = _get_property(request.user)
    complaint = get_object_or_404(Complaint, pk=complaint_id, property=prop)
    complaint.status = "resolved"
    complaint.save()
    messages.success(request, "Complaint marked as resolved. ✅")
    return redirect("complaints")


# ─── Public Complaint Form ───────────────────────────────────
def public_complaint(request, slug):
    prop = get_object_or_404(Property, slug=slug)

    if request.method == "POST":
        room_number = request.POST.get("room_number", "").strip()
        tenant_name = request.POST.get("tenant_name", "").strip()
        text = request.POST.get("text", "").strip()

        if not room_number or not text:
            messages.error(request, "Room number and complaint text are required.")
            return render(request, "core/public_complaint.html", {"prop": prop})

        # AI triage (imported here to keep top-level imports clean)
        from .ai import triage_complaint

        result = triage_complaint(text, room_number)

        Complaint.objects.create(
            property=prop,
            room_number=room_number,
            tenant_name=tenant_name,
            text=text,
            category=result.get("category", "other"),
            urgency=result.get("urgency", 1),
            original_language=result.get("original_language", "unknown"),
            english_translation=result.get("english_translation", text),
            suggested_reply=result.get("suggested_reply", ""),
            reply_in_tenant_language=result.get("reply_in_tenant_language", ""),
        )
        return render(request, "core/complaint_success.html", {"prop": prop})

    return render(request, "core/public_complaint.html", {"prop": prop})


# ─── Weekly Summary (Phase 6, optional) ──────────────────────
@login_required
def weekly_summary(request):
    prop = _get_property(request.user)
    if not prop:
        return redirect("dashboard")

    summary = None
    if request.method == "POST":
        from .ai import generate_weekly_summary
        summary = generate_weekly_summary(prop)

    return render(request, "core/weekly_summary.html", {"prop": prop, "summary": summary})
