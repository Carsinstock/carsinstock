#!/usr/bin/env python3
import os, random, string
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from io import BytesIO

NAVY = colors.HexColor('#1E293B')
GREEN = colors.HexColor('#00C851')
GRAY = colors.HexColor('#64748B')

def generate_offer_code(prefix='REF'):
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-{''.join(random.choices(chars, k=8))}"

def expiry_date(days=30):
    return (datetime.now() + timedelta(days=days)).strftime('%B %d, %Y')

def _build_letter(story, heading, subheading, salutation, body_paragraphs, rep_name, rep_title, dealership_name, rep_phone, offer_code, expires, first=True):
    if not first:
        story.append(PageBreak())

    # Header
    story.append(Paragraph(dealership_name.upper(), ParagraphStyle('DName', fontSize=16, fontName='Helvetica-Bold', textColor=NAVY, spaceAfter=8)))
    story.append(Paragraph(subheading, ParagraphStyle('DAddr', fontSize=9, fontName='Helvetica', textColor=GRAY, spaceAfter=16)))
    story.append(HRFlowable(width='100%', thickness=1, color=GREEN, spaceAfter=20))

    # Date
    story.append(Paragraph(datetime.now().strftime('%B %d, %Y'), ParagraphStyle('Date', fontSize=10, fontName='Helvetica', textColor=GRAY, spaceAfter=20)))

    # Salutation
    story.append(Paragraph(salutation, ParagraphStyle('Sal', fontSize=11, fontName='Helvetica', textColor=NAVY, spaceAfter=16, leading=18)))

    # Body
    body_style = ParagraphStyle('Body', fontSize=11, fontName='Helvetica', textColor=NAVY, leading=18, spaceAfter=14)
    for para in body_paragraphs:
        story.append(Paragraph(para, body_style))

    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph('Sincerely,', body_style))
    story.append(Spacer(1, 0.4*inch))
    story.append(Paragraph(f'<b>{rep_name}</b>', ParagraphStyle('Sig', fontSize=11, fontName='Helvetica-Bold', textColor=NAVY, spaceAfter=2)))
    story.append(Paragraph(rep_title, ParagraphStyle('SigTitle', fontSize=10, fontName='Helvetica', textColor=GRAY, spaceAfter=2)))
    story.append(Paragraph(dealership_name, ParagraphStyle('SigDeal', fontSize=10, fontName='Helvetica', textColor=NAVY, spaceAfter=2)))
    story.append(Paragraph(rep_phone, ParagraphStyle('SigPhone', fontSize=10, fontName='Helvetica', textColor=NAVY, spaceAfter=0)))

    story.append(Spacer(1, 0.4*inch))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#E2E8F0'), spaceAfter=10))
    story.append(Paragraph(f'Offer code: <b>{offer_code}</b> &nbsp;·&nbsp; Expires: {expires}', ParagraphStyle('Footer', fontSize=9, fontName='Helvetica', textColor=GRAY, alignment=TA_CENTER)))

def generate_reference_pdf(letters):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=1.2*inch, leftMargin=1.2*inch, topMargin=1*inch, bottomMargin=1*inch)
    story = []
    offer_codes = []

    for i, l in enumerate(letters):
        code = generate_offer_code('REF')
        offer_codes.append(code)
        expires = expiry_date(30)
        first_name = l.get('reference_first_name', 'Friend')
        rep_name = l.get('rep_name', '')
        rep_first = rep_name.split()[0] if rep_name else 'me'

        body = [
            f"Your friend <b>{l['customer_name']}</b> recently purchased a vehicle from us and was kind enough to list you as a personal reference.",
            f"As a thank-you for being part of their circle, we'd like to extend to you <b>$500 in promotional marketing savings</b> toward the purchase of any vehicle in our inventory.",
            f"This offer is valid for 30 days and must be presented to <b>{rep_name}</b> directly at the time of purchase to be redeemed.",
            f"We'd love the opportunity to help you find the right vehicle at the right price. Stop in and ask for {rep_first} — or give me a call anytime.",
        ]

        _build_letter(
            story=story,
            heading=l['dealership_name'].upper(),
            subheading=l.get('dealership_address', ''),
            salutation=f"Dear {first_name},",
            body_paragraphs=body,
            rep_name=rep_name,
            rep_title='Sales Professional',
            dealership_name=l['dealership_name'],
            rep_phone=l.get('rep_phone', ''),
            offer_code=code,
            expires=expires,
            first=(i == 0)
        )

    doc.build(story)
    return buffer.getvalue(), offer_codes

def generate_neighbor_pdf(letters):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=1.2*inch, leftMargin=1.2*inch, topMargin=1*inch, bottomMargin=1*inch)
    story = []
    offer_codes = []

    for i, l in enumerate(letters):
        code = generate_offer_code('NBR')
        offer_codes.append(code)
        expires = expiry_date(30)
        rep_name = l.get('rep_name', '')
        rep_first = rep_name.split()[0] if rep_name else 'me'

        body = [
            "We just wanted to reach out and say congratulations to one of your neighbors on their recent car purchase from us.",
            "If you've been thinking about upgrading your vehicle, now is a great time to take a look. We'd love the chance to help you find something that fits your needs and budget.",
            f"As a special thank-you for being part of the neighborhood, we're offering you <b>$500 in promotional marketing savings</b> toward your next vehicle purchase.",
            f"This offer is valid for 30 days and must be presented to <b>{rep_name}</b> directly at the time of purchase to be redeemed.",
            f"We'd love the opportunity to help you find the right vehicle at the right price. Stop in and ask for {rep_first} — or give me a call anytime.",
        ]

        _build_letter(
            story=story,
            heading=l['dealership_name'].upper(),
            subheading="A Note From Your Neighbor's Dealership",
            salutation='Dear Neighbor,',
            body_paragraphs=body,
            rep_name=rep_name,
            rep_title='Sales Professional',
            dealership_name=l['dealership_name'],
            rep_phone=l.get('rep_phone', ''),
            offer_code=code,
            expires=expires,
            first=(i == 0)
        )

    doc.build(story)
    return buffer.getvalue(), offer_codes
