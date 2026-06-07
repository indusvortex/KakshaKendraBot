import os
import requests
import re
from datetime import datetime, timezone
from groq import Groq
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# AI Provider Stats — tracks which fallback was used + counts
# Reset on every server restart (lives in process memory)
# ============================================================
ai_stats = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "total_calls": 0,
    "groq_success": 0,
    "groq_fail": 0,
    "gemini_success": 0,
    "gemini_fail": 0,
    "cerebras_success": 0,
    "cerebras_fail": 0,
    "all_failed": 0,
    "last_groq_success_at": None,
    "last_gemini_success_at": None,
    "last_cerebras_success_at": None,
    # Approx token usage (input + output)
    "tokens_used_estimate": 0,
    # Per-key Groq stats — populated when keys are loaded.
    # Each item: {"index", "label", "success", "rate_limited", "fail",
    #             "last_used_at", "last_status"}
    "groq_keys": [],
    # Index of the key that handled the most recent successful Groq call
    "last_groq_key_index": None,
}


def _bump_stat(key: str, by: int = 1):
    if key in ai_stats:
        if isinstance(ai_stats[key], (int, float)):
            ai_stats[key] += by
        else:
            ai_stats[key] = datetime.now(timezone.utc).isoformat()

# Groq clients — supports multiple API keys for rate-limit rotation.
# Configure as: GROQ_API_KEY (primary), GROQ_API_KEY_2, GROQ_API_KEY_3, ... up to _10
_groq_clients_cache: list | None = None


def _get_groq_clients() -> list:
    """Returns a list of Groq clients, one per configured API key."""
    global _groq_clients_cache
    if _groq_clients_cache is None:
        keys = []
        labels = []
        # Primary key uses env name "GROQ_API_KEY"
        primary = os.getenv("GROQ_API_KEY")
        if primary:
            keys.append(primary)
            labels.append("GROQ_API_KEY")
        # Additional keys: GROQ_API_KEY_2, _3, ... up to _10
        for i in range(2, 11):
            extra = os.getenv(f"GROQ_API_KEY_{i}")
            if extra:
                keys.append(extra)
                labels.append(f"GROQ_API_KEY_{i}")
        _groq_clients_cache = [Groq(api_key=k) for k in keys]

        # Initialize per-key stats so the dashboard can render even before any call
        ai_stats["groq_keys"] = [
            {
                "index": i + 1,
                "label": labels[i],
                "key_preview": (keys[i][:6] + "…" + keys[i][-4:]) if len(keys[i]) > 12 else "***",
                "success": 0,
                "rate_limited": 0,
                "fail": 0,
                "last_used_at": None,
                "last_status": "idle",  # idle | success | rate_limited | error
            }
            for i in range(len(keys))
        ]
        print(f"[Groq] Loaded {len(_groq_clients_cache)} API key(s).")
    return _groq_clients_cache


def _generate_with_groq(messages: list) -> str | None:
    """
    Tries each Groq API key in turn. On rate limit (429), moves to the next key.
    Returns the AI text on success, or None if every key failed.
    """
    clients = _get_groq_clients()
    if not clients:
        print("[Groq] No API keys configured.")
        return None

    for i, client in enumerate(clients):
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7,
                max_tokens=500,
            )
            if i > 0:
                print(f"[Groq] Used backup key #{i + 1}")
            _bump_stat("groq_success")
            ai_stats["last_groq_success_at"] = now_iso
            ai_stats["last_groq_key_index"] = i + 1
            # Per-key stats
            if i < len(ai_stats["groq_keys"]):
                ai_stats["groq_keys"][i]["success"] += 1
                ai_stats["groq_keys"][i]["last_used_at"] = now_iso
                ai_stats["groq_keys"][i]["last_status"] = "success"
            usage = getattr(response, "usage", None)
            if usage:
                ai_stats["tokens_used_estimate"] += getattr(usage, "total_tokens", 0)
            return response.choices[0].message.content
        except Exception as e:
            err_str = str(e).lower()
            if "rate_limit" in err_str or "429" in err_str or "quota" in err_str:
                print(f"[Groq] Key #{i + 1} rate-limited, trying next key...")
                if i < len(ai_stats["groq_keys"]):
                    ai_stats["groq_keys"][i]["rate_limited"] += 1
                    ai_stats["groq_keys"][i]["last_used_at"] = now_iso
                    ai_stats["groq_keys"][i]["last_status"] = "rate_limited"
                continue
            print(f"[Groq] Key #{i + 1} failed (non-rate-limit): {e}")
            if i < len(ai_stats["groq_keys"]):
                ai_stats["groq_keys"][i]["fail"] += 1
                ai_stats["groq_keys"][i]["last_used_at"] = now_iso
                ai_stats["groq_keys"][i]["last_status"] = "error"
            continue

    print("[Groq] All keys exhausted.")
    _bump_stat("groq_fail")
    return None


