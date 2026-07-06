import os
import sys
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        if self._pageNumber == 1:
            # Skip header/footer on cover page
            return
            
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor('#1E3A8A'))
        
        # Header text
        self.drawString(54, 790, "KAKSHA KENDRA WHATSAPP BOT")
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor('#64748B'))
        self.drawRightString(541, 790, "COMPLETE MESSAGE FLOW MAP")
        
        # Header line
        self.setStrokeColor(colors.HexColor('#CBD5E1'))
        self.setLineWidth(0.5)
        self.line(54, 782, 541, 782)
        
        # Footer line
        self.line(54, 52, 541, 52)
        
        # Footer text
        self.drawString(54, 40, "Confidential - For Internal Team Reference Only")
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(541, 40, page_text)
        
        self.restoreState()

def build_pdf():
    desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
    pdf_path = os.path.join(desktop, 'Kaksha_Kendra_Complete_Message_Flows.pdf')

    # A4: 595.27 x 842.89 points
    # Margins: Left/Right 54pt (0.75 in), Top 90pt, Bottom 70pt
    doc = SimpleDocTemplate(
        pdf_path, 
        pagesize=A4, 
        leftMargin=54, 
        rightMargin=54, 
        topMargin=90, 
        bottomMargin=70
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#334155'),
        spaceAfter=6
    )
    
    body_bold = ParagraphStyle(
        'CustomBodyBold',
        parent=body_style,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0F172A')
    )
    
    title_style = ParagraphStyle(
        'CustomTitle',
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=30,
        textColor=colors.HexColor('#1E3A8A'),
        alignment=1,
        spaceAfter=10
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#64748B'),
        alignment=1,
        spaceAfter=30
    )
    
    h1_style = ParagraphStyle(
        'CustomH1',
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=22,
        spaceAfter=10,
        keepWithNext=True
    )
    
    h2_style = ParagraphStyle(
        'CustomH2',
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#1E40AF'),
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )
    
    msg_style = ParagraphStyle(
        'MsgStyle',
        fontName='Helvetica',
        fontSize=9,
        leading=13.5,
        textColor=colors.HexColor('#0F172A'),
    )
    
    btn_style = ParagraphStyle(
        'BtnStyle',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#2563EB'),
    )
    
    meta_style = ParagraphStyle(
        'MetaStyle',
        fontName='Helvetica-BoldOblique',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#D97706'),
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        fontName='Helvetica-Bold',
        fontSize=9.0,
        leading=12,
        textColor=colors.white
    )
    
    table_cell_style = ParagraphStyle(
        'TableCell',
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#334155')
    )

    story = []

    # --- COVER PAGE ---
    story.append(Spacer(1, 100))
    # Brand logo block representation
    logo_data = [[Paragraph("<font size=18 color=white><b>KK</b></font>", ParagraphStyle('LogoText', alignment=1))]]
    logo_table = Table(logo_data, colWidths=[60], rowHeights=[60])
    logo_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#1E3A8A')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 15),
    ]))
    story.append(logo_table)
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("KAKSHA KENDRA", title_style))
    story.append(Paragraph("Complete WhatsApp Bot Message Flow Map", subtitle_style))
    
    story.append(Spacer(1, 40))
    
    # Metadata block
    meta_data = [
        [Paragraph("<b>Document Version:</b>", body_style), Paragraph("v2.0 (Interactive Flow Expansion)", body_style)],
        [Paragraph("<b>Generated On:</b>", body_style), Paragraph("June 20, 2026", body_style)],
        [Paragraph("<b>Target Platform:</b>", body_style), Paragraph("WhatsApp Cloud API (Meta)", body_style)],
        [Paragraph("<b>Bot Role:</b>", body_style), Paragraph("Rajat Sir's AI Sales & Support Assistant", body_style)],
        [Paragraph("<b>Audience:</b>", body_style), Paragraph("Internal Team / Admin Dashboard Users", body_style)],
    ]
    t_meta = Table(meta_data, colWidths=[150, 300])
    t_meta.setStyle(TableStyle([
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#F1F5F9')),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_meta)
    
    story.append(Spacer(1, 100))
    story.append(Paragraph("<i>This document provides a complete layout of all automatic replies, interactive buttons, list options, templates, and drip campaigns programmed within the Kaksha Kendra WhatsApp bot.</i>", ParagraphStyle('CoverNote', parent=body_style, alignment=1, textColor=colors.HexColor('#64748B'))))
    story.append(PageBreak())
    
    # --- HELPER FUNCTIONS FOR FLOWABLES ---
    def make_message_bubble(text, buttons=None, title="BOT RESPONSE (MESSAGE)"):
        formatted_text = text.replace('\n', '<br/>')
        content = []
        content.append(Paragraph(f"💬 <b><font color='#475569'>{title}</font></b>", msg_style))
        content.append(Spacer(1, 6))
        content.append(Paragraph(formatted_text, msg_style))
        
        if buttons:
            content.append(Spacer(1, 8))
            content.append(Paragraph("<b>Interactive Option / Buttons:</b>", ParagraphStyle('BtnHeader', parent=msg_style, fontName='Helvetica-Bold', textColor=colors.HexColor('#475569'))))
            for btn in buttons:
                if btn.startswith('🔗') or '[CTA_URL' in btn:
                    content.append(Paragraph(f"⚡ [CTA URL Button] {btn}", btn_style))
                elif btn.startswith('📞') or '[CALL_US' in btn or 'kaksha_call_us' in btn:
                    content.append(Paragraph(f"📞 [Call Template Button] {btn}", meta_style))
                else:
                    content.append(Paragraph(f"🔘 [Quick Reply Button] {btn}", btn_style))
                    
        t = Table([[content]], colWidths=[487])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#E2E8F0')),
            ('LEFTPADDING', (0,0), (-1,-1), 12),
            ('RIGHTPADDING', (0,0), (-1,-1), 12),
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ]))
        return t

    def make_trigger_tag(triggers, context=""):
        content = []
        trigger_text = ", ".join([f"<b>'{t}'</b>" for t in triggers])
        content.append(Paragraph(f"🟢 <b>Trigger Keywords:</b> {trigger_text}", body_style))
        if context:
            content.append(Paragraph(f"ℹ️ <b>Context / Action:</b> {context}", body_style))
            
        t = Table([[content]], colWidths=[487])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#ECFDF5')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#A7F3D0')),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ]))
        return t

    # --- SECTION 1: INTRODUCTION & RULES ---
    story.append(Paragraph("1. System Guidelines & Bot Persona", h1_style))
    story.append(Paragraph("The Kaksha Kendra bot operates under a strict system prompt to ensure optimal conversion rates and professional communication. The core guidelines include:", body_style))
    
    rules = [
        "<b>Pointers Only:</b> Never send long paragraphs. Keep details concise using 1-2 short bullet points.",
        "<b>Crisp Hinglish:</b> Speak in Hinglish (Hindi written in English script) if the user initiates in Hinglish.",
        "<b>Scope Constraint:</b> The bot ONLY handles sales/enrollment inquiries. If academic doubts (e.g. solve a math equation, explain gravity) are sent, the bot deflects using a standardized VIP Members template.",
        "<b>No Broken Links:</b> Place checkout links on a new line without trailing punctuation so they remain clickable.",
        "<b>The Check-In Rule:</b> Always end informational answers with the exact phrase <i>'(Is your doubt cleared?)'</i>. If the student answers 'No', share the tap-to-call phone number on a separate line.",
    ]
    for r in rules:
        story.append(Paragraph(f"• {r}", body_style))
    story.append(Spacer(1, 10))
    
    # --- SECTION 2: GREETING & MAIN MENU ---
    story.append(Paragraph("2. Initial Greeting & Main Menu", h1_style))
    story.append(Paragraph("This flow is triggered immediately when a user starts a conversation (with common greetings like 'Hi', 'Hello') or when a clean restart is needed.", body_style))
    
    story.append(make_trigger_tag(["hi", "hello", "start", "menu", "hey", "namskar", "good morning"]))
    story.append(Spacer(1, 5))
    
    greeting_text = (
        "Boom! 🎉 Welcome to Kaksha Kendra! (Rajat Sir's AI)\n"
        "Yahan Ratta Nahi, Logic Sikhaya Jata Hai! ✨\n\n"
        "Kaise padhna chahenge aap? 👇"
    )
    story.append(make_message_bubble(
        greeting_text,
        buttons=["Online Classes", "Offline Classes", "🔥 Bounce Back Batch", "⚡ Brahmastra Batch", "📋 Seminar Registration"],
        title="GREETING RESPONSE (MAIN MENU)"
    ))
    story.append(Spacer(1, 15))

    # --- SECTION 3: ONLINE CLASSES TRACK ---
    story.append(Paragraph("3. Online Classes Track (Interactive Flows)", h1_style))
    story.append(Paragraph("When the user selects the <b>'Online Classes'</b> button from the main menu, the bot prompts them to choose their academic class.", body_style))
    
    story.append(make_trigger_tag(["Online Classes"], "Transition to Online Class Selection"))
    story.append(Spacer(1, 5))
    
    online_class_prompt = (
        "Top Choice! 🚀 Live mentoring with Rajat Sir!\n"
        "Yahan Ratta Nahi, Logic Sikhaya Jata Hai! ✨\n\n"
        "Aapki class kaunsi hai? 👇"
    )
    story.append(make_message_bubble(
        online_class_prompt,
        buttons=["Class 6-8", "Class 9", "Class 10", "Class 11", "Class 12"],
        title="ONLINE CLASS PROMPT"
    ))
    story.append(PageBreak())

    # --- CLASS-SPECIFIC SUB-TRACKS ---
    story.append(Paragraph("3.1 Class-Specific Sub-Track Details", h2_style))
    story.append(Paragraph("Based on the class button clicked, the bot sends specific marketing text and displays the subjects available for that class.", body_style))

    # Class 6-8
    story.append(Paragraph("A. Class 6-8 Selection", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=8)))
    c68_text = (
        "🌱 Junior classes are not \"Small Steps\" — they are the base of \"Big Results\".\n"
        "\"Strong foundations built early decide how far a student can go later.\"\n\n"
        "Aage badhe? 👇"
    )
    story.append(make_message_bubble(c68_text, buttons=["Foundation Batch"], title="CLASS 6-8 RESPONSE"))
    story.append(Spacer(1, 10))

    # Class 9
    story.append(Paragraph("B. Class 9 Selection", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=8)))
    c9_text = (
        "🔥 Class 9 is Not a \"Rest Year\" — It's the \"Game Changer\"!\n"
        "80% of students struggle in Class 10 because they wasted Class 9. Don't be one of them.\n\n"
        "Ab subject choose karo 👇"
    )
    story.append(make_message_bubble(c9_text, buttons=["Maths", "Science", "Maths + Science"], title="CLASS 9 RESPONSE"))
    story.append(Spacer(1, 10))

    # Class 10
    story.append(Paragraph("C. Class 10 Selection", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=8)))
    c10_text = (
        "🏆 The Marksheet That Stays With You Forever. \"Make It Proud\".\n"
        "Don't gamble with your Board Exams. Get the structured guidance you need to cross 95%.\n\n"
        "Ab subject choose karo 👇"
    )
    story.append(make_message_bubble(c10_text, buttons=["Maths", "Science", "Maths + Science"], title="CLASS 10 RESPONSE"))
    story.append(Spacer(1, 10))

    # Class 11
    story.append(Paragraph("D. Class 11 Selection", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=8)))
    c11_text = (
        "🎯 Class 11 Maths is not a \"Chapter\" — It's the \"Turning Point\".\n"
        "Maths Ko \"Ratta\" Nahi, \"Feel\" Karo. Formulas bhool jaoge, par Logic hamesha yaad rahega.\n\n"
        "Ready? 👇"
    )
    story.append(make_message_bubble(c11_text, buttons=["Maths"], title="CLASS 11 RESPONSE"))
    story.append(Spacer(1, 10))

    # Class 12
    story.append(Paragraph("E. Class 12 Selection", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=8)))
    c12_text = (
        "🏆 The Marksheet That Stays With You Forever. \"Make It Proud\".\n"
        "Don't gamble with your Board Exams. Get the structured guidance you need to cross 95%.\n\n"
        "Ready? 👇"
    )
    story.append(make_message_bubble(c12_text, buttons=["Maths"], title="CLASS 12 RESPONSE"))
    
    story.append(PageBreak())

    # --- ONLINE COURSE DETAILS & CHECKOUT LINK TABLE ---
    story.append(Paragraph("3.2 Online Course Checkout & Link Database", h2_style))
    story.append(Paragraph("When a student taps a specific subject or batch button, they receive the final checkout response. It includes a value-proposition description and a direct purchase CTA button.", body_style))
    
    story.append(make_message_bubble(
        "Sahi Choice! 💎 Champions Edition Activated!\n\n"
        "✅ Lifetime Access — Pay once, master forever\n"
        "✅ VIP Doubt Access — Members only\n"
        "✅ Rajat Sir Personally — Signature drill\n\n"
        "Yahan Ratta Nahi, Logic Sikhaya Jata Hai! ✨\n\n"
        "📖 Details:\n"
        "[Matching Course Page Link]\n\n"
        "Champion banne ke liye 👇",
        buttons=["[CTA_URL display='🛒 Become a Champion' url='<EXACT_CHECKOUT_URL>']"],
        title="ONLINE COURSE DETAILS & CHECKOUT TEMPLATE"
    ))
    story.append(Spacer(1, 10))

    # Link Database Table
    story.append(Paragraph("<b>Table: Full Online Course Pricing and Links Database</b>", body_style))
    
    headers = [Paragraph("<b>Course Selection</b>", table_header_style), 
               Paragraph("<b>Price</b>", table_header_style), 
               Paragraph("<b>Details / Checkout URLs</b>", table_header_style)]
    
    table_data = [headers]
    
    online_links = [
        ("Class 6-8 Foundation", "₹599", "Details: https://www.kakshakendra.com/class-6-8\nBuy: https://courses.kakshakendra.com/single-checkout/698cb19698e0f96347b1af61?pid=p1"),
        ("Class 9 Maths", "₹599", "Details: https://www.kakshakendra.com/class-9\nBuy: https://courses.kakshakendra.com/single-checkout/69821a99300fd63465b6941e?pid=p1"),
        ("Class 9 Science", "₹599", "Details: https://www.kakshakendra.com/class-9\nBuy: https://courses.kakshakendra.com/single-checkout/69873883f74eae010cd63eaf?pid=p1"),
        ("Class 9 Combo (M+S)", "₹899", "Details: https://www.kakshakendra.com/class-9\nBuy: https://courses.kakshakendra.com/single-checkout/698caf12baa1280324f96fab?pid=p1"),
        ("Class 10 Maths", "₹699", "Details: https://www.kakshakendra.com/class-10\nBuy: https://courses.kakshakendra.com/single-checkout/6978af60ea78c4664e4b2e73?pid=p1"),
        ("Class 10 Science", "₹699", "Details: https://www.kakshakendra.com/class-10\nBuy: https://courses.kakshakendra.com/single-checkout/69871e7efa6ddb2e01594906?pid=p1"),
        ("Class 10 Combo (M+S)", "₹999", "Details: https://www.kakshakendra.com/class-10\nBuy: https://courses.kakshakendra.com/single-checkout/698cbe62d557060ac48beb7c?pid=p1"),
        ("Class 11 Maths", "₹599", "Details: https://www.kakshakendra.com/class-11\nBuy: https://courses.kakshakendra.com/single-checkout/6982e065d9425d529eefd106?pid=p1"),
        ("Class 12 Maths", "₹699", "Details: https://www.kakshakendra.com/class-12\nBuy: https://courses.kakshakendra.com/single-checkout/698332b3e2d1e273ee6a7270?pid=p1"),
    ]
    
    for course, price, url_info in online_links:
        table_data.append([
            Paragraph(course, table_cell_style),
            Paragraph(price, table_cell_style),
            Paragraph(url_info.replace('\n', '<br/>'), table_cell_style)
        ])
        
    t_links = Table(table_data, colWidths=[130, 50, 307])
    t_links.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(t_links)
    story.append(Spacer(1, 15))

    # --- SECTION 4: OFFLINE CLASSES TRACK ---
    story.append(Paragraph("4. Offline Classes Track (Interactive Flows)", h1_style))
    story.append(Paragraph("When the user selects the <b>'Offline Classes'</b> button from the main menu, the bot routes them through the offline center information flow.", body_style))
    
    story.append(make_trigger_tag(["Offline Classes"], "Transition to Offline Level Selection"))
    story.append(Spacer(1, 5))
    
    offline_level_prompt = (
        "Top Choice! 🏫 Direct Center pe milte hain!\n"
        "Yahan Ratta Nahi, Logic Sikhaya Jata Hai! ✨\n\n"
        "Aapke bachhe ki class? 👇"
    )
    story.append(make_message_bubble(
        offline_level_prompt,
        buttons=["Pre-Primary (Nur-UKG)", "Primary (1st-5th)", "Junior (6th-8th)", "Secondary (9th-10th)", "Sr. Secondary (11-12)"],
        title="OFFLINE LEVEL PROMPT"
    ))
    story.append(PageBreak())

    # --- OFFLINE LEVEL SUB-TRACKS ---
    story.append(Paragraph("4.1 Offline Level-Specific Sub-Track Details", h2_style))
    story.append(Paragraph("Each level provides customized marketing details about the teaching environment at the physical center in Kanth, UP, followed by action buttons.", body_style))

    # Pre-Primary
    story.append(Paragraph("A. Pre-Primary (Nur-UKG)", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=8)))
    pre_pri_text = (
        "🍎 \"Ab 'A for Apple' ratna nahi, Smart Class mein samajhna hai! ✨\"\n\n"
        "📍 Kanth, UP. Aage badhe? 👇"
    )
    story.append(make_message_bubble(pre_pri_text, buttons=["Register Now", "Call Us"], title="PRE-PRIMARY OFFLINE RESPONSE"))
    story.append(Spacer(1, 10))

    # Primary
    story.append(Paragraph("B. Primary (1st-5th)", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=8)))
    pri_text = (
        "🎒 \"Bhari school bags se nahi, ab 'Smart Concepts' se aage badhega aapka baccha! 💻\"\n\n"
        "📍 Kanth, UP. Next? 👇"
    )
    story.append(make_message_bubble(pri_text, buttons=["Register Now", "Call Us"], title="PRIMARY OFFLINE RESPONSE"))
    story.append(Spacer(1, 10))

    # Junior
    story.append(Paragraph("C. Junior (6th-8th)", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=8)))
    jun_text = (
        "🌱 Junior classes are not \"Small Steps\" — they are the base of \"Big Results\".\n"
        "\"Strong foundations built early decide how far a student can go later.\"\n\n"
        "📍 Kanth, UP. Aage? 👇"
    )
    story.append(make_message_bubble(jun_text, buttons=["Register Now", "Call Us"], title="JUNIOR OFFLINE RESPONSE"))
    story.append(Spacer(1, 10))

    # Secondary
    story.append(Paragraph("D. Secondary (9th-10th)", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=8)))
    sec_text = (
        "🏆 The Marksheet That Stays With You Forever. \"Make It Proud\".\n"
        "Don't gamble with your Board Exams. Get the structured guidance you need to cross 95%.\n\n"
        "(Class 9 mein ho? Yeh \"Game Changer\" year hai — 80% Class 10 strugglers ne 9th waste kiya tha.)\n\n"
        "📍 Kanth, UP. Ready? 👇"
    )
    story.append(make_message_bubble(sec_text, buttons=["Register Now", "Call Us"], title="SECONDARY OFFLINE RESPONSE"))
    story.append(Spacer(1, 10))

    # Sr. Secondary
    story.append(Paragraph("E. Sr. Secondary (11-12)", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=8)))
    sr_sec_text = (
        "🎯 Class 11 Maths is not a \"Chapter\" — It's the \"Turning Point\".\n"
        "Maths Ko \"Ratta\" Nahi, \"Feel\" Karo. Formulas bhool jaoge, par Logic hamesha yaad rahega.\n\n"
        "(Class 12 mein ho? The Marksheet That Stays With You Forever. \"Make It Proud\".)\n\n"
        "📍 Kanth, UP. Aage badhe? 👇"
    )
    story.append(make_message_bubble(sr_sec_text, buttons=["Register Now", "Call Us"], title="SR. SECONDARY OFFLINE RESPONSE"))
    story.append(PageBreak())

    # --- OFFLINE ACTION BUTTON RESPONSE FLOWS ---
    story.append(Paragraph("4.2 Offline Action Responses", h2_style))
    story.append(Paragraph("When the user selects either <b>'Register Now'</b> or <b>'Call Us'</b> inside any of the offline level menus, the bot triggers the following actions:", body_style))

    # Register Now Clicked
    story.append(Paragraph("If 'Register Now' is Clicked:", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=8)))
    reg_now_text = (
        "Top Decision! 🎉\n"
        "Form bharo, 24 ghante mein call!\n"
        "Yahan Ratta Nahi, Champions Banate Hain! ✨"
    )
    story.append(make_message_bubble(
        reg_now_text,
        buttons=["[CTA_URL display='🚀 Join Champions Circle' url='https://forms.gle/UXm5D6fZiZbhA9Tw5']"],
        title="OFFLINE REGISTRATION REDIRECT"
    ))
    story.append(Spacer(1, 10))

    # Call Us Clicked
    story.append(Paragraph("If 'Call Us' is Clicked:", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=8)))
    story.append(Paragraph("The system bypasses the normal message builder and sends a pre-approved Meta WhatsApp Template with a physical tap-to-call button. This keeps the lead interaction fast.", body_style))
    
    call_template_detail = (
        "Template Name: kaksha_call_us\n"
        "Language: English (en) / Hindi (hi)\n"
        "Meta Component: PHONE_NUMBER Call Button (+91 75798 52528)\n"
        "Response saved to database: [Sent template: kaksha_call_us]"
    )
    story.append(make_message_bubble(
        call_template_detail,
        buttons=["[CALL_US BUTTON (Dials +917579852528 directly)]"],
        title="META TAP-TO-CALL TEMPLATE FLOW"
    ))
    story.append(Spacer(1, 15))

    # --- SECTION 5: BOUNCE BACK BATCH FLOW ---
    story.append(Paragraph("5. Bounce Back Batch Flow", h1_style))
    story.append(Paragraph("Designed for CBSE Class 12 Maths RT (Re-Test/Compartment) students. Triggered via buttons or intent keywords. Triggers automatic drip sequences.", body_style))
    
    story.append(make_trigger_tag(
        ["bounce back", "rt exam", "fail ho gaya", "compartment", "supplementary", "pass hona hai", "rt batch"],
        "Substrings match anywhere in the message. Starts the drip task automatically."
    ))
    story.append(Spacer(1, 5))
    
    bb_info = (
        "🔥 BOUNCE BACK BATCH — CBSE Board 2026 RT Students\n\n"
        "\"Fail nahi hone dunga!\" — Rajat Sir\n\n"
        "Agar Maths mein RT aaya hai, toh ab ghabrane ki zaroorat nahi. Yeh batch sirf Maths RT students ke liye hai — yeh aapka sabse bada comeback hoga! 🎯\n\n"
        "✅ Zero se padhai, har concept clear hoga ✨\n"
        "✅ Sirf wahi padhenge jo RT exam mein aayega\n"
        "✅ Rajat Sir ki guarantee — 100% Pass!\n\n"
        "Aaj hi enroll karo! 👇"
    )
    story.append(make_message_bubble(
        bb_info,
        buttons=["[CTA_URL display='🚀 Enroll Now' url='https://www.kakshakendra.com/bounceback--12']"],
        title="BOUNCE BACK BATCH RESPONSE"
    ))
    story.append(PageBreak())

    # Drip Sequence
    story.append(Paragraph("5.1 Bounce Back Drip Campaign Timeline", h2_style))
    story.append(Paragraph("Once a student triggers the Bounce Back flow, the bot schedules background follow-up tasks to maximize conversion. The flow pauses if they mark themselves as purchased.", body_style))
    
    drip_timeline = [
        ("T + 5 Minutes\n(Promo Video)", "🔥 Sirf padhai nahi, strategy bhi zaroori hai!\nDekho Rajat Sir ne kaise pichle saal ke RT students ka result badal diya. 👇\n[Video File attachment containing student testimonials]"),
        ("T + 24 Hours\n(Check-in & Options)", "Hi! 👋 Kal aapne Bounce Back Batch ke baare mein pucha tha. Kya aapne enroll kar liya?\n[Buttons: ✅ Yes, I purchased! / ❌ Not Yet]"),
        ("T + 48 Hours\n(Final Reminder)", "⚠️ Final Reminder for Bounce Back Batch!\nClasses bohot tezi se aage badh rahi hain. Agar abhi miss kiya, toh cover karna mushkil ho jayega! Enroll now to save your year!")
    ]
    
    for time_label, msg_content in drip_timeline:
        story.append(Paragraph(f"⏱️ <b>{time_label}</b>", ParagraphStyle('DripLabel', parent=body_bold, spaceBefore=8)))
        if "Yes, I purchased" in msg_content:
            story.append(make_message_bubble(msg_content, buttons=["✅ Yes, I purchased!", "❌ Not Yet"], title="DRIP CHECK-IN MESSAGE"))
        else:
            story.append(make_message_bubble(msg_content, title="DRIP CAMPAIGN MESSAGE"))
        story.append(Spacer(1, 5))

    story.append(Paragraph("5.2 Drip Response Intercepts", h2_style))
    story.append(Paragraph("When the student clicks the buttons in the 24-Hour Drip Check-in message, the bot intercepts their answers directly:", body_style))
    
    # Intercept YES
    story.append(Paragraph("Response to '✅ Yes, I purchased!':", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=6)))
    yes_text = (
        "🎉 *Congratulations! Welcome to Bounce Back Batch!*\n\n"
        "Rajat Sir ka promise hai — *Fail nahi hone dunga!* 💪\n\n"
        "Course access ke liye apna registered email check karo.\n"
        "Koi bhi problem ho toh hume WhatsApp karo! 😊"
    )
    story.append(make_message_bubble(yes_text, title="PURCHASE CONFIRMED RESPONSE"))
    story.append(Spacer(1, 5))

    # Intercept NO
    story.append(Paragraph("Response to '❌ Not Yet':", ParagraphStyle('SubSub', parent=body_bold, spaceBefore=6)))
    no_text = (
        "No worries! 😊 Hum samjhte hain.\n\n"
        "Yaad rakhna — *RTCLASS12* promo code use karke sirf *₹1499/-* mein enroll kar sakte ho! 🎟️\n\n"
        "Hum thodi der baad aapko remind kar denge. 🔔"
    )
    story.append(make_message_bubble(no_text, title="DISCOUNT REMINDER RESPONSE"))
    
    story.append(PageBreak())

    # --- SECTION 6: BRAHMASTRA BATCH FLOW ---
    story.append(Paragraph("6. Brahmastra Batch Flow", h1_style))
    story.append(Paragraph("Designed for students wanting to fix weak foundations, improve calculation speed, and learn elimination tricks. Triggered via buttons or intent keywords.", body_style))
    
    story.append(make_trigger_tag(
        ["brahmastra", "brahmstra", "calculation speed", "basics weak", "foundation fix", "academic comeback"],
        "Substrings match anywhere in the user message."
    ))
    story.append(Spacer(1, 5))
    
    bm_info = (
        "⚡ BRAHMASTRA: THE ACADEMIC COMEBACK\n\n"
        "\"Master the Core. Dominate the Score!\"\n"
        "\"Calculation ki speed badhao, Basics mazboot karo!\"\n\n"
        "This batch is specifically designed for students who want to fix their foundation from the roots and permanently eliminate the fear of Math and Science numericals. 🧠\n\n"
        "✅ Smart Weightage & fast option-elimination tricks\n"
        "✅ Basics rebuilt from Level 0 to Level 3\n"
        "✅ Rajat Sir's proven 'Oral to Written Drill' method\n\n"
        "Start your Academic Comeback today 👇"
    )
    story.append(make_message_bubble(
        bm_info,
        buttons=["[CTA_URL display='🚀 Enroll Now' url='https://courses.kakshakendra.com/courses/BRAHMASTRA-THE-ACADEMIC-COMEBACK-6a0b52bd4dd0758ae8c1691d']"],
        title="BRAHMASTRA BATCH RESPONSE"
    ))
    story.append(Spacer(1, 15))

    # --- SECTION 7: SEMINAR REGISTRATION FLOW ---
    story.append(Paragraph("7. Seminar Registration Step-by-Step Flow", h1_style))
    story.append(Paragraph("The bot provides an automated step-by-step interactive form to collect registration details from students. Once complete, data is synced to Google Sheets and an alert is broadcast to the admin.", body_style))
    
    story.append(make_trigger_tag(
        ["seminar registration", "reserve my spot", "free seminar", "seminar registration button", "📋 seminar registration"],
        "Starts a session-state tracking flow. Normal AI response is suspended until step 6 is completed."
    ))
    story.append(Spacer(1, 5))

    # Steps
    steps = [
        ("Step 1/6: Welcome & Name", "🎓 *Seminar Registration — Kaksha Kendra*\n\nRajat Sir ke upcoming seminar ke liye aapka swagat hai! 🙏\n\nHamare team member aapko seminar ki poori details ke saath *call karenge*.\n\nPehle, aapki thodi si details chahiye — yeh sirf *2 minute* ka kaam hai! ✨\n\n━━━━━━━━━━━━━━━━━━━━\n👤 *Step 1/6 — Aapka poora naam kya hai?*"),
        ("Step 2/6: Class", "✅ Shukriya, *[User Name]*!\n\n━━━━━━━━━━━━━━━━━━━━\n📚 *Step 2/6 — Aap kis class mein hain?*\n_(e.g. Class 9, Class 10, Class 12)_"),
        ("Step 3/6: Father's Name", "✅ Note kar liya!\n\n━━━━━━━━━━━━━━━━━━━━\n👨 *Step 3/6 — Aapke pita ji ka naam?*"),
        ("Step 4/6: Contact Number", "✅ Perfect!\n\n━━━━━━━━━━━━━━━━━━━━\n📱 *Step 4/6 — Aapka mobile number?*\n_(Jis number par call chahiye)_"),
        ("Step 5/6: Alternate Number", "✅ Saved!\n\n━━━━━━━━━━━━━━━━━━━━\n📞 *Step 5/6 — Ek alternate mobile number dijiye*\n_(Koi bhi family member ka — in case aap unavailable hon)_"),
        ("Step 6/6: Home Address", "✅ Got it!\n\n━━━━━━━━━━━━━━━━━━━━\n🏠 *Step 6/6 — Aapka address?*\n_(Gaon/Mohalla, City, PIN code)_"),
    ]
    
    for step_title, step_text in steps:
        story.append(Paragraph(f"📝 <b>{step_title}</b>", ParagraphStyle('StepLabel', parent=body_bold, spaceBefore=6)))
        story.append(make_message_bubble(step_text, title="SEMINAR FORM INPUT"))
        story.append(Spacer(1, 5))
        
    story.append(PageBreak())

    # Completion Confirmation
    story.append(Paragraph("7.1 Seminar Registration Complete Confirmation", h2_style))
    story.append(Paragraph("Upon submitting the address, the bot finishes the sequence, pushes data to Google Sheets via the Apps Script Webhook, sends an admin notification, and displays:", body_style))
    
    conf_msg = (
        "🎉 *Registration Complete! Shukriya!*\n\n"
        "Aapki details successfully save ho gayi hain:\n\n"
        "👤 Naam: *[Name]*\n"
        "📚 Class: *[Class]*\n"
        "👨 Pita ji: *[Father's Name]*\n"
        "📱 Mobile: *[Mobile]*\n"
        "📞 Alt Mobile: *[Alt Mobile]*\n"
        "🏠 Address: *[Address]*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Hamare team member aapko *seminar ki poori details ke saath jald call karenge!*\n\n"
        "Koi sawaal ho toh hume WhatsApp karo. 😊\n"
        "*Kaksha Kendra — Yahan Ratta Nahi, Logic Sikhaya Jata Hai! ✨*"
    )
    story.append(make_message_bubble(conf_msg, title="SEMINAR REGISTRATION SUCCESS CONFIRMATION"))
    story.append(Spacer(1, 10))

    # Admin Alert Message
    story.append(Paragraph("<b>WhatsApp Notification Broadcast to Admin:</b>", body_style))
    admin_msg = (
        "📋 *NEW SEMINAR REGISTRATION!*\n\n"
        "👤 Naam: [Name]\n"
        "📚 Class: [Class]\n"
        "👨 Pita ji: [Father's Name]\n"
        "📱 Mobile: [Mobile]\n"
        "📞 Alt Mobile: [Alt Mobile]\n"
        "🏠 Address: [Address]\n"
        "💬 WhatsApp: +[Sender ID]\n\n"
        "📞 *Please call to confirm seminar details!*"
    )
    story.append(make_message_bubble(admin_msg, title="ADMIN NOTIFICATION LAYOUT"))
    story.append(Spacer(1, 15))

    # --- SECTION 8: SPECIAL HANDLERS & FALLBACKS ---
    story.append(Paragraph("8. Special Handlers & Deflections", h1_style))
    story.append(Paragraph("The bot has specialized regex and keyword match intercepts to divert specific queries from standard LLM response generation. This reduces server costs and ensures consistent compliance.", body_style))
    
    # On-screen copy
    story.append(Paragraph("8.1 Copy Checking & Re-Evaluation Issue", h2_style))
    story.append(make_trigger_tag(
        ["on screen copy", "re-evaluation", "answer sheet", "marks issue", "result problem", "recheck", "copy dikhao"],
        "Routes students concerned with copy checking or marks directly to Rajat Sir's email."
    ))
    story.append(Spacer(1, 5))
    copy_checking_reply = (
        "📋 *On-Screen Copy / Answer Sheet Issue?*\n\n"
        "Please send your answer copy or details of your concern directly to Rajat Sir:\n\n"
        "📧 *rajatsir@kakshakendra.com*\n\n"
        "Rajat Sir will personally review it and get back to you. 🙏"
    )
    story.append(make_message_bubble(copy_checking_reply, title="COPY CHECK DIRECTIVES"))
    story.append(Spacer(1, 10))

    # Academic doubt deflection
    story.append(Paragraph("8.2 Academic Doubts Deflection (VIP Member Feature)", h2_style))
    story.append(Paragraph("If the AI model detects a homework help request, formula query, or direct physics/chemistry/math solving query, it replies with the VIP Members upgrade prompt:", body_style))
    doubt_text = (
        "Doubts? 💎 Yeh VIP Feature Hai!\n"
        "Sirf Members ke liye — Rajat Sir Personally Solve!\n"
        "Yahan Ratta Nahi, Logic Sikhaya Jata Hai! ✨\n\n"
        "Aapki class? 👇"
    )
    story.append(make_message_bubble(doubt_text, buttons=["Class 6-8", "Class 9", "Class 10", "Class 11", "Class 12"], title="ACADEMIC DOUBT BLOCK RESPONSE"))
    
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Detailed PDF built successfully and saved to: {pdf_path}")

if __name__ == '__main__':
    build_pdf()
