import os
from pathlib import Path
from urllib.parse import urlparse
from datetime import date, time, datetime, timedelta
import calendar
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.db import (
    init_db, create_event, get_event, list_events, list_variants, save_variant,
    analytics, update_variant_status, review_variant, get_variant_review,
    save_publish_checklist, get_publish_checklist, mark_variant_published,
    publishing_history, click_history
)
from src.campaign import AUDIENCES, generate_campaign_variants
from src.llm import LLMError
from src.visuals import create_event_graphic, generate_ai_background
from src.tracking import make_tracked_url, record_query_click

load_dotenv()
init_db()

st.set_page_config(page_title="EventPilot AI", layout="wide")
st.markdown("""
<style>
    .stApp { background: #0b1020; }
    [data-testid="stSidebar"] { background: #10172a; }
    .hero { padding: 1.4rem 1.6rem; border: 1px solid #27334f; border-radius: 18px;
            background: linear-gradient(120deg,#171c38,#123642); margin-bottom: 1rem; }
    .eyebrow { color: #8ee7e2; text-transform: uppercase; letter-spacing: .14em;
               font-size: .76rem; font-weight: 700; }
    .muted { color: #aab5cc; }
    .card { padding: 1rem; border: 1px solid #27334f; border-radius: 14px;
            background: #111a2d; margin: .35rem 0 .8rem 0; }
    h1, h2, h3 { letter-spacing: -.025em; }
    [data-testid="stSidebar"] button { justify-content: flex-start; border-radius: 10px; font-weight: 600; }
    [data-testid="stSidebar"] button[kind="primary"] {
        background: #183b48; color: #8ee7e2; border: 1px solid #326a75;
    }
    [data-testid="stSidebar"] button[kind="secondary"] {
        background: transparent; color: #c3cce0; border-color: transparent;
    }
    [data-testid="stSidebar"] button[kind="secondary"]:hover {
        background: #17243a; border-color: #27334f; color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)

# Capture local tracking URLs, record a click, then clean query params from the visible URL.
params = st.query_params
if params.get("track_event") and params.get("track_variant"):
    if record_query_click(params):
        st.query_params.clear()
        st.toast("Demo ticket click recorded. Analytics updated.")

with st.sidebar:
    st.markdown("## EventPilot AI")
    st.caption("Event marketing workspace")
    st.markdown("**WORKSPACE**")
    navigation = [
        ("Overview", "Overview"),
        ("Create Campaign", "Create Campaign"),
        ("Campaign Library", "Campaign Library"),
        ("Scheduled Posts", "Scheduled Posts"),
        ("Publishing History", "Publishing History"),
        ("Campaign Analytics", "Campaign Analytics"),
        ("Settings", "Settings"),
    ]
    if "active_page" not in st.session_state:
        st.session_state["active_page"] = "Overview"
    for page_name, menu_label in navigation:
        selected = st.session_state["active_page"] == page_name
        if st.button(
            menu_label, key=f"nav_{page_name}", use_container_width=True,
            type="primary" if selected else "secondary",
        ):
            st.session_state["active_page"] = page_name
            st.rerun()
    page = st.session_state["active_page"]
    st.divider()
    st.caption("LOCAL-FIRST MODE")
    st.caption(f"Provider: {os.getenv('LLM_PROVIDER', 'ollama').upper()}")
    st.caption(f"Model: {os.getenv('OLLAMA_MODEL', 'llama3.1:8b')}")

events = list_events()
variants = list_variants()
click_rows = analytics()
total_clicks = sum(r["clicks"] for r in click_rows)
saved_posts = len(variants)
now_local = datetime.now().astimezone().replace(tzinfo=None)

def schedule_datetime(variant):
    value = variant.get("scheduled_for")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

def valid_ticket_url(value):
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)

def show_header(kicker, title, description):
    st.markdown(f"""<div class="hero"><div class="eyebrow">{kicker}</div>
    <h1 style="margin:.35rem 0">{title}</h1><div class="muted">{description}</div></div>""", unsafe_allow_html=True)

if page == "Overview":
    show_header("EVENT MARKETING WORKSPACE", "Turn one event brief into a campaign.", "Create audience-specific content, produce campaign visuals, and learn which message earns attention.")
    a, b, c, d = st.columns(4)
    a.metric("Events", len(events))
    b.metric("Campaign variants", saved_posts)
    c.metric("Tracked clicks", total_clicks)
    d.metric("Audience segments", len(AUDIENCES))
    upcoming = [(v, schedule_datetime(v)) for v in variants if v["status"] == "Scheduled"]
    overdue = [(v, dt) for v, dt in upcoming if dt and dt < now_local]
    due_soon = [(v, dt) for v, dt in upcoming if dt and now_local <= dt <= now_local + timedelta(hours=24)]
    if overdue:
        st.error(f"{len(overdue)} scheduled post(s) are overdue. Open Scheduled Posts and publish or reschedule them.")
    elif due_soon:
        st.warning(f"{len(due_soon)} post(s) are due in the next 24 hours. Review the publishing checklist.")
    elif upcoming:
        st.info(f"{len(upcoming)} post(s) are in your local schedule.")
    st.subheader("Workflow")
    cols = st.columns(4)
    for col, num, title, body in zip(cols, ["01","02","03","04"], ["Brief","Generate","Review","Measure"], [
        "Add the event details once.", "Create tailored copy for each audience.", "Review drafts and save assets.", "Track demo ticket-link clicks."
    ]):
        with col:
            st.markdown(f'<div class="card"><div class="eyebrow">{num}</div><h3>{title}</h3><p class="muted">{body}</p></div>', unsafe_allow_html=True)
    st.subheader("Recent campaigns")
    if variants:
        st.dataframe(pd.DataFrame(variants)[["event_name","audience","platform","status","created_at"]].head(8), use_container_width=True, hide_index=True)
    else:
        st.info("Your workspace is ready. Start by creating your first campaign.")
    st.caption("Publishing is review-first in this version. Instagram posting is not simulated as a successful live publish.")

elif page == "Create Campaign":
    show_header("CAMPAIGN STUDIO", "Create an event campaign", "Enter the facts once. Generate a distinct message for each audience.")
    with st.form("event_form"):
        name = st.text_input("Event name", placeholder="e.g., Fall Jazz Night")
        date = st.text_input("Date and time", placeholder="e.g., Friday, November 13 at 7:30 PM")
        venue = st.text_input("Venue", placeholder="Venue or campus location")
        description = st.text_area("Event description", placeholder="What is happening? What should attendees know?", height=120)
        ticket_url = st.text_input("Ticket link", placeholder="https://example.com/tickets")
        platform = st.selectbox("Target platform", ["Instagram", "Facebook", "LinkedIn"])
        audience_selection = st.multiselect("Audience segments", list(AUDIENCES.keys()), default=list(AUDIENCES.keys()))
        submitted = st.form_submit_button("Generate campaign", type="primary", use_container_width=True)

    if submitted:
        if not all([name.strip(), date.strip(), description.strip(), ticket_url.strip()]):
            st.error("Please provide the event name, date/time, description, and ticket link.")
        elif not valid_ticket_url(ticket_url.strip()):
            st.error("Enter a complete ticket URL beginning with https:// or http://.")
        elif not audience_selection:
            st.error("Select at least one audience segment.")
        else:
            event_id = create_event(name.strip(), date.strip(), venue.strip(), description.strip(), ticket_url.strip())
            event = get_event(event_id)
            with st.spinner("Writing audience-specific campaign copy with your configured model..."):
                try:
                    generated = generate_campaign_variants(event, audience_selection, platform)
                    st.session_state["generated_event_id"] = event_id
                    st.session_state["generated_variants"] = generated
                    st.session_state["generated_platform"] = platform
                    st.session_state["generated_saved"] = False
                    st.success("Campaign copy generated. Review every version before saving.")
                except LLMError as exc:
                    st.error(str(exc))
                    st.info("Your event brief was saved. Check Settings and the model name, then try again.")
                except Exception as exc:
                    st.error(f"Campaign generation failed: {exc}")

    generated = st.session_state.get("generated_variants")
    event_id = st.session_state.get("generated_event_id")
    if generated and event_id:
        event = get_event(event_id)
        st.subheader(f"Drafts for {event['name']}")
        action_cols = st.columns(3)
        if action_cols[0].button("Generate again", use_container_width=True, key=f"regenerate_{event_id}"):
            with st.spinner("Generating a fresh set of captions..."):
                try:
                    fresh_drafts = generate_campaign_variants(
                        event, list(generated), st.session_state.get("generated_platform", "Instagram")
                    )
                    st.session_state["generated_variants"] = fresh_drafts
                    st.session_state["generated_saved"] = False
                    for audience in generated:
                        st.session_state.pop(f"edit_{event_id}_{audience}", None)
                    st.rerun()
                except LLMError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Campaign generation failed: {exc}")
        if action_cols[1].button("Clear drafts", use_container_width=True, key=f"clear_{event_id}"):
            for audience in generated:
                st.session_state.pop(f"edit_{event_id}_{audience}", None)
            st.session_state.pop("generated_variants", None)
            st.session_state.pop("generated_event_id", None)
            st.session_state.pop("generated_saved", None)
            st.rerun()
        if st.session_state.get("generated_saved"):
            action_cols[2].success("Saved to Campaign Library")
        edits = {}
        for audience, caption in generated.items():
            with st.expander(audience, expanded=True):
                edits[audience] = st.text_area(f"{audience} caption", value=caption, height=190, key=f"edit_{event_id}_{audience}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Save reviewed drafts", type="primary", use_container_width=True, disabled=st.session_state.get("generated_saved", False)):
                for audience, caption in edits.items():
                    save_variant(event_id, audience, st.session_state.get("generated_platform", "Instagram"), caption)
                st.session_state["generated_saved"] = True
                st.success("Draft variants saved to Campaign Library.")
                st.rerun()
        background_source = st.radio(
            "Poster background", ["Uploaded photo", "AI-generated", "Abstract"],
            horizontal=True, key=f"background_source_{event_id}",
        )
        event_photo = None
        if background_source == "Uploaded photo":
            event_photo = st.file_uploader(
                "Add an event photo", type=["jpg", "jpeg", "png", "webp"],
                help="A venue, performer, food, or activity photo makes the poster more specific.",
                key=f"event_photo_{event_id}",
            )
        elif background_source == "AI-generated":
            st.caption("Uses the event details with the OpenAI image API. API usage may incur a charge.")
        if event_photo:
            st.image(event_photo, caption="Photo preview", width=260)
        with col2:
            button_label = "Generate poster" if background_source == "AI-generated" else "Generate local event graphic"
            if st.button(button_label, use_container_width=True):
                try:
                    photo_bytes = event_photo.getvalue() if event_photo else None
                    if background_source == "AI-generated":
                        photo_bytes = generate_ai_background(
                            event["name"], event["event_date"], event["venue"], event["description"]
                        )
                    image_path = create_event_graphic(
                        event["name"], event["event_date"], event["venue"], event["description"],
                        photo_bytes if background_source != "Abstract" else None,
                    )
                    st.session_state["last_graphic"] = str(image_path)
                    st.session_state["last_graphic_event_id"] = event_id
                    st.session_state["last_graphic_source"] = background_source
                except Exception as exc:
                    st.error(f"Could not create the event graphic: {exc}")
        graphic = st.session_state.get("last_graphic")
        if graphic and st.session_state.get("last_graphic_event_id") == event_id and Path(graphic).exists():
            graphic_source = st.session_state.get("last_graphic_source")
            caption = {
                "Uploaded photo": "Poster built around your uploaded event photo.",
                "AI-generated": "AI-generated background with event details added by EventPilot.",
                "Abstract": "Poster created locally with an abstract backdrop.",
            }.get(graphic_source, "Poster created locally.")
            st.image(graphic, caption=caption)
            with open(graphic, "rb") as f:
                st.download_button("Download campaign graphic", f, file_name=Path(graphic).name, mime="image/png")

elif page == "Campaign Library":
    show_header("CONTENT LIBRARY", "Review and manage drafts", "Every saved variant stays editable and can be exported for manual publishing.")
    if not variants:
        st.info("No saved variants yet. Generate and save a campaign first.")
    else:
        selected_event = st.selectbox("Filter by event", ["All events"] + [f"{e['id']} · {e['name']}" for e in events])
        filtered = variants
        if selected_event != "All events":
            selected_id = int(selected_event.split(" · ")[0])
            filtered = [v for v in variants if v["event_id"] == selected_id]
        for v in filtered:
            with st.expander(f"{v['event_name']} · {v['audience']} · {v['status']}"):
                st.text_area("Caption", value=v["caption"], height=160, key=f"library_caption_{v['id']}")
                tracked = make_tracked_url(os.getenv("PUBLIC_BASE_URL") or "http://localhost:8501", v["event_id"], v["id"])
                st.code(tracked, language=None)
                st.caption("For local testing only unless PUBLIC_BASE_URL points to a deployed HTTPS app.")
                st.download_button("Export caption (.txt)", v["caption"], file_name=f"eventpilot-{v['id']}.txt", key=f"download_{v['id']}")
                review = get_variant_review(v["id"])
                if review:
                    st.caption(f"Last review: {review['decision']} by {review['reviewer']} · {review['reviewed_at']}")
                    if review.get("note"):
                        st.write(f"Reviewer note: {review['note']}")
                reviewer = st.text_input("Reviewer name", key=f"reviewer_{v['id']}")
                review_note = st.text_area("Review note (optional)", key=f"review_note_{v['id']}", height=70)
                approve_col, changes_col = st.columns(2)
                with approve_col:
                    if st.button("Approve for scheduling", key=f"approve_{v['id']}", disabled=not reviewer.strip()):
                        review_variant(v["id"], reviewer, "Approved", review_note)
                        st.success("Approved. This post can now be scheduled.")
                        st.rerun()
                with changes_col:
                    if st.button("Request changes", key=f"changes_{v['id']}", disabled=not reviewer.strip()):
                        review_variant(v["id"], reviewer, "Changes requested", review_note)
                        st.success("Changes request recorded.")
                        st.rerun()
                if v["status"] == "Scheduled" and st.button("Remove from schedule", key=f"unschedule_{v['id']}"):
                    update_variant_status(v["id"], "Approved", None)
                    st.rerun()

elif page == "Campaign Analytics":
    show_header("PERFORMANCE", "Campaign analytics", "Compare click activity, review progress, and publishing workflow across campaigns.")
    st.caption("These are actual clicks recorded by this app, not Instagram reach or impressions. Local-only links are suitable for testing on your own machine.")
    a, b, c, d = st.columns(4)
    a.metric("Tracked clicks", total_clicks)
    c.metric("Variants with clicks", sum(1 for r in click_rows if r["clicks"] > 0))
    b.metric("Saved variants", len(click_rows))
    d.metric("Published manually", sum(1 for v in variants if v["status"] == "Published manually"))
    review_counts = pd.Series([v["status"] for v in variants]).value_counts() if variants else pd.Series(dtype=int)
    st.subheader("Workflow funnel")
    st.bar_chart(pd.DataFrame({"Variants": review_counts}))
    approved_total = sum(1 for v in variants if v["status"] in ("Approved", "Scheduled", "Published manually"))
    st.caption(f"{approved_total} of {len(variants)} variants have passed review or been published.")
    daily_clicks = click_history()
    if daily_clicks:
        st.subheader("Daily tracked clicks")
        trend = pd.DataFrame(daily_clicks).set_index("click_date")
        st.line_chart(trend["clicks"])
    if click_rows:
        df = pd.DataFrame(click_rows)
        st.subheader("Clicks by audience variant")
        st.bar_chart(df.groupby("audience", as_index=True)["clicks"].sum())
        st.subheader("Variant detail")
        st.dataframe(df[["event_name","audience","platform","status","clicks","created_at"]], use_container_width=True, hide_index=True)
        st.download_button("Export analytics CSV", df.to_csv(index=False), file_name="eventpilot-analytics.csv", mime="text/csv")
    else:
        st.info("Analytics will appear after you save variants and open their tracked links.")

elif page == "Scheduled Posts":
    show_header("PUBLISHING QUEUE", "Schedule a post", "Set a publish time for an approved caption and keep the details in one place.")
    st.info("This queue is a planning tool. It does not connect to Instagram or Meta, publish posts automatically, or send notifications while the app is closed.")
    available = [v for v in variants if v["status"] == "Approved"]
    if available:
        labels = {f"{v['event_name']} · {v['audience']} · {v['platform']} (#{v['id']})": v for v in available}
        with st.form("schedule_post_form"):
            chosen_label = st.selectbox("Saved post", list(labels))
            chosen_date = st.date_input("Publish date", value=date.today())
            chosen_time = st.time_input("Publish time (your local time)", value=time(18, 0))
            submitted_schedule = st.form_submit_button("Add to schedule", type="primary", use_container_width=True)
        if submitted_schedule:
            chosen = labels[chosen_label]
            scheduled_for = datetime.combine(chosen_date, chosen_time).isoformat(timespec="minutes")
            update_variant_status(chosen["id"], "Scheduled", scheduled_for)
            st.success(f"Scheduled {chosen['event_name']} for {scheduled_for.replace('T', ' ')}.")
            st.rerun()
    else:
        st.info("Approve a saved draft in Campaign Library before adding it to the schedule.")

    scheduled = sorted((v for v in variants if v["status"] == "Scheduled"), key=lambda v: v.get("scheduled_for") or "")
    st.subheader("Calendar and queue")
    if scheduled:
        month_anchor = st.date_input("Calendar month", value=date.today(), key="calendar_month")
        month_start = month_anchor.replace(day=1)
        month_weeks = calendar.monthcalendar(month_start.year, month_start.month)
        by_day = {}
        for item in scheduled:
            dt = schedule_datetime(item)
            if dt and dt.year == month_start.year and dt.month == month_start.month:
                by_day.setdefault(dt.day, []).append(f"{dt.strftime('%I:%M %p')} · {item['event_name']}")
        st.caption(month_start.strftime("%B %Y") + " · Times use the timezone configured on this computer.")
        grid = []
        for week in month_weeks:
            grid.append({calendar.day_name[i]: ("\n".join([str(week[i])] + by_day.get(week[i], [])) if week[i] else "") for i in range(7)})
        st.dataframe(pd.DataFrame(grid), use_container_width=True, hide_index=True, height=280)
        st.subheader("Scheduled queue")
        st.dataframe(pd.DataFrame([{
            "Publish date and time": (v.get("scheduled_for") or "Not set").replace("T", " "),
            "Event": v["event_name"], "Audience": v["audience"], "Platform": v["platform"],
            "Caption": v["caption"], "Status": v["status"],
        } for v in scheduled]), use_container_width=True, hide_index=True)
        for v in scheduled:
            with st.expander(f"{v.get('scheduled_for') or 'Unscheduled'} · {v['event_name']} · {v['audience']}"):
                st.text_area("Caption", value=v["caption"], height=130, key=f"scheduled_caption_{v['id']}")
                existing_dt = schedule_datetime(v) or now_local
                with st.form(f"reschedule_form_{v['id']}"):
                    new_day = st.date_input("New date", value=existing_dt.date(), key=f"resched_date_{v['id']}")
                    new_time = st.time_input("New time", value=existing_dt.time().replace(second=0, microsecond=0), key=f"resched_time_{v['id']}")
                    change_schedule = st.form_submit_button("Save new time")
                if change_schedule:
                    update_variant_status(v["id"], "Scheduled", datetime.combine(new_day, new_time).isoformat(timespec="minutes"))
                    st.rerun()
                checklist = get_publish_checklist(v["id"])
                st.markdown("**Before you publish manually**")
                caption_ok = st.checkbox("Caption reviewed", value=bool(checklist.get("caption_checked")), key=f"check_caption_{v['id']}")
                media_ok = st.checkbox("Image or media ready", value=bool(checklist.get("media_checked")), key=f"check_media_{v['id']}")
                platform_ok = st.checkbox(f"Correct {v['platform']} account selected", value=bool(checklist.get("platform_checked")), key=f"check_platform_{v['id']}")
                publish_note = st.text_input("Publishing note (optional)", value=checklist.get("publish_note", ""), key=f"publish_note_{v['id']}")
                if st.button("Save checklist", key=f"save_checklist_{v['id']}"):
                    save_publish_checklist(v["id"], caption_ok, media_ok, platform_ok, publish_note)
                    st.toast("Checklist saved.")
                if st.button("Mark as published manually", key=f"published_{v['id']}", disabled=not (caption_ok and media_ok and platform_ok)):
                    mark_variant_published(v["id"], publish_note)
                    st.success("Added to publishing history as manually published.")
                    st.rerun()
                st.download_button("Export caption (.txt)", v["caption"], file_name=f"eventpilot-{v['id']}.txt", key=f"scheduled_download_{v['id']}")
                if st.button("Cancel scheduled post", key=f"cancel_schedule_{v['id']}"):
                    update_variant_status(v["id"], "Approved", None)
                    st.rerun()
    else:
        st.caption("Your scheduled queue is empty.")

elif page == "Publishing History":
    show_header("REVIEW & PUBLISH LOG", "Publishing history", "Review decisions and manually published posts recorded in this workspace.")
    history = publishing_history()
    if history:
        st.dataframe(pd.DataFrame([{
            "Event": row["event_name"], "Audience": row["audience"], "Platform": row["platform"],
            "Status": row["status"], "Reviewer": row["reviewer"] or "—",
            "Decision": row["decision"] or "—", "Reviewed at": row["reviewed_at"] or "—",
            "Published at": row["published_at"] or "—", "Review note": row["review_note"] or "",
            "Publish note": row["publish_note"] or "",
        } for row in history]), use_container_width=True, hide_index=True)
        st.download_button("Export publishing history CSV", pd.DataFrame(history).to_csv(index=False), file_name="eventpilot-publishing-history.csv", mime="text/csv")
    else:
        st.info("Review and publishing history will appear here.")

elif page == "Settings":
    show_header("CONFIGURATION", "Settings and integrations", "Keep provider configuration outside application code.")
    st.subheader("Current local model configuration")
    st.code(f"LLM_PROVIDER={os.getenv('LLM_PROVIDER', 'ollama')}\nOLLAMA_BASE_URL={os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}\nOLLAMA_MODEL={os.getenv('OLLAMA_MODEL', 'llama3.1:8b')}")
    st.markdown("Change these values in `.env`, then restart Streamlit.")
    st.subheader("Provider adapters")
    st.markdown("Ollama is enabled. Optional Gemini, Groq, and OpenAI examples are commented in `src/llm.py`. Uncomment and install the selected SDK only when you want to test that provider. Keep API keys in `.env`, never in Git.")
    st.subheader("Publishing")
    st.markdown("Posts can be reviewed, scheduled in a local queue, and marked as published manually. The app does not connect to Instagram or Meta. Automated publishing requires an eligible account and an official Meta API integration.")
    st.subheader("Image generation")
    st.markdown("The abstract poster and photo-based poster are composed locally. AI-generated backgrounds use the OpenAI image API and may incur charges.")
    if os.getenv("OPENAI_API_KEY"):
        st.success("OpenAI image generation is configured.")
    else:
        st.info("To enable AI backgrounds, add OPENAI_API_KEY=your-key to .env and restart Streamlit. The key is read from your local environment and is never shown here.")