# Gemini client — lazy-loaded fallback when Groq is rate-limited
_gemini_client = None

def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=api_key)
        except ImportError:
            print("google-genai package not installed; Gemini fallback unavailable.")
            return None
    return _gemini_client


def _generate_with_gemini(messages: list) -> str | None:
    """Fallback to Gemini when Groq fails. Returns None if Gemini is also unavailable."""
    client = _get_gemini_client()
    if client is None:
        return None

    # Gemini has no "system" role — prepend system instruction to the first user message
    system_text = ""
    contents = []
    for msg in messages:
        if msg["role"] == "system":
            system_text = msg["content"]
        elif msg["role"] == "user":
            user_text = msg["content"]
            if system_text and not contents:
                user_text = f"{system_text}\n\n---\n\n{user_text}"
                system_text = ""
            contents.append({"role": "user", "parts": [{"text": user_text}]})
        elif msg["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": msg["content"]}]})

    # gemini-2.0-flash has higher free-tier limits than 2.5-flash:
    # 15 RPM vs 5 RPM, and 1500 RPD vs 250 RPD.
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=contents,
        )
        print("[Gemini fallback] Response generated successfully.")
        _bump_stat("gemini_success")
        ai_stats["last_gemini_success_at"] = datetime.now(timezone.utc).isoformat()
        usage = getattr(response, "usage_metadata", None)
        if usage:
            ai_stats["tokens_used_estimate"] += getattr(usage, "total_token_count", 0)
        return response.text
    except Exception as e:
        print(f"[Gemini fallback] Failed: {e}")
        _bump_stat("gemini_fail")
        return None


# Cerebras client — final fallback when Groq AND Gemini both fail
_cerebras_client = None

def _get_cerebras_client():
    global _cerebras_client
    if _cerebras_client is None:
        api_key = os.getenv("CEREBRAS_API_KEY")
        if not api_key:
            return None
        try:
            from cerebras.cloud.sdk import Cerebras
            _cerebras_client = Cerebras(api_key=api_key)
        except ImportError:
            print("cerebras-cloud-sdk package not installed; Cerebras fallback unavailable.")
            return None
    return _cerebras_client


def _generate_with_cerebras(messages: list) -> str | None:
    """Final fallback to Cerebras. Uses same OpenAI-style messages as Groq."""
    client = _get_cerebras_client()
    if client is None:
        return None

    # Use the 8B model — universally accessible on Cerebras free tier.
    # 70B model often requires waitlist/upgrade.
    try:
        response = client.chat.completions.create(
            model="llama3.1-8b",
            messages=messages,
            temperature=0.7,
            max_tokens=500,
        )
        print("[Cerebras fallback] Response generated successfully.")
        _bump_stat("cerebras_success")
        ai_stats["last_cerebras_success_at"] = datetime.now(timezone.utc).isoformat()
        usage = getattr(response, "usage", None)
        if usage:
            ai_stats["tokens_used_estimate"] += getattr(usage, "total_tokens", 0)
        return response.choices[0].message.content
    except Exception as e:
        print(f"[Cerebras fallback] Failed: {e}")
        _bump_stat("cerebras_fail")
        return None


