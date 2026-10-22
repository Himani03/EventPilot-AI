from src.llm import generate_text

AUDIENCES = {
    "Regulars": "people who already attend events and may appreciate a reason to come back",
    "First-timers": "people who are curious but may need a welcoming, low-pressure introduction",
    "Students": "students who value affordability, social plans, and clear practical details",
}

def build_prompt(event, audience, platform="Instagram"):
    audience_context = AUDIENCES.get(audience, audience)
    return f"""
You are a thoughtful event marketing copywriter. Create one polished {platform} promotional post.

EVENT FACTS (Do not invent facts):
Name: {event['name']}
Date and time: {event['event_date']}
Venue: {event.get('venue') or 'Not provided'}
Description: {event['description']}
Ticket link: {event['ticket_url']}

TARGET AUDIENCE: {audience}
Audience context: {audience_context}

Requirements:
- Make the opening line specific and engaging.
- Adapt the message to the audience rather than just swapping audience labels.
- Include the event name and date.
- Include one clear call to action to get tickets.
- Use 3 to 6 relevant hashtags.
- Keep it concise, around 80 to 140 words.
- Do not invent prices, performers, reviews, scarcity, accessibility details, or other event facts.
- Avoid generic hype and misleading urgency.
- Return only the post copy, no explanation or heading.
""".strip()

def generate_campaign_variants(event, audiences=None, platform="Instagram"):
    audiences = audiences or list(AUDIENCES.keys())
    result = {}
    for audience in audiences:
        result[audience] = generate_text(build_prompt(event, audience, platform))
    return result
