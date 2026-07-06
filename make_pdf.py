import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT

def create_pdf():
    desktop = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop') 
    pdf_path = os.path.join(desktop, 'Kaksha_Kendra_Message_Flows.pdf')

    doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    
    title_style = styles['Heading1']
    title_style.textColor = 'blue'
    heading_style = styles['Heading2']
    heading_style.textColor = 'darkred'
    heading_style.spaceBefore = 15
    heading_style.spaceAfter = 5
    sub_heading = styles['Heading3']
    normal = styles['Normal']
    normal.fontSize = 10
    normal.spaceAfter = 10
    
    code_style = ParagraphStyle(
        name='CodeStyle', parent=styles['Normal'], fontName='Courier', fontSize=9,
        leftIndent=20, backColor='#f0f0f0', spaceBefore=5, spaceAfter=15, borderPadding=10
    )
    
    trigger_style = ParagraphStyle(
        name='TriggerStyle', parent=styles['Normal'], textColor='green', fontName='Helvetica-Bold', spaceAfter=5
    )

    story = []
    
    story.append(Paragraph('Kaksha Kendra Bot - Message Flow Map', title_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph('This document details all automatic replies and message flows handled by the bot.', normal))
    
    story.append(Paragraph('1. Bounce Back Batch Flow', heading_style))
    story.append(Paragraph('Triggers: bounce back, rt exam, fail ho gaya, compartment, pass hona hai', trigger_style))
    bb_text = '''🔥 BOUNCE BACK BATCH - CBSE Board 2026 RT Students<br/><br/>
"Fail nahi hone dunga!" - Rajat Sir<br/><br/>
Agar Maths mein RT aaya hai, toh ab ghabrane ki zaroorat nahi...<br/>
✅ Zero se padhai, har concept clear hoga<br/>
✅ Rajat Sir ki guarantee - 100% Pass!<br/>
Aaj hi enroll karo! 👇<br/>
[CTA_URL display="🚀 Enroll Now" url="https://..."]'''
    story.append(Paragraph(bb_text, code_style))

    story.append(Paragraph('2. Brahmastra Batch Flow', heading_style))
    story.append(Paragraph('Triggers: brahmastra, calculation speed, basics weak, foundation fix', trigger_style))
    bm_text = '''⚡ BRAHMASTRA: THE ACADEMIC COMEBACK<br/><br/>
"Master the Core. Dominate the Score!"<br/><br/>
This batch is specifically designed for students who want to fix their foundation...<br/>
✅ Smart Weightage & fast option-elimination tricks<br/>
✅ Basics rebuilt from Level 0 to Level 3<br/>
Start your Academic Comeback today 👇'''
    story.append(Paragraph(bm_text, code_style))

    story.append(Paragraph('3. Seminar Registration Flow', heading_style))
    story.append(Paragraph('Triggers: seminar registration, reserve my spot, free seminar', trigger_style))
    sem_text = '''🎓 *Seminar Registration - Kaksha Kendra*<br/><br/>
Rajat Sir ke upcoming seminar ke liye aapka swagat hai!<br/>
Pehle, aapki thodi si details chahiye - yeh sirf *2 minute* ka kaam hai!<br/>
━━━━━━━━━━━━━━━━━━━━<br/>
👤 *Step 1/6 - Aapka poora naam kya hai?*'''
    story.append(Paragraph(sem_text, code_style))
    story.append(Paragraph('<i>(The bot then asks for Class, Father''s Name, Mobile, Alt Mobile, and Address one-by-one. It then sends the confirmation below)</i>', normal))
    sem_end = '''🎉 *Registration Complete! Shukriya!*<br/><br/>
Aapki details successfully save ho gayi hain:<br/>
👤 Naam: *[Name]*<br/>
📚 Class: *[Class]*<br/>
🏠 Address: *[Address]*<br/>
━━━━━━━━━━━━━━━━━━━━<br/>
✅ Hamare team member aapko *seminar ki poori details ke saath jald call karenge!*'''
    story.append(Paragraph(sem_end, code_style))
    
    story.append(Paragraph('4. Copy Checking / Answer Sheet Issues', heading_style))
    story.append(Paragraph('Triggers: on screen copy, re-evaluation, marks issue, copy check', trigger_style))
    copy_text = '''📋 *On-Screen Copy / Answer Sheet Issue?*<br/><br/>
Please send your answer copy or details of your concern directly to Rajat Sir:<br/>
📧 *rajatsir@kakshakendra.com*'''
    story.append(Paragraph(copy_text, code_style))
    
    story.append(Paragraph('5. Call Us / Team Handover', heading_style))
    story.append(Paragraph('Triggers: call us, call now, call', trigger_style))
    story.append(Paragraph('Template: kaksha_call_us (Sends the official Meta-approved Template Message with a call button)', code_style))
    
    story.append(Paragraph('6. Bounce Back Drip Campaign', heading_style))
    story.append(Paragraph('Intercepts:', sub_heading))
    story.append(Paragraph('If student replies ''Yes, I purchased'':', trigger_style))
    story.append(Paragraph('🎉 *Congratulations! Welcome to Bounce Back Batch!*<br/>Course access ke liye apna registered email check karo.', code_style))
    
    story.append(Paragraph('If student replies ''Not yet'':', trigger_style))
    story.append(Paragraph('No worries! 😊 Hum samjhte hain.<br/>Yaad rakhna - *RTCLASS12* promo code use karke sirf *₹1499/-* mein enroll kar sakte ho!', code_style))
    
    story.append(Paragraph('Drip Messages:', sub_heading))
    story.append(Paragraph('+5 Minutes (Promo Video):', trigger_style))
    story.append(Paragraph('🔥 *Sirf padhai nahi, strategy bhi zaroori hai!*<br/>Dekho Rajat Sir ne kaise pichle saal ke RT students ka result badal diya. 👇<br/>[Video File attached]', code_style))
    
    story.append(Paragraph('+24 Hours (Check-in):', trigger_style))
    story.append(Paragraph('Hi! 👋 Kal aapne Bounce Back Batch ke baare mein pucha tha.<br/>Kya aapne enroll kar liya?<br/>[Yes Button] [Not Yet Button]', code_style))
    
    story.append(Paragraph('+48 Hours (Final Reminder):', trigger_style))
    story.append(Paragraph('⚠️ *Final Reminder for Bounce Back Batch!*<br/>Classes bohot tezi se aage badh rahi hain. Agar abhi miss kiya, toh cover karna mushkil ho jayega!', code_style))

    story.append(Paragraph('7. Offline / Online / General Leads', heading_style))
    story.append(Paragraph('Triggers: Fallback AI detects general inquiries', trigger_style))
    story.append(Paragraph('If the bot detects the user is asking a general question, the AI handles the reply. The lead is sent to the Dashboard "Pending Calls" list. The team can then manually record them as "Offline" or "Online" via the "Add Lead" button.', normal))

    doc.build(story)
    print(f'PDF saved successfully to: {pdf_path}')

create_pdf()
