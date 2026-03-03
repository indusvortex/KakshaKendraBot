import sqlite3
import re
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

def get_payload(message_text: str):
    options_match = re.search(r'\[OPTIONS\](.*?)\[/OPTIONS\]', message_text, re.DOTALL)
    
    if options_match:
        options_text = options_match.group(1).strip()
        options = [opt.strip() for opt in options_text.split('\n') if opt.strip()]
        main_text = re.sub(r'\[OPTIONS\].*?\[/OPTIONS\]', '', message_text, flags=re.DOTALL).strip()
        
        if not main_text:
            main_text = 'Please select an option:'
            
        if len(options) == 0:
            payload = {'messaging_product': 'whatsapp', 'to': os.getenv('TEST_PHONE', '919012345678'), 'type': 'text', 'text': {'body': message_text}}
        elif len(options) <= 3:
            buttons = []
            for i, opt in enumerate(options):
                buttons.append({'type': 'reply', 'reply': {'id': f'btn_{i}', 'title': opt[:20]}})
            payload = {'messaging_product': 'whatsapp', 'to': os.getenv('TEST_PHONE', '919012345678'), 'type': 'interactive', 'interactive': {'type': 'button', 'body': {'text': main_text}, 'action': {'buttons': buttons}}}
        else:
            rows = []
            for i, opt in enumerate(options[:10]):
                rows.append({'id': f'list_opt_{i}', 'title': opt[:24]})
            payload = {'messaging_product': 'whatsapp', 'to': os.getenv('TEST_PHONE', '919012345678'), 'type': 'interactive', 'interactive': {'type': 'list', 'body': {'text': main_text}, 'action': {'button': 'Select Class', 'sections': [{'title': 'Options', 'rows': rows}]}}}
    else:
        payload = {'messaging_product': 'whatsapp', 'to': os.getenv('TEST_PHONE', '919012345678'), 'type': 'text', 'text': {'body': message_text}}
    
    return payload

conn = sqlite3.connect('whatsapp_bot.db')
res = conn.execute("SELECT sender_id, content FROM messages WHERE role='assistant' ORDER BY id DESC LIMIT 1").fetchone()

payload = get_payload(res[1])
payload['to'] = res[0]

whatsapp_api_url = f"https://graph.facebook.com/v19.0/{os.getenv('WHATSAPP_PHONE_NUMBER_ID')}/messages"

headers = {
    'Authorization': f"Bearer {os.getenv('WHATSAPP_TOKEN')}",
    'Content-Type': 'application/json',
}

response = requests.post(whatsapp_api_url, headers=headers, json=payload)
with open('error.json', 'w') as f:
    f.write(response.text)
