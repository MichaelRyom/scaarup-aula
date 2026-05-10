import datetime

import pytest

from custom_components.aula.client import (
    Client,
    aggregate_vikar_payload,
    school_year_start,
)


def lesson(date_iso, status, profile_id=1, title=None, teacher=None):
    entry = {
        "type": "lesson",
        "belongsToProfiles": [profile_id],
        "startDateTime": f"{date_iso}T08:00:00+00:00",
        "lesson": {"lessonStatus": status},
    }
    if title is not None:
        entry["title"] = title
    if teacher is not None:
        entry["lesson"]["participants"] = [
            {"teacherName": teacher, "participantRole": "primaryTeacher"}
        ]
    return entry


# ---------------------------------------------------------------------------
# school_year_start
# ---------------------------------------------------------------------------

def test_school_year_start_in_autumn():
    assert school_year_start(datetime.date(2025, 9, 15)) == datetime.date(2025, 8, 1)


def test_school_year_start_january():
    assert school_year_start(datetime.date(2026, 1, 4)) == datetime.date(2025, 8, 1)


def test_school_year_start_first_of_august():
    assert school_year_start(datetime.date(2025, 8, 1)) == datetime.date(2025, 8, 1)


def test_school_year_start_last_of_july():
    assert school_year_start(datetime.date(2025, 7, 31)) == datetime.date(2024, 8, 1)


# ---------------------------------------------------------------------------
# aggregate_vikar_payload — monthly lesson/substitute counts
# ---------------------------------------------------------------------------

def test_aggregate_counts_normal_and_substitute():
    payload = {
        "data": [
            lesson("2025-08-13", "normal"),
            lesson("2025-08-14", "substitute"),
            lesson("2025-08-14", "substitute"),
            lesson("2025-09-01", "normal"),
        ]
    }
    months = aggregate_vikar_payload(payload, 1)
    assert months["2025-08"]["lessons"] == 3
    assert months["2025-08"]["substitute"] == 2
    assert months["2025-09"]["lessons"] == 1
    assert months["2025-09"]["substitute"] == 0


def test_aggregate_filters_by_profile():
    payload = {
        "data": [
            lesson("2025-08-13", "substitute", profile_id=1),
            lesson("2025-08-13", "substitute", profile_id=999),
        ]
    }
    months = aggregate_vikar_payload(payload, 1)
    assert months["2025-08"]["lessons"] == 1
    assert months["2025-08"]["substitute"] == 1


def test_aggregate_skips_non_lesson_entries():
    payload = {
        "data": [
            {"type": "event", "startDateTime": "2025-08-13T08:00:00+00:00"},
            lesson("2025-08-14", "normal"),
        ]
    }
    months = aggregate_vikar_payload(payload, 1)
    assert months["2025-08"]["lessons"] == 1
    assert months["2025-08"]["substitute"] == 0


def test_aggregate_handles_missing_lesson_dict():
    payload = {
        "data": [
            {
                "type": "lesson",
                "belongsToProfiles": [1],
                "startDateTime": "2025-08-13T08:00:00+00:00",
            }
        ]
    }
    months = aggregate_vikar_payload(payload, 1)
    assert months["2025-08"]["lessons"] == 1
    assert months["2025-08"]["substitute"] == 0


def test_aggregate_empty_payload():
    assert aggregate_vikar_payload({}, 1) == {}
    assert aggregate_vikar_payload({"data": []}, 1) == {}
    assert aggregate_vikar_payload({"data": None}, 1) == {}


def test_aggregate_skips_lesson_without_date():
    payload = {
        "data": [
            {
                "type": "lesson",
                "belongsToProfiles": [1],
                "startDateTime": "",
                "lesson": {"lessonStatus": "substitute"},
            },
            lesson("2025-08-13", "substitute"),
        ]
    }
    months = aggregate_vikar_payload(payload, 1)
    assert months["2025-08"]["lessons"] == 1
    assert months["2025-08"]["substitute"] == 1


# ---------------------------------------------------------------------------
# aggregate_vikar_payload — subjects (fag)
# ---------------------------------------------------------------------------

def test_aggregate_tracks_subject():
    payload = {
        "data": [
            lesson("2025-08-13", "substitute", title="Matematik"),
            lesson("2025-08-14", "normal", title="Matematik"),
            lesson("2025-08-15", "substitute", title="Dansk"),
        ]
    }
    months = aggregate_vikar_payload(payload, 1)
    assert months["2025-08"]["subjects"] == {
        "Matematik": {"lessons": 2, "substitute": 1},
        "Dansk": {"lessons": 1, "substitute": 1},
    }


