#!/usr/bin/env python3
"""
app/utils/claude_vision.py
Wraps Anthropic Claude Vision API to extract names + addresses
from a photo of a handwritten reference sheet.
"""

import os
import json
import base64
import anthropic


VISION_PROMPT = (
    "Extract all names and addresses from this handwritten reference sheet. "
    "Return JSON in this exact format:\n"
    '[\n'
    '  {"name": "John Smith", "address": "123 Main St, Toms River NJ 08753"},\n'
    '  ...\n'
    ']\n'
    "If a line is illegible, return it with name='UNCLEAR' so the rep can edit. "
    "Do not invent information. Only return valid JSON, no commentary."
)


def extract_references_from_image(image_bytes, media_type='image/jpeg'):
    """
    Takes raw image bytes and media_type.
    Returns list of dicts: [{'name': ..., 'address': ...}, ...]
    Raises ValueError if no names extracted or JSON invalid.
    """
    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))

    image_data = base64.standard_b64encode(image_bytes).decode('utf-8')

    response = client.messages.create(
        model='claude-opus-4-7',
        max_tokens=1000,
        messages=[
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': media_type,
                            'data': image_data,
                        },
                    },
                    {
                        'type': 'text',
                        'text': VISION_PROMPT,
                    }
                ],
            }
        ],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith('```'):
        raw = raw.split('```')[1]
        if raw.startswith('json'):
            raw = raw[4:]
        raw = raw.strip()

    try:
        entries = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"Claude returned invalid JSON: {raw[:200]}")

    if not isinstance(entries, list) or len(entries) == 0:
        raise ValueError("No names extracted from image.")

    # Validate each entry has name and address
    cleaned = []
    for e in entries:
        if isinstance(e, dict) and 'name' in e:
            cleaned.append({
                'name': str(e.get('name', 'UNCLEAR')).strip(),
                'address': str(e.get('address', '')).strip(),
            })

    if len(cleaned) == 0:
        raise ValueError("No valid entries found in extracted JSON.")

    return cleaned
