from datetime import date

from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify


class Property(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="properties")
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, max_length=140)
    city = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "properties"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            n = 1
            while Property.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Room(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="rooms")
    number = models.CharField(max_length=20)
    floor = models.IntegerField(default=1)
    beds = models.IntegerField(default=1)
    rent_per_bed = models.IntegerField(help_text="INR per bed per month")

    class Meta:
        ordering = ["floor", "number"]

    def __str__(self):
        return f"Room {self.number}"


class Tenant(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="tenants")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="tenants")
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15)
    rent_amount = models.IntegerField(help_text="INR per month")
    due_day = models.IntegerField(help_text="Day of month (1-28)")
    joined_on = models.DateField(default=date.today)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["property", "is_active"]),
        ]

    def __str__(self):
        return self.name

    # --- Rent status logic: single source of truth ---
    def rent_status(self):
        """Return rent status for the current month: 'Paid', 'Overdue', or 'Due'."""
        today = date.today()
        current_month = today.replace(day=1)
        if self.payments.filter(month=current_month).exists():
            return "Paid"
        if today.day > self.due_day:
            return "Overdue"
        return "Due"


class RentPayment(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="payments")
    month = models.DateField(help_text="First day of the month")
    amount = models.IntegerField()
    paid_on = models.DateField(default=date.today)

    class Meta:
        unique_together = ("tenant", "month")
        indexes = [
            models.Index(fields=["tenant", "month"]),
        ]

    def __str__(self):
        return f"{self.tenant.name} – {self.month:%b %Y}"


class Complaint(models.Model):
    STATUS_CHOICES = [("open", "Open"), ("resolved", "Resolved")]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="complaints")
    room_number = models.CharField(max_length=20)
    tenant_name = models.CharField(max_length=120, blank=True, default="")
    text = models.TextField()
    category = models.CharField(max_length=30, blank=True, default="other")
    urgency = models.IntegerField(default=1, help_text="1=Low, 2=Normal, 3=Urgent")
    original_language = models.CharField(max_length=40, blank=True, default="unknown")
    english_translation = models.TextField(blank=True, default="")
    suggested_reply = models.TextField(blank=True, default="")
    reply_in_tenant_language = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-urgency", "-created_at"]
        indexes = [
            models.Index(fields=["property", "status", "urgency"]),
        ]

    def __str__(self):
        return f"Complaint – Room {self.room_number}"
