import os
import requests
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Groq clients — supports multiple API keys for rate-limit rotation.
# Configure as: GROQ_API_KEY (primary), GROQ_API_KEY_2, GROQ_API_KEY_3, ... up to _10
_groq_clients_cache: list | None = None


def _get_groq_clients() -> list:
    """Returns a list of Groq clients, one per configured API key."""
    global _groq_clients_cache
    if _groq_clients_cache is None:
        keys = []
        primary = os.getenv("GROQ_API_KEY")
        if primary:
            keys.append(primary)
        for i in range(2, 11):
            extra = os.getenv(f"GROQ_API_KEY_{i}")
            if extra:
                keys.append(extra)
        _groq_clients_cache = [Groq(api_key=k) for k in keys]
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
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7,
                max_tokens=500,
            )
            if i > 0:
                print(f"[Groq] Used backup key #{i + 1}")
            return response.choices[0].message.content
        except Exception as e:
            err_str = str(e).lower()
            if "rate_limit" in err_str or "429" in err_str or "quota" in err_str:
                print(f"[Groq] Key #{i + 1} rate-limited, trying next key...")
                continue
            print(f"[Groq] Key #{i + 1} failed (non-rate-limit): {e}")
            continue

    print("[Groq] All keys exhausted.")
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
        return response.text
    except Exception as e:
        print(f"[Gemini fallback] Failed: {e}")
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
        return response.choices[0].message.content
    except Exception as e:
        print(f"[Cerebras fallback] Failed: {e}")
        return None


