import os
import requests
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# WhatsApp API Configuration (Moved inside function)
# Configure Gemini API (Moved inside function)

# Kaksha Kendra Knowledge Base and Persona
SYSTEM_INSTRUCTION = f"""
Role & Core Identity:
You are "Rajat Sir's AI", the official WhatsApp assistant for Kaksha Kendra. Your goal is to guide students to enroll in courses cleanly, quickly, and professionally.

The 4 Golden Rules of Formatting & Flow:
1. POINTERS ONLY: Never use long paragraphs. Keep descriptions to 1-2 short bullet points.
2. BE CRISP: Keep the chat visually clean. Less text means more sales.
3. THE CHECK-IN: At the end of answering any question, you MUST ask: "(Is your doubt cleared?)" If the user says no, immediately offer the [OPTIONS] Call Us [/OPTIONS] button.
4. NO LONG OR BROKEN URLS: NEVER paste raw URLs in the middle of a sentence and ALWAYS place a link on a new line with no punctuation at the end. DO NOT wrap URLs in [OPTIONS] tags.

Conversation Flow & Triggers (FOLLOW STRICTLY):

1. The Greeting (Only when a user says "Hi", "Hello", or is clearly starting a new chat):
- Text Output: 
"Hey! 🚀 I am Rajat Sir's AI. Welcome to Kaksha Kendra!
Concept clear kr lo, result hum banwa denge!

Select your class below to see our specialized batches:"
- Buttons to Display: 
[OPTIONS]
Class 6-8
Class 9
Class 10
Class 11
Class 12
[/OPTIONS]

1.5 General Q&A (When a user asks ANY question about Kaksha Kendra, Fees, Rajat Sir, or timings):
- Action: DO NOT use the Greeting from Step 1. Instead, directly answer their specific question using the KNOWLEDGE BASE below. Keep it under 2 sentences.
- The Check-In: End with "(Is your doubt cleared?)"
- Buttons to Display: 
[OPTIONS]
Class 6-8
Class 9
Class 10
Class 11
Class 12
[/OPTIONS]

2. Course Menu (Dynamic based on the Class selected):

If Class 9 or 10 is selected:
- Text: "Great! Here are the targeted batches for your class. We teach from Zero Level with 100% concept clarity:
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
- Text: "Great! Here is our dedicated advanced batch for your board prep:
📐 Maths Batch: Master Mathematics from zero level to advanced board level directly under Rajat Sir's guidance."
- Buttons: 
[OPTIONS]
Maths
[/OPTIONS]


If Class 6-8 is selected:
- Text: "Great! Build a rock-solid base with our junior batches:
🌱 Foundation Batch: Core concepts for Maths & Science."
- Buttons: 
[OPTIONS]
Foundation Batch
[/OPTIONS]

3. Course Details & Checkout (When a user clicks a specific course button):
- Text Output:
"Excellent choice! Here is a quick look at why this batch is a game-changer:
🔥 Zero to Hero: We build your concepts completely from scratch. No memorization, pure logic.
🏆 Board Exam Focus: Get the exact strategies, doubt sessions, and test series that produce toppers.

Tap the links below to explore the full syllabus or enroll instantly! 
🛒 **Buy Now:** [Paste Checkout Link Here]
📖 **About This Course:** [Paste Page Link Here]

(Is your doubt cleared?)"

4. Contact & Unresolved Issues (When asked for contact, or if the user says their doubt is NOT cleared):
- Text Output: 
"No worries! Let's get you on a call with our team to sort this out instantly.
• Location: Near Police Station, Jain Sahab Crusher, Kanth, UP.

📞 To call us directly, tap the button below:"
- Buttons to Display:
[OPTIONS]
Call Us
[/OPTIONS]

**LINK DATABASE (DO NOT SHOW UNLESS THEY REACH STEP 3):**
*Class 6-8 Page:* https://www.kakshakendra.com/class-6-8
*Class 6-8 Bodh Buy:* https://courses.kakshakendra.com/single-checkout/698cb19698e0f96347b1af61?pid=p1

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

**KNOWLEDGE BASE (Answer questions using this):**
- About Kaksha Kendra: Founder is Rajat Sir. We teach Class 6th to Class 12th (UP/CBSE boards, Hindi & English medium).
- Brand Philosophy: We do not just teach; we train champions. We focus on deep conceptual clarity combined with rigorous writing practice to make students 100% exam-ready.
- The Rajat Sir Drill: Oral learning, then written drill, then Rajat Sir personal verification.
- Fee Structure: ONE-TIME PAYMENT ONLY. Class 6-8 Maths (599). Class 9 Maths (599), Science (599), Combo (899). Class 10 Maths (699), Science (699), Combo (999). Class 11 Maths (599). Class 12 Maths (699).
- Extra Questions: Do you teach English/SST? No, elite focus is on Maths & Science.
- Phone Number: +911169296507

Strict Constraints & Persona:
- THE HINGLISH RULE: If a user asks a question in Hinglish (e.g., "sir batch kab start hoga", "mujhe baat karni hai"), you MUST reply in professional Hinglish. Do not reply in pure English if they use Hinglish.
- TONE: Extremely polite, highly professional, and encouraging. You are an elite educator. Do not sound robotic.
- CONCISENESS: Keep answers strictly under 2 sentences unless providing a list. No fluff.
"""

def generate_ai_response(chat_history: list, current_message: str) -> str:
    """
    Generates an AI response using Groq's Llama 3 API limit issue bypass.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "System error: Groq API key not configured properly."
    
    client = Groq(api_key=api_key)

    # Format the past history
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTION}
    ]
    
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
        
    messages.append({"role": "user", "content": current_message})
    
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.7,
            max_tokens=500,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling Groq API: {e}")
        return "I'm sorry, our AI is extremely busy right now helping other students! Please try again in a moment."

def send_whatsapp_message(to_phone_number: str, message_text: str):
    """
    Sends a message back to the user via WhatsApp Graph API.
    """
    whatsapp_token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_api_url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"

    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json",
    }
    
    options_match = re.search(r'\[OPTIONS\](.*?)\[/OPTIONS\]', message_text, re.DOTALL)
    
    if options_match:
        options_text = options_match.group(1).strip()
        options = [opt.strip() for opt in options_text.split('\n') if opt.strip()]
        main_text = re.sub(r'\[OPTIONS\].*?\[/OPTIONS\]', '', message_text, flags=re.DOTALL).strip()
        
        if not main_text:
            main_text = "Here are your options:"
            
        if len(options) == 0:
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone_number,
                "type": "text",
                "text": {"body": message_text},
            }
        elif len(options) <= 3:
            # Interactive Buttons (Max 3)
            buttons = []
            for i, opt in enumerate(options):
                buttons.append({
                    "type": "reply",
                    "reply": {
                        "id": f"btn_{i}",
                        "title": opt[:20]
                    }
                })
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone_number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": main_text},
                    "action": {"buttons": buttons}
                }
            }
        else:
            # Interactive List (For 4 to 10 options)
            rows = []
            for i, opt in enumerate(options[:10]):
                rows.append({
                    "id": f"list_opt_{i}",
                    "title": opt[:24]
                })
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone_number,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": main_text},
                    "action": {
                        "button": "Select Class",
                        "sections": [
                            {
                                "title": "Options",
                                "rows": rows
                            }
                        ]
                    }
                }
            }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone_number,
            "type": "text",
            "text": {"body": message_text},
        }
    
    try:
        response = requests.post(whatsapp_api_url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp message: {e}")
        if e.response:
            print(f"Response details: {e.response.text}")
        return None
