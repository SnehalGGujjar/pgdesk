"""
AI triage for PG complaints.
- Uses Gemini API (google-genai SDK) when GEMINI_API_KEY is set.
- Falls back to keyword-based rules so the demo NEVER fails.
- AI triage is isolated in this single function so it can become an async
  Celery/Redis queue task as the product scales.
"""
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

# ─── Keyword-based fallback ──────────────────────────────────

_CATEGORY_KEYWORDS = {
    "plumbing": [
        "water", "geyser", "leak", "tap", "pipe", "drain", "bathroom", "toilet", "flush",
        "paani", "pani", "neeru", "nal", "पानी", "नल", "गीज़र", "बाथरूम",
    ],
    "electrical": [
        "light", "fan", "switch", "power", "bulb", "socket", "mcb", "inverter", "wiring",
        "bijli", "current", "currentu", "batti", "spark", "बिजली", "पंखा", "स्विच",
    ],
    "wifi": ["wifi", "internet", "router", "network", "wi-fi", "net", "वाईफाई"],
    "food": ["food", "mess", "kitchen", "cook", "meal", "breakfast", "dinner", "lunch", "khana", "oota", "खाना"],
    "cleanliness": [
        "clean", "dirty", "cockroach", "pest", "garbage", "dustbin", "sweep", "mop", "hygiene",
        "safai", "kachra", "ganda", "साफ़", "गंदा", "कचरा",
    ],
    "noise": ["noise", "loud", "music", "party", "disturb", "aawaz", "shor", "galata", "आवाज़", "शोर"],
    "safety": ["fire", "smoke", "theft", "lock", "break", "cctv", "guard", "security", "chori", "aag", "धुआं", "आग", "चोरी"],
}

_URGENCY3_WORDS = [
    "fire", "shock", "smoke", "no water", "no power", "gas leak", "theft", "short circuit", "flooding",
    "aag", "spark", "currentu", "current illa", "paani nahi", "aag lagi", "धुआं", "आग", "करंट",
]
_URGENCY2_WORDS = ["not working", "broken", "leaking", "stuck", "slow", "noisy", "kharab", "ganda", "काम नहीं", "खराब"]


def _fallback_triage(text, room):
    """Keyword-based fallback — always returns a valid dict."""
    lower = text.lower()

    # Category
    category = "other"
    for cat, words in _CATEGORY_KEYWORDS.items():
        if any(w in lower for w in words):
            category = cat
            break

    # Urgency
    urgency = 1
    if any(w in lower for w in _URGENCY3_WORDS):
        urgency = 3
    elif any(w in lower for w in _URGENCY2_WORDS):
        urgency = 2

    reply = (
        f"Thank you for reporting this. We've noted the {category} issue in Room {room} "
        f"and will send someone to look into it shortly."
    )
    
    # Language detection in fallback
    orig_lang = "unknown"
    if any('\u0900' <= char <= '\u097F' for char in text):
        orig_lang = "Hindi"
    elif any('\u0C80' <= char <= '\u0CFF' for char in text):
        orig_lang = "Kannada"
    elif any('\u0B80' <= char <= '\u0BFF' for char in text):
        orig_lang = "Tamil"
    elif any('\u0C00' <= char <= '\u0C7F' for char in text):
        orig_lang = "Telugu"

    return {
        "category": category,
        "urgency": urgency,
        "suggested_reply": reply,
        "original_language": orig_lang,
        "english_translation": text,
        "reply_in_tenant_language": reply,
    }


# ─── Main triage function ────────────────────────────────────

