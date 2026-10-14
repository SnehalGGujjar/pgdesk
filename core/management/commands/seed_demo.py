"""
Seed demo data for PGDesk.
Idempotent: safe to run multiple times.
Creates demo owner, property, rooms, tenants, payments, and complaints.
"""
import random
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from core.models import Complaint, Property, RentPayment, Room, Tenant


INDIAN_NAMES = [
    "Rahul Sharma", "Priya Patel", "Arun Kumar", "Sneha Reddy",
    "Vikram Singh", "Anjali Nair", "Rohan Gupta", "Divya Iyer",
    "Karthik Menon", "Pooja Verma", "Amit Joshi", "Neha Kapoor",
    "Siddharth Rao", "Meera Das", "Ajay Thakur", "Kavitha Pillai",
    "Ravi Prasad", "Swathi Murthy", "Deepak Hegde", "Lakshmi Bhat",
]

PHONES = [
    "9876543210", "9876543211", "9876543212", "9876543213",
    "9876543214", "9876543215", "9876543216", "9876543217",
    "9876543218", "9876543219", "9876543220", "9876543221",
    "9876543222", "9876543223", "9876543224", "9876543225",
    "9876543226", "9876543227", "9876543228", "9876543229",
]

COMPLAINTS_DATA = [
    {
        "room_number": "102",
        "tenant_name": "Priya Patel",
        "text": "The bathroom tap is leaking badly, water is pooling on the floor.",
        "category": "plumbing",
        "urgency": 2,
        "suggested_reply": "Thank you for reporting this, Priya. We've contacted the plumber and he'll visit Room 102 by tomorrow morning.",
        "status": "open",
    },
    {
        "room_number": "205",
        "tenant_name": "Vikram Singh",
        "text": "No hot water from the geyser since yesterday. It makes a clicking noise but doesn't heat.",
        "category": "plumbing",
        "urgency": 3,
        "suggested_reply": "Hi Vikram, we understand this is urgent. Our electrician will check the geyser in Room 205 today itself. Please use the common bathroom on the 2nd floor in the meantime.",
        "status": "open",
    },
    {
        "room_number": "301",
        "tenant_name": "Anjali Nair",
        "text": "WiFi has been very slow for the past 3 days, can barely load anything.",
        "category": "wifi",
        "urgency": 2,
        "suggested_reply": "Hi Anjali, sorry about the WiFi trouble. We're upgrading the router this week. We'll ensure the 3rd floor gets better coverage.",
        "status": "open",
    },
    {
        "room_number": "104",
        "tenant_name": "Rohan Gupta",
        "text": "The ceiling fan in my room is making a loud rattling noise, especially at night.",
        "category": "electrical",
        "urgency": 1,
        "suggested_reply": "Hi Rohan, we'll send the maintenance person to tighten/replace the fan in Room 104 this weekend. Thanks for letting us know!",
        "status": "resolved",
    },
    {
        "room_number": "402",
        "tenant_name": "",
        "text": "Common area on 4th floor hasn't been cleaned in 3 days. Dustbin is overflowing.",
        "category": "cleanliness",
        "urgency": 2,
        "suggested_reply": "We apologise for the inconvenience. The cleaning staff has been notified and the 4th floor common area will be cleaned today. We'll ensure daily cleaning going forward.",
        "status": "open",
    },
    {
        "room_number": "303",
        "tenant_name": "Siddharth Rao",
        "text": "Noticed a burning smell from the switchboard near the door. Sparks when I turn on the light.",
        "category": "safety",
        "urgency": 3,
        "suggested_reply": "Hi Siddharth, this is a safety concern and we're treating it as urgent. Please do NOT use that switchboard. Our electrician is on the way to Room 303 immediately.",
        "status": "resolved",
    },
]


