from io import BytesIO
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest


APP_FOLDER = Path(__file__).resolve().parents[2] / "backend" / "app"
sys.path.insert(0, str(APP_FOLDER))

from connectors.sharepoint_connector import _extract_document, _get_view_count
from mappers.document_chunker import create_document_chunks, split_text
from rules.rule_handlers import apply_selected_rules


def test_pptx_extracts_slide_text_and_number():
    pptx = pytest.importorskip("pptx")
    Presentation = pptx.Presentation
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Project update"
    slide.placeholders[1].text = "The ingestion flow is working"
    data = BytesIO()
    presentation.save(data)

    content, units = _extract_document("update.pptx", data.getvalue())

    assert "Project update" in content
    assert "The ingestion flow is working" in units[0]["content"]
    assert units[0]["slide"] == 1


def test_xlsx_extracts_sheet_rows_and_name():
    openpyxl = pytest.importorskip("openpyxl")
    Workbook = openpyxl.Workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sales"
    sheet.append(["Region", "Total"])
    sheet.append(["Sydney", 25])
    data = BytesIO()
    workbook.save(data)

    content, units = _extract_document("sales.xlsx", data.getvalue())

    assert "Sydney | 25" in content
    assert units[0]["sheet"] == "Sales"
    assert [unit["content"] for unit in units] == ["Region | Total", "Sydney | 25"]


def test_long_slide_chunks_are_ordered_and_keep_metadata():
    # A long slide should split with overlap while every chunk keeps its slide number.
    units = [{"content": " ".join(f"word{i}" for i in range(900)), "slide": 2}]

    chunks = create_document_chunks("deck.pptx", ".pptx", units[0]["content"], units)

    assert [chunk["chunk_index"] for chunk in chunks] == [0, 1, 2]
    assert [chunk["chunk_id"] for chunk in chunks] == [
        "deck.pptx_0",
        "deck.pptx_1",
        "deck.pptx_2",
    ]
    assert all(chunk["slide"] == 2 for chunk in chunks)
    assert all(chunk["page"] is None and chunk["sheet"] is None for chunk in chunks)
    assert all(len(chunk["content"].split()) <= 500 for chunk in chunks)
    assert chunks[0]["content"].split()[-50:] == chunks[1]["content"].split()[:50]


def _kb_document(content, modified_at="2026-01-01T00:00:00+00:00", view_count=None):
    return {
        "title": "Article",
        "content": content,
        "modified_at": modified_at,
        "view_count": view_count,
        "tags": [],
    }


def test_sensitive_content_stores_category_not_secret_value():
    # Detection records safe labels rather than leaking the matched credentials.
    document = apply_selected_rules(
        _kb_document("password=MyPassword123 and api key: abc123"),
        "Knowledge Base Rules",
    )

    assert document["contains_sensitive_content"] is True
    assert document["sensitive_matches"] == ["password", "api_key"]
    assert "MyPassword123" not in document["sensitive_matches"]


def test_normal_content_is_not_sensitive_and_is_classified():
    document = apply_selected_rules(
        _kb_document("This setup guide explains how to configure access."),
        "Knowledge Base Rules",
    )

    assert document["contains_sensitive_content"] is False
    assert document["sensitive_matches"] == []
    assert document["kb_category"] == "how-to"
    assert "how-to" in document["tags"]


@pytest.mark.parametrize(
    ("modified_at", "view_count", "expected"),
    [
        ("2020-01-01T00:00:00+00:00", 9, True),
        ("2020-01-01T00:00:00+00:00", 10, False),
        ("2026-01-01T00:00:00+00:00", 9, False),
        ("2020-01-01T00:00:00+00:00", None, False),
    ],
)
def test_stale_requires_old_and_low_view_count(modified_at, view_count, expected):
    # Neither age nor low usage is enough by itself to archive an article.
    document = apply_selected_rules(
        _kb_document("General article", modified_at, view_count),
        "Knowledge Base Rules",
    )

    assert document["is_stale"] is expected
    assert document["kb_status"] == ("archive" if expected else "active")


def test_sentence_aware_split_prefers_sentence_boundaries():
    # Punctuation should be preserved as the natural end of each chunk.
    first = " ".join(["first"] * 300) + "."
    second = " ".join(["second"] * 180) + "!"
    third = " ".join(["third"] * 100) + "?"

    pieces = split_text(f"{first} {second} {third}")

    assert pieces[0].endswith("!")
    assert pieces[1].endswith("?")
    assert all(len(piece.split()) <= 500 for piece in pieces)


def test_graph_analytics_maps_all_time_access_count():
    response = Mock()
    response.json.return_value = {"allTime": {"access": {"actionCount": 12}}}
    session = Mock()
    session.get.return_value = response

    assert _get_view_count(session, "drive-1", "item-1", {"Authorization": "x"}) == 12


def test_graph_analytics_failure_returns_none():
    # Missing analytics should not prevent the rest of the document from loading.
    import requests

    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("forbidden")
    session = Mock()
    session.get.return_value = response

    assert _get_view_count(session, "drive-1", "item-1", {}) is None
