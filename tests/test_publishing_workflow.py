import pytest

from src import db


@pytest.fixture
def local_db(tmp_path, monkeypatch):
    """Give each test an isolated SQLite database."""
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "eventpilot-test.db")
    db.init_db()
    event_id = db.create_event(
        "Community Film Night", "Friday at 7 PM", "Student Center",
        "Short films and discussion", "https://example.com/tickets",
    )
    variant_id = db.save_variant(event_id, "Students", "Instagram", "Join us Friday!")
    return event_id, variant_id


def test_review_records_reviewer_and_updates_status(local_db):
    _, variant_id = local_db
    assert db.get_variant_review(variant_id) is None

    db.review_variant(variant_id, "  Casey  ", "Approved", "Caption looks good.")

    review = db.get_variant_review(variant_id)
    variant = db.list_variants()[0]
    assert review["reviewer"] == "Casey"
    assert review["decision"] == "Approved"
    assert review["note"] == "Caption looks good."
    assert variant["status"] == "Approved"


@pytest.mark.parametrize("reviewer,decision", [("   ", "Approved"), ("Casey", "Maybe")])
def test_review_rejects_blank_reviewer_or_unknown_decision(local_db, reviewer, decision):
    _, variant_id = local_db

    with pytest.raises(ValueError):
        db.review_variant(variant_id, reviewer, decision)


def test_review_can_be_replaced_by_a_later_decision(local_db):
    _, variant_id = local_db
    db.review_variant(variant_id, "Casey", "Changes requested", "Add the venue.")
    db.review_variant(variant_id, "Jordan", "Approved", "Updated copy checked.")

    review = db.get_variant_review(variant_id)
    assert review["reviewer"] == "Jordan"
    assert review["decision"] == "Approved"
    assert review["note"] == "Updated copy checked."
    assert db.list_variants()[0]["status"] == "Approved"


def test_checklist_persists_and_manual_publish_is_recorded(local_db):
    _, variant_id = local_db
    assert db.get_publish_checklist(variant_id) == {}
    db.save_publish_checklist(variant_id, True, True, False, "Need final account check.")
    checklist = db.get_publish_checklist(variant_id)
    assert checklist["caption_checked"] == 1
    assert checklist["media_checked"] == 1
    assert checklist["platform_checked"] == 0

    db.save_publish_checklist(variant_id, True, True, True, "Published to Instagram.")
    db.mark_variant_published(variant_id, "Published to Instagram.")
    updated = db.get_publish_checklist(variant_id)
    assert updated["published_at"]
    assert updated["publish_note"] == "Published to Instagram."
    assert db.list_variants()[0]["status"] == "Published manually"
    assert db.list_variants()[0]["scheduled_for"] is None


def test_schedule_updates_and_cancellation_clear_schedule(local_db):
    _, variant_id = local_db
    first_time = "2026-11-10T18:00"
    second_time = "2026-11-11T19:30"
    db.update_variant_status(variant_id, "Scheduled", first_time)
    db.update_variant_status(variant_id, "Scheduled", second_time)
    assert db.list_variants()[0]["scheduled_for"] == second_time

    db.update_variant_status(variant_id, "Approved", None)
    assert db.list_variants()[0]["status"] == "Approved"
    assert db.list_variants()[0]["scheduled_for"] is None


def test_history_handles_no_records_and_includes_review_and_published_posts(local_db):
    _, variant_id = local_db
    assert db.publishing_history() == []

    db.review_variant(variant_id, "Casey", "Approved")
    reviewed = db.publishing_history()
    assert len(reviewed) == 1
    assert reviewed[0]["reviewer"] == "Casey"
    assert reviewed[0]["published_at"] is None

    db.mark_variant_published(variant_id)
    history = db.publishing_history()
    assert len(history) == 1
    assert history[0]["status"] == "Published manually"
    assert history[0]["published_at"]


def test_click_history_empty_and_grouped_by_day(local_db):
    event_id, variant_id = local_db
    assert db.click_history() == []

    with db.connect() as conn:
        conn.executemany(
            "INSERT INTO clicks(variant_id,event_id,clicked_at) VALUES(?,?,?)",
            [
                (variant_id, event_id, "2026-10-20T10:00:00+00:00"),
                (variant_id, event_id, "2026-10-20T12:00:00+00:00"),
                (variant_id, event_id, "2026-10-21T12:00:00+00:00"),
            ],
        )

    assert db.click_history() == [
        {"click_date": "2026-10-20", "clicks": 2},
        {"click_date": "2026-10-21", "clicks": 1},
    ]


def test_database_initialization_is_safe_to_repeat(local_db):
    event_id, variant_id = local_db
    db.review_variant(variant_id, "Casey", "Approved")

    db.init_db()

    assert len(db.list_events()) == 1
    assert db.list_events()[0]["id"] == event_id
    assert db.get_variant_review(variant_id)["reviewer"] == "Casey"