def test_aggregate_skips_lesson_with_no_title():
    payload = {"data": [lesson("2025-08-13", "substitute")]}
    months = aggregate_vikar_payload(payload, 1)
    assert months["2025-08"]["subjects"] == {}


def test_aggregate_subjects_empty_title_ignored():
    payload = {
        "data": [
            {
                "type": "lesson",
                "belongsToProfiles": [1],
                "startDateTime": "2025-08-13T08:00:00+00:00",
                "title": "   ",  # whitespace-only
                "lesson": {"lessonStatus": "normal"},
            }
        ]
    }
    months = aggregate_vikar_payload(payload, 1)
    assert months["2025-08"]["subjects"] == {}


# ---------------------------------------------------------------------------
# aggregate_vikar_payload — teachers (lærer)
# ---------------------------------------------------------------------------

def test_aggregate_tracks_primary_teacher():
    payload = {
        "data": [
            lesson("2025-08-13", "substitute", teacher="Lars Jensen"),
            lesson("2025-08-14", "normal", teacher="Lars Jensen"),
            lesson("2025-08-15", "substitute", teacher="Anna Møller"),
        ]
    }
    months = aggregate_vikar_payload(payload, 1)
    assert months["2025-08"]["teachers"] == {
        "Lars Jensen": {"lessons": 2, "substitute": 1},
        "Anna Møller": {"lessons": 1, "substitute": 1},
    }


def test_aggregate_skips_lesson_with_no_teacher():
    payload = {"data": [lesson("2025-08-13", "substitute")]}
    months = aggregate_vikar_payload(payload, 1)
    assert months["2025-08"]["teachers"] == {}


def test_aggregate_ignores_substitute_teacher_role():
    """substituteTeacher participants must not be counted as the primary teacher."""
    payload = {
        "data": [
            {
                "type": "lesson",
                "belongsToProfiles": [1],
                "startDateTime": "2025-08-13T08:00:00+00:00",
                "lesson": {
                    "lessonStatus": "substitute",
                    "participants": [
                        {
                            "teacherName": "Lars Jensen",
                            "participantRole": "primaryTeacher",
                        },
                        {
                            "teacherName": "Vikar Person",
                            "participantRole": "substituteTeacher",
                        },
                    ],
                },
            }
        ]
    }
    months = aggregate_vikar_payload(payload, 1)
    assert "Vikar Person" not in months["2025-08"]["teachers"]
    assert months["2025-08"]["teachers"] == {
        "Lars Jensen": {"lessons": 1, "substitute": 1}
    }


def test_aggregate_subject_and_teacher_across_months():
    payload = {
        "data": [
            lesson("2025-08-13", "substitute", title="Matematik", teacher="Lars Jensen"),
            lesson("2025-09-01", "normal", title="Matematik", teacher="Lars Jensen"),
        ]
    }
    months = aggregate_vikar_payload(payload, 1)
    assert months["2025-08"]["subjects"]["Matematik"] == {"lessons": 1, "substitute": 1}
    assert months["2025-09"]["subjects"]["Matematik"] == {"lessons": 1, "substitute": 0}
    assert months["2025-08"]["teachers"]["Lars Jensen"] == {"lessons": 1, "substitute": 1}
    assert months["2025-09"]["teachers"]["Lars Jensen"] == {"lessons": 1, "substitute": 0}


# ---------------------------------------------------------------------------
# Client._month_chunks
# ---------------------------------------------------------------------------

def test_month_chunks_single_month():
    chunks = list(
        Client._month_chunks(datetime.date(2025, 8, 5), datetime.date(2025, 8, 20))
    )
    assert chunks == [(datetime.date(2025, 8, 1), datetime.date(2025, 8, 31))]


def test_month_chunks_spans_multiple_months():
    chunks = list(
        Client._month_chunks(datetime.date(2025, 8, 1), datetime.date(2025, 10, 31))
    )
    assert chunks == [
        (datetime.date(2025, 8, 1), datetime.date(2025, 8, 31)),
        (datetime.date(2025, 9, 1), datetime.date(2025, 9, 30)),
        (datetime.date(2025, 10, 1), datetime.date(2025, 10, 31)),
    ]


def test_month_chunks_crosses_year_boundary():
    chunks = list(
        Client._month_chunks(datetime.date(2025, 12, 1), datetime.date(2026, 2, 28))
    )
    assert chunks == [
        (datetime.date(2025, 12, 1), datetime.date(2025, 12, 31)),
        (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31)),
        (datetime.date(2026, 2, 1), datetime.date(2026, 2, 28)),
    ]