class Command(BaseCommand):
    help = "Seed demo data for PGDesk (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset tenants, payments and complaints to default demo state",
        )

    def handle(self, *args, **options):
        reset = options.get("reset", False)
        # Demo owner
        user, created = User.objects.get_or_create(
            username="demo",
            defaults={"is_active": True},
        )
        if created:
            user.set_password("demo12345")
            user.save()
            self.stdout.write(self.style.SUCCESS("Created demo user"))
        else:
            self.stdout.write("Demo user already exists")

        # Property
        prop, created = Property.objects.get_or_create(
            slug="sunrise-pg",
            defaults={"owner": user, "name": "Sunrise PG", "city": "Bengaluru"},
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created property: Sunrise PG"))
        else:
            self.stdout.write("Property already exists")

        # Rooms: 4 floors, 3 rooms per floor = 12 rooms
        rooms = []
        for floor in range(1, 5):
            for room_num in range(1, 4):
                number = f"{floor}0{room_num}"
                beds = 2 if room_num <= 2 else 1
                rent = random.choice([6000, 6500, 7000, 7500, 8000, 8500, 9000])
                room, _ = Room.objects.get_or_create(
                    property=prop,
                    number=number,
                    defaults={"floor": floor, "beds": beds, "rent_per_bed": rent},
                )
                rooms.append(room)

        self.stdout.write(f"Ensured {len(rooms)} rooms exist")

        # Tenants: 20 active tenants spread across rooms
        today = date.today()
        current_month = today.replace(day=1)
        prev_month = (current_month - timedelta(days=1)).replace(day=1)
        prev2_month = (prev_month - timedelta(days=1)).replace(day=1)

        existing_tenant_count = Tenant.objects.filter(property=prop).count()
        if existing_tenant_count >= 20 and not reset:
            self.stdout.write("Tenants already seeded")
            tenants = list(Tenant.objects.filter(property=prop, is_active=True))
        else:
            # Clear and re-seed
            Tenant.objects.filter(property=prop).delete()
            RentPayment.objects.filter(tenant__property=prop).delete()

            tenants = []
            room_idx = 0
            for i in range(20):
                room = rooms[room_idx % len(rooms)]
                room_idx += 1
                rent = random.choice([6000, 6500, 7000, 7500, 8000, 8500, 9000])
                due_day = random.choice([1, 3, 5, 7, 10])
                tenant = Tenant.objects.create(
                    property=prop,
                    room=room,
                    name=INDIAN_NAMES[i],
                    phone=PHONES[i],
                    rent_amount=rent,
                    due_day=due_day,
                    joined_on=today - timedelta(days=random.randint(30, 180)),
                    is_active=True,
                )
                tenants.append(tenant)

            self.stdout.write(self.style.SUCCESS(f"Created {len(tenants)} tenants"))

            # Payments: previous 2 months fully paid
            for t in tenants:
                for month in [prev2_month, prev_month]:
                    RentPayment.objects.get_or_create(
                        tenant=t,
                        month=month,
                        defaults={
                            "amount": t.rent_amount,
                            "paid_on": month.replace(day=min(t.due_day, 28)),
                        },
                    )

            # Current month: ~12 paid, ~4 due, ~4 overdue
            # We need to set due_days so that the status logic works correctly today
            random.shuffle(tenants)

            # First 12: mark as paid
            for t in tenants[:12]:
                RentPayment.objects.get_or_create(
                    tenant=t,
                    month=current_month,
                    defaults={
                        "amount": t.rent_amount,
                        "paid_on": current_month.replace(day=min(t.due_day, today.day)),
                    },
                )

            # Next 4: "due" — set due_day to be >= today's day
            for t in tenants[12:16]:
                t.due_day = min(today.day + random.randint(0, 10), 28)
                t.save()

            # Last 4: "overdue" — set due_day to be < today's day
            for t in tenants[16:20]:
                t.due_day = max(1, today.day - random.randint(1, 5))
                t.save()

            self.stdout.write(self.style.SUCCESS("Created rent payments (12 paid, 4 due, 4 overdue)"))

        # Complaints
        existing_complaints = Complaint.objects.filter(property=prop).count()
        if existing_complaints >= 6 and not reset:
            self.stdout.write("Complaints already seeded")
        else:
            Complaint.objects.filter(property=prop).delete()
            for i, c_data in enumerate(COMPLAINTS_DATA):
                Complaint.objects.create(
                    property=prop,
                    created_at=today - timedelta(hours=random.randint(1, 72)),
                    **c_data,
                )
            self.stdout.write(self.style.SUCCESS(f"Created {len(COMPLAINTS_DATA)} complaints"))

        self.stdout.write(self.style.SUCCESS("\nDemo data seeded successfully!"))
        self.stdout.write("   Login: demo / demo12345")
        self.stdout.write("   Complaint link: /c/sunrise-pg/")