def triage_complaint(text: str, room: str) -> dict:
    """
    Triage a complaint using the Gemini LLM with keyword fallback.
    Returns: {
        "category": str,
        "urgency": int,
        "suggested_reply": str,
        "original_language": str,
        "english_translation": str,
        "reply_in_tenant_language": str,
    }
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.info("No GEMINI_API_KEY set, using keyword fallback.")
        return _fallback_triage(text, room)

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        prompt = (
            "You triage complaints for a PG/hostel owner in India. The complaint may be in English, Hindi, Hinglish, Kannada, Tamil, Telugu, etc. "
            "Return ONLY valid JSON, no markdown:\n"
            "{\n"
            '  "category": "plumbing|electrical|food|cleanliness|wifi|noise|safety|other",\n'
            '  "urgency": 1-3 (3 = safety risk, no water, no power; 2 = affects daily life; 1 = minor),\n'
            '  "original_language": "English|Hindi|Kannada|Tamil|Telugu|Hinglish|etc.",\n'
            '  "english_translation": "English translation of complaint (or same as text if already in English)",\n'
            '  "suggested_reply": "1-2 polite sentences in English written as the owner, with a concrete next step",\n'
            '  "reply_in_tenant_language": "Polite reply written in the tenant\'s language or dialect (e.g. Hindi, Hinglish, Kannada) or English if complaint was English"\n'
            "}\n"
            f"Complaint from room {room}: {text}"
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=400,
            ),
        )

        raw = response.text.strip()

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)

        # Validate keys
        category = data.get("category", "other")
        valid_cats = {"plumbing", "electrical", "food", "cleanliness", "wifi", "noise", "safety", "other"}
        if category not in valid_cats:
            category = "other"

        urgency = int(data.get("urgency", 1))
        urgency = max(1, min(3, urgency))  # clamp 1-3

        orig_lang = data.get("original_language", "unknown")
        eng_trans = data.get("english_translation", text) or text

        reply = data.get("suggested_reply", "")
        if not reply:
            reply = f"Thank you for your complaint about Room {room}. We'll look into it."

        tenant_reply = data.get("reply_in_tenant_language", reply) or reply

        return {
            "category": category,
            "urgency": urgency,
            "suggested_reply": reply,
            "original_language": orig_lang,
            "english_translation": eng_trans,
            "reply_in_tenant_language": tenant_reply,
        }

    except Exception as exc:
        logger.warning("LLM triage failed (%s), using keyword fallback.", exc)
        return _fallback_triage(text, room)


# ─── Weekly summary (Phase 6, optional) ──────────────────────

def generate_weekly_summary(property_obj) -> str:
    """Generate a weekly summary using LLM or a simple template."""
    from datetime import date, timedelta
    from .models import Complaint, Tenant

    today = date.today()
    week_ago = today - timedelta(days=7)
    current_month = today.replace(day=1)

    active_tenants = Tenant.objects.filter(property=property_obj, is_active=True)
    statuses = [t.rent_status() for t in active_tenants]
    paid = statuses.count("Paid")
    due = statuses.count("Due")
    overdue = statuses.count("Overdue")
    overdue_amount = sum(t.rent_amount for t in active_tenants if t.rent_status() == "Overdue")

    recent_complaints = Complaint.objects.filter(
        property=property_obj, created_at__date__gte=week_ago
    )
    open_complaints = recent_complaints.filter(status="open").count()
    resolved_complaints = recent_complaints.filter(status="resolved").count()

    context = (
        f"Property: {property_obj.name}\n"
        f"Date: {today}\n"
        f"Tenants: {paid} paid, {due} due, {overdue} overdue (₹{overdue_amount:,} outstanding)\n"
        f"Complaints this week: {open_complaints} open, {resolved_complaints} resolved\n"
    )

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return (
            f"📊 Weekly Summary for {property_obj.name}\n\n"
            f"• Rent collection: {paid} paid, {due} pending, {overdue} overdue\n"
            f"• Outstanding amount: ₹{overdue_amount:,}\n"
            f"• New complaints this week: {open_complaints + resolved_complaints}\n"
            f"• Resolved: {resolved_complaints}, Still open: {open_complaints}\n"
            f"• Action: Follow up with overdue tenants and address open complaints."
        )

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = (
            "You are an assistant for a PG/hostel owner in India. "
            "Summarise this week's status in exactly 5 concise bullet points. "
            "Be specific with numbers. Keep it friendly and actionable.\n\n"
            + context
        )
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(temperature=0.4, max_output_tokens=400),
        )
        return response.text.strip()
    except Exception as exc:
        logger.warning("Weekly summary LLM failed (%s), using template.", exc)
        return (
            f"📊 Weekly Summary for {property_obj.name}\n\n"
            f"• Rent: {paid} paid, {due} pending, {overdue} overdue (₹{overdue_amount:,})\n"
            f"• Complaints: {open_complaints} open, {resolved_complaints} resolved\n"
            f"• Follow up with overdue tenants."
        )
