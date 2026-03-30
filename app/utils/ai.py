import anthropic
import os

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def generate_bio(name, experience_years=None, dealership=None, specialties=None):
    """Generate a professional salesperson bio."""
    prompt = f"Write a short, engaging professional bio (3-4 sentences) for a car salesperson named {name}."
    if experience_years:
        prompt += f" They have {experience_years} years of experience."
    if dealership:
        prompt += f" They work at {dealership}."
    if specialties:
        prompt += f" They specialize in {specialties}."
    prompt += " Make it warm, trustworthy, and focused on customer service. No hashtags. No emojis. Write in first person."
    
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"AI Bio error: {e}")
        return None

def draft_email(salesperson_name, customer_name, vehicle_info, tone="friendly"):
    """Draft a follow-up email to a customer."""
    tones = {
        "friendly": "warm and friendly, like texting a friend",
        "professional": "professional but approachable",
        "urgent": "creating gentle urgency — this deal won't last",
        "checkin": "casual check-in, no pressure"
    }
    tone_desc = tones.get(tone, tones["friendly"])
    
    prompt = f"""Write a short follow-up email (3-5 sentences) from {salesperson_name} to {customer_name} about a {vehicle_info}.
Tone: {tone_desc}.
Include a clear call to action (come see it, schedule a test drive, call me).
No subject line. Just the email body. Sign off with the salesperson's name.
Keep it natural — not salesy or pushy."""
    
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"AI Email error: {e}")
        return None

def chatbot_response(customer_message, salesperson_name, inventory_summary=None, history=None, dealership_name=None):
    """Generate a chatbot response for the storefront."""
    first_name = salesperson_name.split()[0] if salesperson_name else "the salesperson"
    dealership_line = f" at {dealership_name}" if dealership_name else ""
    system = f"""You are a friendly assistant on {salesperson_name}'s car sales page{dealership_line}.
You speak on behalf of {first_name} — a real car salesperson. Keep it casual, warm, and direct. No corporate fluff.
Your only job: help the customer figure out if one of {first_name}'s cars is right for them, and get them to reach out.
Rules:
- Keep every response to 2 sentences max. Never ramble.
- If they ask about a specific car that's listed, give them the key facts (year, price, miles if known).
- If they ask about something not listed, say {first_name} may be able to locate it — just have them reach out.
- Always end with a soft push to call, text, or hit "I'm Interested" on a vehicle.
- Never make up prices, mileage, or details you weren't given.
- Sound like a person, not a bot."""

    if inventory_summary and inventory_summary != "No vehicles currently listed":
        system += f"\n\n{first_name}'s current inventory: {inventory_summary}"
    else:
        system += f"\n\n{first_name} doesn't have vehicles listed right now but can help locate what you need."
    
    try:
        msgs = []
        if history:
            for h in history[-10:]:
                msgs.append({"role": h.get("role","user"), "content": h.get("content","")})
        msgs.append({"role": "user", "content": customer_message})
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=system,
            messages=msgs
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"AI Chat error: {e}")
        return "I'm having trouble right now. Please call or text directly!"
