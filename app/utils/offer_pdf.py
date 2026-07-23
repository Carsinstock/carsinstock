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
from reportlab.pdfgen import canvas

from zoneinfo import ZoneInfo
# Customer-facing dates only.  The SERVER stays UTC -- crons are
# scheduled against it and must not move.  Without this, a letter
# generated after 8 PM ET prints tomorrow's date and the 30-day
# expiry counts from tomorrow.
ET = ZoneInfo('America/New_York')

NAVY = colors.HexColor('#1E293B')
GREEN = colors.HexColor('#00C851')
GRAY = colors.HexColor('#64748B')

def generate_offer_code(prefix='REF'):
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-{''.join(random.choices(chars, k=8))}"

def expiry_date(days=30):
    return (datetime.now(ET) + timedelta(days=days)).strftime('%B %d, %Y')

def _build_letter(story, heading, subheading, salutation, body_paragraphs, rep_name, rep_title, dealership_name, rep_phone, offer_code, expires, first=True, rep_slug=''):
    if not first:
        story.append(PageBreak())

    # Header
    story.append(Paragraph(dealership_name.upper(), ParagraphStyle('DName', fontSize=16, fontName='Helvetica-Bold', textColor=NAVY, spaceAfter=8)))
    story.append(Paragraph(subheading, ParagraphStyle('DAddr', fontSize=9, fontName='Helvetica', textColor=GRAY, spaceAfter=16)))
    story.append(HRFlowable(width='100%', thickness=1, color=GREEN, spaceAfter=20))

    # Date
    story.append(Paragraph(datetime.now(ET).strftime('%B %d, %Y'), ParagraphStyle('Date', fontSize=10, fontName='Helvetica', textColor=GRAY, spaceAfter=20)))

    # Salutation
    story.append(Paragraph(salutation, ParagraphStyle('Sal', fontSize=11, fontName='Helvetica', textColor=NAVY, spaceAfter=16, leading=18)))

    # Body
    body_style = ParagraphStyle('Body', fontSize=11, fontName='Helvetica', textColor=NAVY, leading=18, spaceAfter=14)
    for para in body_paragraphs:
        story.append(Paragraph(para, body_style))

    story.append(Spacer(1, 0.18*inch))
    story.append(Paragraph('Sincerely,', body_style))
    story.append(Spacer(1, 0.22*inch))
    sig_col = [
        Paragraph(f'<b>{rep_name}</b>', ParagraphStyle('Sig', fontSize=11, fontName='Helvetica-Bold', textColor=NAVY, spaceAfter=2)),
        Paragraph(rep_title, ParagraphStyle('SigTitle', fontSize=10, fontName='Helvetica', textColor=GRAY, spaceAfter=2)),
        Paragraph(dealership_name, ParagraphStyle('SigDeal', fontSize=10, fontName='Helvetica', textColor=NAVY, spaceAfter=2)),
        Paragraph(rep_phone, ParagraphStyle('SigPhone', fontSize=10, fontName='Helvetica', textColor=NAVY, spaceAfter=0)),
    ]
    qr_col = ''
    if rep_slug:
        import qrcode as _qrlib
        from reportlab.platypus import Image as _RLImage
        _qr = _qrlib.QRCode(version=1, box_size=8, border=2, error_correction=_qrlib.constants.ERROR_CORRECT_M)
        _qr.add_data(f'https://cardeals.autos/{rep_slug}?ref=qr'); _qr.make(fit=True)
        _qr_img = _qr.make_image(fill_color='#1E293B', back_color='white')
        _qr_buf = BytesIO(); _qr_img.save(_qr_buf, format='PNG'); _qr_buf.seek(0)
        _qr_flow = _RLImage(_qr_buf, width=2.4*inch, height=2.4*inch); _qr_flow.hAlign='CENTER'
        qr_col = [
            Paragraph('<b>Scan to See My Inventory</b>', ParagraphStyle('QRCap', fontSize=10, fontName='Helvetica-Bold', textColor=NAVY, alignment=1, spaceAfter=6)),
            _qr_flow,
            Paragraph(f'cardeals.autos/{rep_slug}', ParagraphStyle('QRUrl', fontSize=8, fontName='Helvetica', textColor=GRAY, alignment=1, spaceBefore=4, spaceAfter=0)),
        ]
    from reportlab.platypus import Table, TableStyle
    _t = Table([[sig_col, qr_col]], colWidths=[3.1*inch, 2.5*inch])
    _t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0),('ALIGN',(1,0),(1,0),'RIGHT')]))
    story.append(_t)
    story.append(Spacer(1, 0.15*inch))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#E2E8F0'), spaceAfter=10))
    story.append(Paragraph(f'Offer code: <b>{offer_code}</b> &nbsp;·&nbsp; Expires: {expires}', ParagraphStyle('Footer', fontSize=9, fontName='Helvetica', textColor=GRAY, alignment=TA_CENTER)))

