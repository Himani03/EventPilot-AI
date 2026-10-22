from src.campaign import build_prompt, AUDIENCES

def test_prompt_includes_event_facts_and_audience():
    event = {
        "name": "Community Film Night",
        "event_date": "Friday at 7 PM",
        "venue": "Student Center",
        "description": "A short film showcase and discussion.",
        "ticket_url": "https://example.com/tickets",
    }
    prompt = build_prompt(event, "Students")
    assert "Community Film Night" in prompt
    assert "https://example.com/tickets" in prompt
    assert "Students" in prompt
    assert "Do not invent facts" in prompt

def test_three_audience_segments_exist():
    assert set(AUDIENCES) == {"Regulars", "First-timers", "Students"}
