#!/usr/bin/env python3
"""
app/utils/offer_pdf.py
Generates bundled multi-page PDF for Reference and Neighbor letters.
Each page = one letter. Standard US Letter 8.5x11.
"""

import os
import random
import string
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from io import BytesIO


NAVY = colors.HexColor('#1E293B')
GREEN = colors.HexColor('#00C851')


def generate_offer_code(prefix='REF'):
    """Generate unique 8-char alphanumeric offer code."""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=8))
    return f"{prefix}-{code}"


def expiry_date(days=30):
    return (datetime.utcnow() + timedelta(days=days)).strftime('%B %d, %Y')


def _base_styles():
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle(
        'Header',
        fontSize=18,
        textColor=NAVY,
        fontName='Helvetica-Bold',
        spaceAfter=4,
    )
    subheader_style = ParagraphStyle(
        'SubHeader',
        fontSize=11,
        textColor=GREEN,
        fontName='Helvetica-Bold',
        spaceAfter=16,
    )
    body_style = ParagraphStyle(
        'Body',
        fontSize=11,
        textColor=colors.HexColor('#1E293B'),
        fontName='Helvetica',
        leading=18,
        spaceAfter=12,
    )
    footer_style = ParagraphStyle(
        'Footer',
        fontSize=10,
        textColor=colors.HexColor('#64748B'),
        fontName='Helvetica',
        leading=14,
        spaceAfter=6,
    )
    offer_style = ParagraphStyle(
        'Offer',
        fontSize=11,
        textColor=NAVY,
        fontName='Helvetica-Bold',
        leading=16,
        spaceAfter=6,
    )
    return header_style, subheader_style, body_style, footer_style, offer_style


def generate_reference_pdf(letters):
    """
    Generate a bundled multi-page reference letter PDF.

    letters: list of dicts with keys:
        reference_name, reference_first_name, reference_address,
        customer_name, rep_name, dealership_name,
        rep_phone, rep_slug
    
    Returns: (pdf_bytes, list of offer_code strings)
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )

    header_style, subheader_style, body_style, footer_style, offer_style = _base_styles()
    story = []
    offer_codes = []

    for i, l in enumerate(letters):
        code = generate_offer_code('REF')
        offer_codes.append(code)
        expires = expiry_date(30)

        if i > 0:
            from reportlab.platypus import PageBreak
            story.append(PageBreak())

        # Header
        story.append(Paragraph(l['dealership_name'], header_style))
        story.append(Paragraph('Personal Reference Letter', subheader_style))
        story.append(Spacer(1, 0.1 * inch))

        # Salutation
        story.append(Paragraph(f"Dear {l['reference_first_name']},", body_style))

        # Body
        story.append(Paragraph(
            f"Your friend <b>{l['customer_name']}</b> recently purchased a vehicle from "
            f"<b>{l['rep_name']}</b> at <b>{l['dealership_name']}</b> and listed you as "
            f"a personal reference.",
            body_style
        ))

        story.append(Paragraph(
            "As a thank-you for being part of their circle, we'd like to offer you "
            "<b>$500 in promotional marketing savings</b> toward the purchase of any "
            "vehicle in our inventory.",
            body_style
        ))

        story.append(Paragraph(
            f"This offer is valid for 30 days and must be presented to <b>{l['rep_name']}</b> "
            f"directly at time of purchase to be redeemed.",
            body_style
        ))

        story.append(Paragraph(
            f"If you'd like to browse our inventory or set up a time to visit, "
            f"<b>{l['rep_name']}</b> is your direct contact:",
            body_style
        ))

        story.append(Paragraph(f"📞 {l['rep_phone']}", offer_style))
        story.append(Paragraph(f"🌐 cardeals.autos/{l['rep_slug']}", offer_style))
        story.append(Spacer(1, 0.2 * inch))

        story.append(Paragraph(f"Thank you,", body_style))
        story.append(Paragraph(f"<b>{l['rep_name']}</b>", body_style))
        story.append(Paragraph(l['dealership_name'], body_style))
        story.append(Spacer(1, 0.3 * inch))

        # Offer code block
        story.append(Paragraph(f"Offer code: <b>{code}</b>", offer_style))
        story.append(Paragraph(f"Expires: {expires}", footer_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes, offer_codes


def generate_neighbor_pdf(letters):
    """
    Generate a bundled multi-page neighbor letter PDF.

    letters: list of dicts with keys:
        neighbor_address, rep_name, dealership_name,
        rep_phone, rep_slug
    
    Returns: (pdf_bytes, list of offer_code strings)
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )

    header_style, subheader_style, body_style, footer_style, offer_style = _base_styles()
    story = []
    offer_codes = []

    for i, l in enumerate(letters):
        code = generate_offer_code('NBR')
        offer_codes.append(code)
        expires = expiry_date(30)

        if i > 0:
            from reportlab.platypus import PageBreak
            story.append(PageBreak())

        # Header
        story.append(Paragraph(l['dealership_name'], header_style))
        story.append(Paragraph('A Note From Your Neighbor\'s Dealership', subheader_style))
        story.append(Spacer(1, 0.1 * inch))

        # Salutation
        story.append(Paragraph("Dear Neighbor,", body_style))

        # Body
        story.append(Paragraph(
            "We just wanted to reach out and say congratulations to one of your neighbors "
            "on their recent car purchase from us.",
            body_style
        ))

        story.append(Paragraph(
            "If you've been thinking about upgrading your vehicle, now is a great time to "
            "take a look. We'd love the chance to help you find something that fits your "
            "needs and budget.",
            body_style
        ))

        story.append(Paragraph(
            "As a special thank-you for being part of the neighborhood, we're offering you "
            "<b>$500 in promotional marketing savings</b> toward your next vehicle purchase.",
            body_style
        ))

        story.append(Paragraph(
            f"This offer is valid for 30 days and must be presented to <b>{l['rep_name']}</b> "
            f"directly at time of purchase to be redeemed.",
            body_style
        ))

        story.append(Paragraph(
            "If you'd like to browse our inventory or set up a time to stop by, "
            "we'd be happy to help:",
            body_style
        ))

        story.append(Paragraph(f"📞 {l['rep_phone']}", offer_style))
        story.append(Paragraph(f"🌐 cardeals.autos/{l['rep_slug']}", offer_style))
        story.append(Spacer(1, 0.2 * inch))

        story.append(Paragraph("Sincerely,", body_style))
        story.append(Paragraph(f"<b>{l['rep_name']}</b>", body_style))
        story.append(Paragraph(l['dealership_name'], body_style))
        story.append(Spacer(1, 0.3 * inch))

        # Offer code block
        story.append(Paragraph(f"Offer code: <b>{code}</b>", offer_style))
        story.append(Paragraph(f"Expires: {expires}", footer_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes, offer_codes