def generate_reference_pdf(letters):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=1.2*inch, leftMargin=1.2*inch, topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []
    offer_codes = []

    for i, l in enumerate(letters):
        code = l.get('offer_code') or generate_offer_code('REF')
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
            first=(i == 0),
            rep_slug=l.get('rep_slug', '')
        )

    doc.build(story)
    return buffer.getvalue(), offer_codes

RED = colors.HexColor('#B91C1C')


def _summary_flowables(summary, n_generated):
    """Internal cover sheet for a neighbor batch.

    Deliberately looks NOTHING like a letter: Courier not Helvetica, red
    banner, no dealership letterhead, no green rule, no signature block,
    no QR, no offer code.  A rep working fast must never fold this into
    an envelope.

    Counts are DERIVED, not trusted from the caller.  n_generated is
    len(letters) -- the number of letters actually in this file -- so the
    printed count and the document cannot disagree.
    """
    s = []
    s.append(Paragraph('NOT A LETTER - DO NOT MAIL',
             ParagraphStyle('NotLetter', fontSize=20, fontName='Courier-Bold',
                            textColor=RED, alignment=TA_CENTER, spaceAfter=4)))
    s.append(Paragraph('internal check sheet - keep or discard',
             ParagraphStyle('NotLetterSub', fontSize=10, fontName='Courier',
                            textColor=RED, alignment=TA_CENTER, spaceAfter=18)))
    s.append(HRFlowable(width='100%', thickness=3, color=RED, spaceAfter=22))

    h = ParagraphStyle('SumH', fontSize=14, fontName='Courier-Bold',
                       textColor=NAVY, spaceAfter=14)
    row = ParagraphStyle('SumRow', fontSize=12, fontName='Courier',
                         textColor=NAVY, leading=20, spaceAfter=4)

    reasons = summary.get('reasons') or {}
    n_checked = int(summary.get('candidates') or n_generated)
    n_dropped = max(n_checked - n_generated, 0)
    n_explained = sum(int(v) for v in reasons.values())
    n_unexplained = n_dropped - n_explained

    s.append(Paragraph('ADDRESS CHECK RESULTS', h))
    s.append(Paragraph('Addresses checked . . . . %d' % n_checked, row))
    s.append(Paragraph('Letters in this file  . . %d' % n_generated, row))
    s.append(Paragraph('Dropped . . . . . . . . . %d' % n_dropped, row))

    if n_dropped:
        s.append(Spacer(1, 0.12*inch))
        s.append(Paragraph('WHY THEY WERE DROPPED',
                 ParagraphStyle('SumWhy', fontSize=11, fontName='Courier-Bold',
                                textColor=NAVY, spaceAfter=8)))
        det = ParagraphStyle('SumDetail', fontSize=11, fontName='Courier',
                             textColor=GRAY, leading=17, spaceAfter=2)
        for why, n in sorted(reasons.items(), key=lambda kv: -int(kv[1])):
            s.append(Paragraph('%3d  %s' % (int(n), why), det))
        unex = ParagraphStyle('SumUnex', fontSize=11, fontName='Courier-Bold',
                              textColor=RED, leading=17, spaceAfter=2)
        if n_unexplained > 0:
            s.append(Spacer(1, 0.06*inch))
            s.append(Paragraph('%3d  NOT ACCOUNTED FOR - tell your manager'
                               % n_unexplained, unex))
        elif n_unexplained < 0:
            s.append(Spacer(1, 0.06*inch))
            s.append(Paragraph('COUNTS DISAGREE by %d - tell your manager'
                               % abs(n_unexplained), unex))

    near = summary.get('near')
    s.append(Spacer(1, 0.22*inch))
    if near:
        s.append(Paragraph('Neighbors on: <b>%s</b>' % near,
                 ParagraphStyle('SumNear', fontSize=12, fontName='Courier',
                                textColor=NAVY, spaceAfter=6)))
        s.append(Paragraph('If that is not the street and town you meant, '
                           'stop and check the address you started from '
                           'before mailing these.',
                 ParagraphStyle('SumNearWarn', fontSize=10, fontName='Courier',
                                textColor=GRAY, leading=15)))
    else:
        s.append(Paragraph('No deliverable addresses in this batch - nothing '
                           'to mail.',
                 ParagraphStyle('SumNone', fontSize=12, fontName='Courier',
                                textColor=RED, spaceAfter=6)))
        s.append(Paragraph('Every address was checked and none could be '
                           'confirmed as a mailable home. Try a different '
                           'starting address.',
                 ParagraphStyle('SumNoneSub', fontSize=10, fontName='Courier',
                                textColor=GRAY, leading=15)))

    s.append(Spacer(1, 0.30*inch))
    s.append(HRFlowable(width='100%', thickness=0.5, color=GRAY, spaceAfter=8))
    s.append(Paragraph('Addresses confirmed with USPS data. Generated %s'
                       % datetime.now(ET).strftime('%B %d, %Y at %I:%M %p'),
             ParagraphStyle('SumFoot', fontSize=8, fontName='Courier',
                            textColor=GRAY, alignment=TA_CENTER)))
    return s