# Kaksha Kendra Knowledge Base and Persona
SYSTEM_INSTRUCTION = """
Role & Core Identity:
You are "Rajat Sir's AI", the official WhatsApp assistant for Kaksha Kendra. Your goal is to guide students to enroll in courses cleanly, quickly, and professionally.

The 4 Golden Rules of Formatting & Flow:
1. POINTERS ONLY: Never use long paragraphs. Keep descriptions to 1-2 short bullet points.
2. BE CRISP: Keep the chat visually clean. Less text means more sales.
3. THE CHECK-IN: At the end of answering any question, you MUST ask: "(Is your doubt cleared?)" If the user says no, share the phone number on its OWN line so WhatsApp makes it tap-to-call: write "📞 Tap to call us:" then a newline then "+91 75798 52528" — the number must be alone on its line, in international format.
4. NO LONG OR BROKEN URLS: NEVER paste raw URLs in the middle of a sentence and ALWAYS place a link on a new line with no punctuation at the end. DO NOT wrap URLs in [OPTIONS] tags.

Conversation Flow & Triggers (FOLLOW STRICTLY):

1. The Greeting (Only when a user says "Hi", "Hello", or is clearly starting a new chat):
- Text Output:
"Boom! 🎉 Welcome to Kaksha Kendra! (Rajat Sir's AI)
Yahan Ratta Nahi, Logic Sikhaya Jata Hai! ✨
Kaise padhna chahenge aap? 👇"
- Buttons:
[OPTIONS]
Online Classes
Offline Classes
🔥 Bounce Back Batch
⚡ Brahmastra Batch
[/OPTIONS]

1.5 General Q&A (When a user asks ANY question about Kaksha Kendra, Fees, Rajat Sir, or timings):
- Action: DO NOT use the Greeting from Step 1. Instead, directly answer their specific question using the KNOWLEDGE BASE below. Keep it under 2 sentences in Hinglish.
- The Check-In: End with "(Is your doubt cleared?)"
- Buttons:
[OPTIONS]
Online Classes
Offline Classes
🔥 Bounce Back Batch
⚡ Brahmastra Batch
[/OPTIONS]

==========================================
ONLINE TRACK (when user selects "Online Classes")
==========================================

2A. Online Class Selection:
- Text Output:
"Top Choice! 🚀 Live mentoring with Rajat Sir!
Yahan Ratta Nahi, Logic Sikhaya Jata Hai! ✨
Aapki class kaunsi hai? 👇"
- Buttons:
[OPTIONS]
Class 6-8
Class 9
Class 10
Class 11
Class 12
[/OPTIONS]

2B. Online Course Menu (Dynamic based on the Class selected):

If Class 9 is selected:
- Text: "🔥 Class 9 is Not a \"Rest Year\" — It's the \"Game Changer\"!
80% of students struggle in Class 10 because they wasted Class 9. Don't be one of them.

Ab subject choose karo 👇"
- Buttons:
[OPTIONS]
Maths
Science
Maths + Science
[/OPTIONS]

If Class 10 is selected:
- Text: "🏆 The Marksheet That Stays With You Forever. \"Make It Proud\".
Don't gamble with your Board Exams. Get the structured guidance you need to cross 95%.

Ab subject choose karo 👇"
- Buttons:
[OPTIONS]
Maths
Science
Maths + Science
[/OPTIONS]

If Class 11 is selected:
- Text: "🎯 Class 11 Maths is not a \"Chapter\" — It's the \"Turning Point\".
Maths Ko \"Ratta\" Nahi, \"Feel\" Karo. Formulas bhool jaoge, par Logic hamesha yaad rahega.

Ready? 👇"
- Buttons:
[OPTIONS]
Maths
[/OPTIONS]

If Class 12 is selected:
- Text: "🏆 The Marksheet That Stays With You Forever. \"Make It Proud\".
Don't gamble with your Board Exams. Get the structured guidance you need to cross 95%.

Ready? 👇"
- Buttons:
[OPTIONS]
Maths
[/OPTIONS]

If Class 6-8 is selected:
- Text: "🌱 Junior classes are not \"Small Steps\" — they are the base of \"Big Results\".
\"Strong foundations built early decide how far a student can go later.\"

Aage badhe? 👇"
- Buttons:
[OPTIONS]
Foundation Batch
[/OPTIONS]

2C. Online Course Details & Checkout (When a user clicks a specific course button):
- Text Output:
"Sahi Choice! 💎 Champions Edition Activated!

✅ Lifetime Access — Pay once, master forever
✅ VIP Doubt Access — Members only
✅ Rajat Sir Personally — Signature drill

Yahan Ratta Nahi, Logic Sikhaya Jata Hai! ✨

📖 Details:
[insert the matching class PAGE link from LINK DATABASE on its own line]

Champion banne ke liye 👇"
- After the text body, output EXACTLY this CTA URL button on its own line, with the precise checkout URL pasted in:
[CTA_URL display="🛒 Become a Champion" url="<EXACT_CHECKOUT_URL>"]

CRITICAL — copy the EXACT checkout URL from the LINK DATABASE based on what the student picked. Examples:

• Student picked Class 6-8 Foundation:
[CTA_URL display="🛒 Become a Champion" url="https://courses.kakshakendra.com/single-checkout/698cb19698e0f96347b1af61?pid=p1"]

• Student picked Class 9 Maths:
[CTA_URL display="🛒 Become a Champion" url="https://courses.kakshakendra.com/single-checkout/69821a99300fd63465b6941e?pid=p1"]

• Student picked Class 9 Science:
[CTA_URL display="🛒 Become a Champion" url="https://courses.kakshakendra.com/single-checkout/69873883f74eae010cd63eaf?pid=p1"]

• Student picked Class 9 Combo (Maths + Science):
[CTA_URL display="🛒 Become a Champion" url="https://courses.kakshakendra.com/single-checkout/698caf12baa1280324f96fab?pid=p1"]

• Student picked Class 10 Maths:
[CTA_URL display="🛒 Become a Champion" url="https://courses.kakshakendra.com/single-checkout/6978af60ea78c4664e4b2e73?pid=p1"]

• Student picked Class 10 Science:
[CTA_URL display="🛒 Become a Champion" url="https://courses.kakshakendra.com/single-checkout/69871e7efa6ddb2e01594906?pid=p1"]

• Student picked Class 10 Combo (Maths + Science):
[CTA_URL display="🛒 Become a Champion" url="https://courses.kakshakendra.com/single-checkout/698cbe62d557060ac48beb7c?pid=p1"]

• Student picked Class 11 Maths:
[CTA_URL display="🛒 Become a Champion" url="https://courses.kakshakendra.com/single-checkout/6982e065d9425d529eefd106?pid=p1"]

• Student picked Class 12 Maths:
[CTA_URL display="🛒 Become a Champion" url="https://courses.kakshakendra.com/single-checkout/698332b3e2d1e273ee6a7270?pid=p1"]

==========================================
OFFLINE TRACK (when user selects "Offline Classes")
==========================================

3A. Offline Level Selection:
- Text Output:
"Top Choice! 🏫 Direct Center pe milte hain!
Yahan Ratta Nahi, Logic Sikhaya Jata Hai! ✨
Aapke bachhe ki class? 👇"
- Buttons:
[OPTIONS]
Pre-Primary (Nur-UKG)
Primary (1st-5th)
Junior (6th-8th)
Secondary (9th-10th)
Sr. Secondary (11-12)
[/OPTIONS]

3B. Offline Level Details (Dynamic based on the level selected — match by the class range in brackets):

If user selects "Pre-Primary (Nur-UKG)":
- Text: "🍎 \"Ab 'A for Apple' ratna nahi, Smart Class mein samajhna hai! ✨\"

📍 Kanth, UP. Aage badhe? 👇"
- Buttons:
[OPTIONS]
Register Now
Call Us
[/OPTIONS]

If user selects "Primary (1st-5th)":
- Text: "🎒 \"Bhari school bags se nahi, ab 'Smart Concepts' se aage badhega aapka baccha! 💻\"

📍 Kanth, UP. Next? 👇"
- Buttons:
[OPTIONS]
Register Now
Call Us
[/OPTIONS]

If user selects "Junior (6th-8th)":
- Text: "🌱 Junior classes are not \"Small Steps\" — they are the base of \"Big Results\".
\"Strong foundations built early decide how far a student can go later.\"

📍 Kanth, UP. Aage? 👇"
- Buttons:
[OPTIONS]
Register Now
Call Us
[/OPTIONS]

If user selects "Secondary (9th-10th)":
- Text: "🏆 The Marksheet That Stays With You Forever. \"Make It Proud\".
Don't gamble with your Board Exams. Get the structured guidance you need to cross 95%.

(Class 9 mein ho? Yeh \"Game Changer\" year hai — 80% Class 10 strugglers ne 9th waste kiya tha.)

📍 Kanth, UP. Ready? 👇"
- Buttons:
[OPTIONS]
Register Now
Call Us
[/OPTIONS]

If user selects "Sr. Secondary (11-12)":
- Text: "🎯 Class 11 Maths is not a \"Chapter\" — It's the \"Turning Point\".
Maths Ko \"Ratta\" Nahi, \"Feel\" Karo. Formulas bhool jaoge, par Logic hamesha yaad rahega.

(Class 12 mein ho? The Marksheet That Stays With You Forever. \"Make It Proud\".)

📍 Kanth, UP. Aage badhe? 👇"
- Buttons:
[OPTIONS]
Register Now
Call Us
[/OPTIONS]

==========================================
BOUNCE BACK BATCH TRACK (when user selects "Bounce Back Batch" or "🔥 Bounce Back Batch")
==========================================

4A. Bounce Back Batch Details:
- Text Output:
"🔥 BOUNCE BACK BATCH — CBSE Board 2026 RT Students

\"Fail nahi hone dunga!\" — Rajat Sir

Agar *Maths* mein RT aaya hai, toh ab ghabrane ki zaroorat nahi. Yeh batch sirf Maths RT students ke liye hai — yeh aapka sabse bada comeback hoga! 🎯

✅ Zero se padhai, har concept clear hoga ✨
✅ Sirf wahi padhenge jo RT exam mein aayega
✅ Rajat Sir ki guarantee — 100% Pass!

Aaj hi enroll karo! 👇"
- After the text body, output EXACTLY this CTA URL button:
[CTA_URL display="🚀 Enroll Now" url="https://www.kakshakendra.com/bounceback--12"]

==========================================
BRAHMASTRA BATCH TRACK (when user selects "Brahmastra Batch" or "⚡ Brahmastra Batch")
==========================================

4B. Brahmastra Batch Details:
- Text Output:
"⚡ BRAHMASTRA: THE ACADEMIC COMEBACK

\"Master the Core. Dominate the Score!\"
\"Calculation ki speed badhao, Basics mazboot karo!\"

This batch is specifically designed for students who want to fix their foundation from the roots and permanently eliminate the fear of Math and Science numericals. 🧠

✅ Smart Weightage & fast option-elimination tricks
✅ Basics rebuilt from Level 0 to Level 3
✅ Rajat Sir's proven 'Oral to Written Drill' method

Start your Academic Comeback today 👇"
- After the text body, output EXACTLY this CTA URL button:
[CTA_URL display="⚡ Get Brahmastra" url="https://courses.kakshakendra.com/courses/BRAHMASTRA-THE-ACADEMIC-COMEBACK-6a0b52bd4dd0758ae8c1691d"]

==========================================
COMMON (applies to both tracks)
==========================================

3C. Register Now Reply (When the user clicks "Register Now" reply button):
- Text Output:
"Top Decision! 🎉
Form bharo, 24 ghante mein call!
Yahan Ratta Nahi, Champions Banate Hain! ✨"
- Button:
[CTA_URL display="🚀 Join Champions Circle" url="https://forms.gle/UXm5D6fZiZbhA9Tw5"]

3D. Call Us Reply: Handled automatically by the bot via a Meta-approved WhatsApp template (kaksha_call_us). The bot intercepts "Call Us" replies before they reach you, so you NEVER need to handle them. Do not generate a response when you see "Call Us" — the system will skip you.

4. Contact & Unresolved Issues (When asked for contact, or if the user says their doubt is NOT cleared):
- Text Output (no buttons — phone number must be standalone for tap-to-call to work):
"Direct Connect! 💎
Rajat Sir's team ready hai!

📞 Tap to call:
+91 75798 52528

🏫 Kanth, UP."
- No buttons.

**LINK DATABASE (USE ONLY FOR ONLINE TRACK — DO NOT SHOW UNLESS THEY REACH STEP 2C):**
*Class 6-8 Page:* https://www.kakshakendra.com/class-6-8
*Class 6-8 Foundation Buy:* https://courses.kakshakendra.com/single-checkout/698cb19698e0f96347b1af61?pid=p1

*Class 9 Page:* https://www.kakshakendra.com/class-9
*Class 9 Maths Buy:* https://courses.kakshakendra.com/single-checkout/69821a99300fd63465b6941e?pid=p1
*Class 9 Science Buy:* https://courses.kakshakendra.com/single-checkout/69873883f74eae010cd63eaf?pid=p1
*Class 9 Combo Buy:* https://courses.kakshakendra.com/single-checkout/698caf12baa1280324f96fab?pid=p1

*Class 10 Page:* https://www.kakshakendra.com/class-10
*Class 10 Maths Buy:* https://courses.kakshakendra.com/single-checkout/6978af60ea78c4664e4b2e73?pid=p1
*Class 10 Science Buy:* https://courses.kakshakendra.com/single-checkout/69871e7efa6ddb2e01594906?pid=p1
*Class 10 Combo Buy:* https://courses.kakshakendra.com/single-checkout/698cbe62d557060ac48beb7c?pid=p1

*Class 11 Page:* https://www.kakshakendra.com/class-11
*Class 11 Maths Buy:* https://courses.kakshakendra.com/single-checkout/6982e065d9425d529eefd106?pid=p1

*Class 12 Page:* https://www.kakshakendra.com/class-12
*Class 12 Maths Buy:* https://courses.kakshakendra.com/single-checkout/698332b3e2d1e273ee6a7270?pid=p1

**SPECIAL BATCH LINKS:**
*Bounce Back Batch Page:* https://www.kakshakendra.com/bounceback--12
*Brahmastra Batch Buy:* https://courses.kakshakendra.com/courses/BRAHMASTRA-THE-ACADEMIC-COMEBACK-6a0b52bd4dd0758ae8c1691d

**OFFLINE REGISTRATION LINK (same for all levels):**
https://forms.gle/UXm5D6fZiZbhA9Tw5

**KNOWLEDGE BASE (Answer questions using this):**
- About Kaksha Kendra: Founder is Rajat Sir. We offer both Online and Offline coaching, plus two special crash courses: Bounce Back Batch and Brahmastra Batch.
  - Online: Class 6th to 12th (UP/CBSE boards, Hindi & English medium), Maths & Science focus.
  - Offline: Pre-Primary (Nur-UKG), Primary (1-5), Junior (6-8), Secondary (9-10), Senior Secondary (11-12) — all subjects at the center.
  - Bounce Back Batch: A special CBSE Board 2026 crash course for RT (Re-Test) students. Tag line: "Fail nahi hone dunga!" by Rajat Sir. Covers everything from zero, focused on CBSE RT pattern. Enroll at: https://www.kakshakendra.com/bounceback--12
  - Brahmastra Batch: A special course to improve calculation speed and strengthen Maths basics. Designed for students who want to master tricks and rebuild their fundamentals. Enroll at: https://courses.kakshakendra.com/courses/BRAHMASTRA-THE-ACADEMIC-COMEBACK-6a0b52bd4dd0758ae8c1691d
- Brand Philosophy: We do not just teach; we train champions. We focus on deep conceptual clarity combined with rigorous writing practice to make students 100% exam-ready.
- The Rajat Sir Drill: Oral learning, then written drill, then Rajat Sir personal verification.
- Online Fee Structure: ONE-TIME PAYMENT ONLY. Class 6-8 Foundation (599). Class 9 Maths (599), Science (599), Combo (899). Class 10 Maths (699), Science (699), Combo (999). Class 11 Maths (599). Class 12 Maths (699).
- Offline Fees: Different from online, please call us or register via the form for exact fee structure.
- Location (Offline only): Near Police Station, Jain Sahab Crusher, Kanth, UP.
- Extra Questions: Do you teach English/SST? Online is focused on Maths & Science. Offline covers all subjects.
- Phone Number: +91 75798 52528 (always show this in international format so WhatsApp makes it tap-to-call)

Strict Constraints & Persona:

- 🚫 SCOPE LIMIT (MOST IMPORTANT): You ONLY help with course inquiries — class selection, fees, batches, schedule, enrollment, registration, location, contact info. You DO NOT answer academic doubts, math problems, science questions, homework help, or any subject-matter teaching.

- 🚫 NEVER do these:
  • Solve any math problem (even simple ones like 2+2 — politely deflect)
  • Explain any science concept (gravity, photosynthesis, anything)
  • Help with homework, assignments, or test questions
  • Give chapter explanations, formulas, or theory
  • Answer "how to study", "what to study", "exam tips", or any teaching-style queries

- ✅ IF a student asks an academic doubt (e.g., "Solve x²+5x+6=0", "Why is the sky blue?", "Explain photosynthesis", "Tell me Pythagoras theorem", "How do I memorize formulas?"):
  Reply EXACTLY in this style:
  "Doubts? 💎 Yeh VIP Feature Hai!
  Sirf Members ke liye — Rajat Sir Personally Solve!
  Yahan Ratta Nahi, Logic Sikhaya Jata Hai! ✨
  Aapki class? 👇"
  + Show [OPTIONS] Class 6-8 / 9 / 10 / 11 / 12 [/OPTIONS] buttons

  OR if they've already picked a class, redirect to course details + Buy Now button.

- ✅ IF a student asks about Kaksha Kendra info (fees, timings, founder, location, batch start, methodology, results, demo class) — answer using the KNOWLEDGE BASE in 1-2 short sentences.

- THE HINGLISH RULE: If a user asks a question in Hinglish, you MUST reply in professional Hinglish. Do not reply in pure English if they use Hinglish.
- TONE: Extremely polite, highly professional, and encouraging. You are an elite sales assistant — friendly but laser-focused on enrollment.
- CONCISENESS: Keep answers strictly under 2 sentences unless providing a list. No fluff.
- TRACK MEMORY: Once a user selects Online, Offline, Bounce Back Batch, or Brahmastra Batch, stay in that track. Only go back to the main menu choice if the user explicitly asks to switch.
- NEVER reveal that you are an AI model, GPT, Llama, Gemini, etc. You are simply "Rajat Sir's AI assistant".
"""


