import sqlite3
import re
import json

def get_payload(message_text: str):
    options_match = re.search(r'\[OPTIONS\](.*?)\[/OPTIONS\]', message_text, re.DOTALL)
    
    if options_match:
        options_text = options_match.group(1).strip()
        options = [opt.strip() for opt in options_text.split('\n') if opt.strip()]
        main_text = re.sub(r'\[OPTIONS\].*?\[/OPTIONS\]', '', message_text, flags=re.DOTALL).strip()
        
        if not main_text:
            main_text = "Please select an option:"
            
        if len(options) == 0:
            payload = {"type": "text", "text": {"body": message_text}}
        elif len(options) <= 3:
            buttons = []
            for i, opt in enumerate(options):
                buttons.append({"type": "reply", "reply": {"id": f"btn_{i}", "title": opt[:20]}})
            payload = {"type": "interactive", "interactive": {"type": "button", "body": {"text": main_text}, "action": {"buttons": buttons}}}
        else:
            rows = []
            for i, opt in enumerate(options[:10]):
                rows.append({"id": f"list_opt_{i}", "title": opt[:24]})
            payload = {"type": "interactive", "interactive": {"type": "list", "body": {"text": main_text}, "action": {"button": "Select Class", "sections": [{"title": "Options", "rows": rows}]}}}
    else:
        payload = {"type": "text", "text": {"body": message_text}}
    print(json.dumps(payload, indent=2))

conn = sqlite3.connect('whatsapp_bot.db')
res = conn.execute("SELECT content FROM messages WHERE role='assistant' ORDER BY id DESC LIMIT 1").fetchone()
get_payload(res[0])