def generate_halt_pdf(message):
    """Single-page notice for a halted batch.

    No letters exist when the gate halts, and the route cannot return
    nothing, so the rep gets a sheet stating plainly that nothing was
    generated and nothing was sent.  `message` is the REP-facing text
    from rep_halt_message() -- never the technical halt_reason, which is
    logged instead.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=1.2*inch, leftMargin=1.2*inch,
                            topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []
    story.append(Paragraph('NOT A LETTER - DO NOT MAIL',
             ParagraphStyle('HaltTag', fontSize=20, fontName='Courier-Bold',
                            textColor=RED, alignment=TA_CENTER, spaceAfter=4)))
    story.append(Paragraph('internal check sheet - keep or discard',
             ParagraphStyle('HaltTagSub', fontSize=10, fontName='Courier',
                            textColor=RED, alignment=TA_CENTER, spaceAfter=18)))
    story.append(HRFlowable(width='100%', thickness=3, color=RED, spaceAfter=26))
    story.append(Paragraph('NO LETTERS WERE GENERATED',
             ParagraphStyle('HaltH', fontSize=15, fontName='Courier-Bold',
                            textColor=NAVY, spaceAfter=18)))
    for line in (message or '').split('\n'):
        if line.strip():
            story.append(Paragraph(line.strip(),
                 ParagraphStyle('HaltBody', fontSize=12, fontName='Courier',
                                textColor=NAVY, leading=20, spaceAfter=8)))
    story.append(Spacer(1, 0.30*inch))
    story.append(HRFlowable(width='100%', thickness=0.5, color=GRAY, spaceAfter=8))
    story.append(Paragraph('Nothing was mailed and no offer codes were used. %s'
                           % datetime.now(ET).strftime('%B %d, %Y at %I:%M %p'),
             ParagraphStyle('HaltFoot', fontSize=8, fontName='Courier',
                            textColor=GRAY, alignment=TA_CENTER)))
    doc.build(story)
    return buffer.getvalue()


def generate_neighbor_pdf(letters, summary=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=1.2*inch, leftMargin=1.2*inch, topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []
    offer_codes = []

    if summary:
        story.extend(_summary_flowables(summary, len(letters)))

    for i, l in enumerate(letters):
        code = l.get('offer_code') or generate_offer_code('NBR')
        offer_codes.append(code)
        expires = expiry_date(30)
        rep_name = l.get('rep_name', '')
        rep_first = rep_name.split()[0] if rep_name else 'me'

        body = [
            "We just wanted to reach out and say congratulations to one of your neighbors on their recent car purchase from us.",
            "If you've been thinking about upgrading your vehicle, now is a great time to take a look.",
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
            first=(i == 0 and not summary),
            rep_slug=l.get('rep_slug', '')
        )

    if not story:
        story.append(Paragraph('Nothing to print.',
                     ParagraphStyle('Empty', fontSize=12,
                                    fontName='Courier', textColor=NAVY)))

    doc.build(story)
    return buffer.getvalue(), offer_codes


def generate_avery_5160_labels(addresses, return_address=None, prefix=None):
    """
    Generates a printable Avery 5160 label sheet PDF.
    30 labels per page, 3 columns x 10 rows.
    Label size: 2.625" x 1"
    Compatible with Avery 5160 / 8160 label sheets.
    """
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate
    from reportlab.lib.units import inch

    buffer = BytesIO()

    # Page setup — US Letter
    PAGE_W, PAGE_H = letter

    # Avery 5160 specs
    COLS = 3
    ROWS = 10
    LABEL_W = 2.625 * inch
    LABEL_H = 1.0 * inch
    LEFT_MARGIN = 0.19 * inch
    TOP_MARGIN = 0.5 * inch
    COL_GAP = 0.125 * inch

    label_style = ParagraphStyle('Label', fontSize=9, fontName='Helvetica', textColor=NAVY, leading=13, spaceAfter=0)
    small_style = ParagraphStyle('Small', fontSize=7, fontName='Helvetica', textColor=GRAY, leading=10)

    c = canvas.Canvas(buffer, pagesize=letter)

    idx = 0
    total = len(addresses)

    while idx < total:
        # Draw 30 labels per page
        for row in range(ROWS):
            for col in range(COLS):
                if idx >= total:
                    break
                addr = addresses[idx]
                idx += 1

                x = LEFT_MARGIN + col * (LABEL_W + COL_GAP)
                y = PAGE_H - TOP_MARGIN - (row + 1) * LABEL_H

                # Draw label border (light, for alignment — remove for final print)
                c.setStrokeColor(colors.HexColor('#E2E8F0'))
                c.setLineWidth(0.3)
                c.rect(x, y, LABEL_W, LABEL_H)

                # Address text
                if '\n' in addr:
                    lines = [l.strip() for l in addr.split('\n') if l.strip()]
                else:
                    lines = [l.strip() for l in addr.split(',') if l.strip()]
                if prefix:
                    lines = [prefix] + lines
                text_x = x + 0.12 * inch
                text_y = y + LABEL_H - 0.22 * inch

                c.setFont('Helvetica', 9)
                c.setFillColor(NAVY)
                for line in lines[:4]:
                    c.drawString(text_x, text_y, line)
                    text_y -= 13

        if idx < total:
            c.showPage()

    # Footer note on last page
    c.setFont('Helvetica', 7)
    c.setFillColor(colors.HexColor('#94A3B8'))
    c.drawString(LEFT_MARGIN, 0.3 * inch, 'Print on Avery 5160 / 8160 label sheets (30 labels per sheet, 2-5/8" x 1"). Available at Staples, Office Depot, or Amazon.')

    c.save()
    return buffer.getvalue()