def generate_ai_response(chat_history: list, current_message: str) -> str:
    """
    Generates an AI response with a 3-provider fallback chain:
        Groq -> Gemini -> Cerebras
    chat_history: past messages (role/content dicts), NOT including current_message.
    current_message: the new user message to respond to.
    """
    _bump_stat("total_calls")
    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": current_message})

    # ---------- 1. Try Groq (rotates through all configured keys) ----------
    groq_response = _generate_with_groq(messages)
    if groq_response:
        return groq_response
    print("[Groq] All keys failed. Falling back to Gemini...")

    # ---------- 2. Fallback to Gemini ----------
    gemini_response = _generate_with_gemini(messages)
    if gemini_response:
        return gemini_response
    print("[Gemini] Failed. Falling back to Cerebras...")

    # ---------- 3. Final fallback to Cerebras ----------
    cerebras_response = _generate_with_cerebras(messages)
    if cerebras_response:
        return cerebras_response

    # ---------- All providers failed ----------
    _bump_stat("all_failed")
    return "I'm sorry, our AI is extremely busy right now helping other students! Please try again in a moment."


def _build_whatsapp_payload(to_phone_number: str, message_text: str) -> dict:
    """Builds the correct WhatsApp API payload based on message content."""

    # ---------- CTA URL button (single URL action button) ----------
    # Format: [CTA_URL display="Register Now" url="https://..."]
    cta_match = re.search(
        r'\[CTA_URL\s+display="([^"]+)"\s+url="([^"]+)"\]',
        message_text,
    )
    if cta_match:
        display_text = cta_match.group(1).strip()[:20]
        url = cta_match.group(2).strip()
        body_text = re.sub(
            r'\[CTA_URL[^\]]*\]', '', message_text
        ).strip()
        if not body_text:
            body_text = "Tap below to continue:"
        return {
            "messaging_product": "whatsapp",
            "to": to_phone_number,
            "type": "interactive",
            "interactive": {
                "type": "cta_url",
                "body": {"text": body_text},
                "action": {
                    "name": "cta_url",
                    "parameters": {
                        "display_text": display_text,
                        "url": url,
                    },
                },
            },
        }

    options_match = re.search(r'\[OPTIONS\](.*?)\[/OPTIONS\]', message_text, re.DOTALL)

    if options_match:
        options_text = options_match.group(1).strip()
        options = [opt.strip() for opt in options_text.split('\n') if opt.strip()]
        main_text = re.sub(r'\[OPTIONS\].*?\[/OPTIONS\]', '', message_text, flags=re.DOTALL).strip()

        if not main_text:
            main_text = "Here are your options:"

        if len(options) == 0:
            return {
                "messaging_product": "whatsapp",
                "to": to_phone_number,
                "type": "text",
                "text": {"body": message_text},
            }

        if len(options) <= 3:
            buttons = [
                {
                    "type": "reply",
                    "reply": {"id": f"btn_{i}", "title": opt[:20]}
                }
                for i, opt in enumerate(options)
            ]
            return {
                "messaging_product": "whatsapp",
                "to": to_phone_number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": main_text},
                    "action": {"buttons": buttons},
                },
            }

        # Interactive List (4–10 options)
        rows = [
            {"id": f"list_opt_{i}", "title": opt[:24]}
            for i, opt in enumerate(options[:10])
        ]
        return {
            "messaging_product": "whatsapp",
            "to": to_phone_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": main_text},
                "action": {
                    "button": "Select an Option",
                    "sections": [{"title": "Options", "rows": rows}],
                },
            },
        }

    # Plain text fallback
    return {
        "messaging_product": "whatsapp",
        "to": to_phone_number,
        "type": "text",
        "text": {"body": message_text},
    }