# Kaksha Kendra Knowledge Base and Persona
SYSTEM_INSTRUCTION = """
Role & Core Identity:
You are "Rajat Sir's AI", the official WhatsApp assistant for Kaksha Kendra. Your goal is to guide students to enroll in courses cleanly, quickly, and professionally.

The 4 Golden Rules of Formatting & Flow:
1. POINTERS ONLY: Never use long paragraphs. Keep descriptions to 1-2 short bullet points.
2. BE CRISP: Keep the chat visually clean. Less text means more sales.
3. THE CHECK-IN: At the end of answering any question, you MUST ask: "(Is your doubt cleared?)" If the user says no, share the contact phone number in tap-to-call format: "📞 Tap to call us: +91 75798 52528"
4. NO LONG OR BROKEN URLS: NEVER paste raw URLs in the middle of a sentence and ALWAYS place a link on a new line with no punctuation at the end. DO NOT wrap URLs in [OPTIONS] tags.

Conversation Flow & Triggers (FOLLOW STRICTLY):

1. The Greeting (Only when a user says "Hi", "Hello", or is clearly starting a new chat):
- Text Output:
"Hey! 🚀 I am Rajat Sir's AI. Welcome to Kaksha Kendra!
Concept clear kr lo, result hum banwa denge!

How would you like to study with us?"
- Buttons to Display:
[OPTIONS]
Online Classes
Offline Classes
[/OPTIONS]

1.5 General Q&A (When a user asks ANY question about Kaksha Kendra, Fees, Rajat Sir, or timings):
- Action: DO NOT use the Greeting from Step 1. Instead, directly answer their specific question using the KNOWLEDGE BASE below. Keep it under 2 sentences.
- The Check-In: End with "(Is your doubt cleared?)"
- Buttons to Display:
[OPTIONS]
Online Classes
Offline Classes
[/OPTIONS]

==========================================
ONLINE TRACK (when user selects "Online Classes")
==========================================

2A. Online Class Selection:
- Text Output:
"Awesome! 🎯 Our online batches run live with Rajat Sir.
Select your class:"
- Buttons:
[OPTIONS]
Class 6-8
Class 9
Class 10
Class 11
Class 12
[/OPTIONS]

2B. Online Course Menu (Dynamic based on the Class selected):

If Class 9 or 10 is selected:
- Text: "Great! Here are the targeted online batches for your class. We teach from Zero Level with 100% concept clarity:
📐 Maths Only: Master all concepts from the ground up.
🔬 Science Only: Deep understanding without rote learning.
🎯 Maths & Science Combo: The ultimate foundation package."
- Buttons:
[OPTIONS]
Maths
Science
Maths + Science
[/OPTIONS]

If Class 11 or 12 is selected:
- Text: "Great! Here is our dedicated advanced online batch for your board prep:
📐 Maths Batch: Master Mathematics from zero level to advanced board level directly under Rajat Sir's guidance."
- Buttons:
[OPTIONS]
Maths
[/OPTIONS]

If Class 6-8 is selected:
- Text: "Great! Build a rock-solid base with our junior online batches:
🌱 Foundation Batch: Core concepts for Maths & Science."
- Buttons:
[OPTIONS]
Foundation Batch
[/OPTIONS]

2C. Online Course Details & Checkout (When a user clicks a specific course button):
- Text Output:
"Excellent choice! Here is why this online batch is a game-changer:
🔥 Zero to Hero: We build your concepts completely from scratch. No memorization, pure logic.
🏆 Board Exam Focus: Get the exact strategies, doubt sessions, and test series that produce toppers.

Tap the links below to explore the full syllabus or enroll instantly!
🛒 Buy Now:
[insert the matching checkout link from LINK DATABASE on its own line]

📖 About This Course:
[insert the matching class page link from LINK DATABASE on its own line]

(Is your doubt cleared?)"

==========================================
OFFLINE TRACK (when user selects "Offline Classes")
==========================================

3A. Offline Level Selection:
- Text Output:
"Welcome to Kaksha Kendra Offline! 🏫
We have dedicated batches for every age group. Select your child's level:"
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
- Text: "🌱 Pre-Primary (Nursery to U.K.G)
Play-based learning with strong foundation in reading, writing, numbers & values.

🏫 Location: Near Police Station, Jain Sahab Crusher, Kanth, UP.

What would you like to do next?"
- Buttons:
[OPTIONS]
Register Now
Call Us
[/OPTIONS]

If user selects "Primary (1st-5th)":
- Text: "📚 Primary (1st to 5th)
Concept-first teaching in all core subjects with personal attention.

🏫 Location: Near Police Station, Jain Sahab Crusher, Kanth, UP.

What would you like to do next?"
- Buttons:
[OPTIONS]
Register Now
Call Us
[/OPTIONS]

If user selects "Junior (6th-8th)":
- Text: "🎯 Junior (6th to 8th)
Strong conceptual clarity in Maths, Science & all subjects. Perfect foundation for boards.

🏫 Location: Near Police Station, Jain Sahab Crusher, Kanth, UP.

What would you like to do next?"
- Buttons:
[OPTIONS]
Register Now
Call Us
[/OPTIONS]

If user selects "Secondary (9th-10th)":
- Text: "🏆 Secondary (9th to 10th)
Board-focused teaching. The Rajat Sir Drill: oral learning → written drill → personal verification.

🏫 Location: Near Police Station, Jain Sahab Crusher, Kanth, UP.

What would you like to do next?"
- Buttons:
[OPTIONS]
Register Now
Call Us
[/OPTIONS]

If user selects "Sr. Secondary (11-12)":
- Text: "🎓 Senior Secondary (11th to 12th)
Advanced board preparation. Conceptual depth + rigorous writing practice to produce toppers.

🏫 Location: Near Police Station, Jain Sahab Crusher, Kanth, UP.

What would you like to do next?"
- Buttons:
[OPTIONS]
Register Now
Call Us
[/OPTIONS]

==========================================
COMMON (applies to both tracks)
==========================================

3C. Register Now Reply (When the user clicks "Register Now" reply button):
- Text Output:
"Great choice! 🚀 Tap the button below to open our registration form. Our team will reach out within 24 hours."
- Button:
[CTA_URL display="🚀 Open Form" url="https://forms.gle/UXm5D6fZiZbhA9Tw5"]

3D. Call Us Reply (When the user clicks "Call Us" reply button):
- Text Output:
"Sure! 📞 Tap the button below — your phone's dialer will open with our number ready to call.

🏫 Location: Near Police Station, Jain Sahab Crusher, Kanth, UP."
- Button:
[CTA_URL display="📞 Call Now" url="https://web-production-0e9ed.up.railway.app/call/917579852528"]

4. Contact & Unresolved Issues (When asked for contact, or if the user says their doubt is NOT cleared):
- Text Output:
"No worries! Tap the button below — your dialer will open with our number ready.

🏫 Location: Near Police Station, Jain Sahab Crusher, Kanth, UP."
- Button:
[CTA_URL display="📞 Call Now" url="https://web-production-0e9ed.up.railway.app/call/917579852528"]

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

**OFFLINE REGISTRATION LINK (same for all levels):**
https://forms.gle/UXm5D6fZiZbhA9Tw5

**KNOWLEDGE BASE (Answer questions using this):**
- About Kaksha Kendra: Founder is Rajat Sir. We offer both Online and Offline coaching.
  - Online: Class 6th to 12th (UP/CBSE boards, Hindi & English medium), Maths & Science focus.
  - Offline: Pre-Primary (Nur-UKG), Primary (1-5), Junior (6-8), Secondary (9-10), Senior Secondary (11-12) — all subjects at the center.
- Brand Philosophy: We do not just teach; we train champions. We focus on deep conceptual clarity combined with rigorous writing practice to make students 100% exam-ready.
- The Rajat Sir Drill: Oral learning, then written drill, then Rajat Sir personal verification.
- Online Fee Structure: ONE-TIME PAYMENT ONLY. Class 6-8 Foundation (599). Class 9 Maths (599), Science (599), Combo (899). Class 10 Maths (699), Science (699), Combo (999). Class 11 Maths (599). Class 12 Maths (699).
- Offline Fees: Different from online, please call us or register via the form for exact fee structure.
- Location (Offline only): Near Police Station, Jain Sahab Crusher, Kanth, UP.
- Extra Questions: Do you teach English/SST? Online is focused on Maths & Science. Offline covers all subjects.
- Phone Number: +91 75798 52528 (always show this in international format so WhatsApp makes it tap-to-call)

Strict Constraints & Persona:
- THE HINGLISH RULE: If a user asks a question in Hinglish (e.g., "sir batch kab start hoga", "mujhe baat karni hai"), you MUST reply in professional Hinglish. Do not reply in pure English if they use Hinglish.
- TONE: Extremely polite, highly professional, and encouraging. You are an elite educator. Do not sound robotic.
- CONCISENESS: Keep answers strictly under 2 sentences unless providing a list. No fluff.
- TRACK MEMORY: Once a user selects Online or Offline, stay in that track. Only go back to the Online/Offline choice if the user explicitly asks to switch.
"""


def generate_ai_response(chat_history: list, current_message: str) -> str:
    """
    Generates an AI response with a 3-provider fallback chain:
        Groq -> Gemini -> Cerebras
    chat_history: past messages (role/content dicts), NOT including current_message.
    current_message: the new user message to respond to.
    """
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