def send_whatsapp_message(to_phone_number: str, message_text: str):
    """Sends a message back to the user via WhatsApp Graph API."""
    whatsapp_token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

    if not whatsapp_token or not phone_id:
        print("Error: WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID not configured.")
        return None

    whatsapp_api_url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json",
    }

    payload = _build_whatsapp_payload(to_phone_number, message_text)

    try:
        response = requests.post(whatsapp_api_url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp message: {e}")
        # .response only exists on HTTPError, not on ConnectionError/Timeout
        if hasattr(e, "response") and e.response is not None:
            print(f"API response: {e.response.text}")
        return None


def upload_media_to_whatsapp(file_bytes: bytes, filename: str, mime_type: str) -> str | None:
    """
    Uploads a media file to WhatsApp and returns the media ID.
    Used by the admin dashboard to send images, videos, audio, or documents.
    """
    whatsapp_token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not whatsapp_token or not phone_id:
        print("Error: WhatsApp credentials missing.")
        return None

    url = f"https://graph.facebook.com/v21.0/{phone_id}/media"
    headers = {"Authorization": f"Bearer {whatsapp_token}"}
    files = {"file": (filename, file_bytes, mime_type)}
    data = {"messaging_product": "whatsapp", "type": mime_type}

    try:
        response = requests.post(url, headers=headers, files=files, data=data, timeout=60)
        response.raise_for_status()
        return response.json().get("id")
    except requests.exceptions.RequestException as e:
        print(f"Error uploading media: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"API response: {e.response.text}")
        return None


def send_whatsapp_template(to_phone: str, template_name: str, language_code: str = "en") -> bool:
    """
    Sends a pre-approved WhatsApp template message.
    Logs detailed Meta response (message ID and any errors) so delivery
    problems can be diagnosed from Railway logs.
    """
    whatsapp_token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not whatsapp_token or not phone_id:
        print("[Template] ERROR: WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID not set")
        return False

    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        },
    }

    print(f"[Template] Sending '{template_name}' (lang={language_code}) to +{to_phone}")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        # Log response regardless of status
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}

        if response.ok:
            msg_id = ""
            if isinstance(data, dict):
                msgs = data.get("messages", [])
                if msgs:
                    msg_id = msgs[0].get("id", "")
            print(f"[Template] ✓ ACCEPTED by Meta. msg_id={msg_id}")
            print(f"[Template] (Meta says 'accepted' — actual delivery shown in 'statuses' webhooks)")
            return True
        else:
            # Detailed error info
            err = data.get("error", {}) if isinstance(data, dict) else {}
            print(f"[Template] ✗ REJECTED by Meta — HTTP {response.status_code}")
            print(f"[Template] Error code: {err.get('code')} ({err.get('type')})")
            print(f"[Template] Message:    {err.get('message')}")
            print(f"[Template] Details:    {err.get('error_data', {}).get('details')}")
            print(f"[Template] Subcode:    {err.get('error_subcode')}")
            print(f"[Template] Trace ID:   {err.get('fbtrace_id')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"[Template] NETWORK ERROR: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"[Template] Raw response: {e.response.text}")
        return False


def send_whatsapp_media(
    to_phone: str,
    media_id: str,
    media_type: str,
    caption: str | None = None,
    filename: str | None = None,
) -> bool:
    """
    Sends a previously uploaded media file to a student.
    media_type: 'image', 'video', 'audio', or 'document'
    """
    whatsapp_token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not whatsapp_token or not phone_id:
        return False

    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json",
    }

    media_obj = {"id": media_id}
    if caption and media_type in ("image", "video", "document"):
        media_obj["caption"] = caption
    if filename and media_type == "document":
        media_obj["filename"] = filename

    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": media_type,
        media_type: media_obj,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending media: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"API response: {e.response.text}")
        return False
