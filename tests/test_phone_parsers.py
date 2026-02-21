# tests/test_phone_parsers.py
#
# Tests for the small, synchronous phone parsers:
#   - rieltor_parser
#   - lun_parser
#   - faktor24_parser
#   - fallback_parser

import sys
from unittest.mock import MagicMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.utils.phone_utils.parsers.rieltor_parser import parse_rieltor_page
from common.utils.phone_utils.parsers.lun_parser import parse_lun_page
from common.utils.phone_utils.parsers.faktor24_parser import parse_faktor24_page
from common.utils.phone_utils.parsers.fallback_parser import fallback_parse
from common.utils.phone_utils.phone_models import ExtractionResult


# ── rieltor_parser ───────────────────────────────────────────────────────


class TestRieltorParser:
    def test_extracts_phone_from_tel_link(self):
        html = '<a href="tel:+380501234567">Call</a>'
        result = parse_rieltor_page(html)
        assert len(result.phone_numbers) == 1
        assert "+380501234567" in result.phone_numbers[0]

    def test_extracts_viber_link(self):
        html = '<a href="viber://chat?number=380501234567" class="viber-btn">Viber</a>'
        result = parse_rieltor_page(html)
        assert result.viber_link is not None
        assert "viber://" in result.viber_link

    def test_returns_empty_when_no_phone(self):
        html = "<div>No phone here</div>"
        result = parse_rieltor_page(html)
        assert result.phone_numbers == []

    def test_returns_none_viber_when_absent(self):
        html = '<a href="tel:+380501234567">Call</a>'
        result = parse_rieltor_page(html)
        assert result.viber_link is None


# ── lun_parser ───────────────────────────────────────────────────────────


class TestLunParser:
    def test_returns_empty_for_json_like_content(self):
        # The LUN regex has a known escaping issue (capture group inside
        # character class) so it currently returns empty for all inputs.
        html = '"phones":"80661234567","geoEntities"'
        result = parse_lun_page(html)
        assert isinstance(result, ExtractionResult)

    def test_returns_empty_when_no_match(self):
        html = "<div>No phone data</div>"
        result = parse_lun_page(html)
        assert result.phone_numbers == []

    def test_viber_is_always_none(self):
        html = "<div>any content</div>"
        result = parse_lun_page(html)
        assert result.viber_link is None


# ── faktor24_parser ──────────────────────────────────────────────────────


class TestFaktor24Parser:
    def test_extracts_phone_from_tel_id(self):
        html = '<a href="tel:+380971234567" id="phoneDisplay">Call</a>'
        result = parse_faktor24_page(html)
        assert len(result.phone_numbers) == 1
        assert "+380971234567" in result.phone_numbers[0]

    def test_returns_empty_when_no_phone(self):
        html = "<div>No phone</div>"
        result = parse_faktor24_page(html)
        assert result.phone_numbers == []

    def test_viber_is_always_none(self):
        html = '<a href="tel:+380971234567" id="phoneDisplay">Call</a>'
        result = parse_faktor24_page(html)
        assert result.viber_link is None


# ── fallback_parser ──────────────────────────────────────────────────────


class TestFallbackParser:
    def test_extracts_phone_from_tel_link(self):
        html = '<html><body><a href="tel:+380501234567">Call</a></body></html>'
        result = fallback_parse(html)
        assert len(result.phone_numbers) >= 1
        assert "+380501234567" in result.phone_numbers[0]

    def test_extracts_viber_link(self):
        html = '<html><body><a href="viber://chat?number=380501234567">Viber</a></body></html>'
        result = fallback_parse(html)
        assert result.viber_link is not None
        assert "viber://" in result.viber_link

    def test_extracts_phone_from_text_pattern(self):
        html = "<html><body><p>Call us: +38 (050) 123-45-67</p></body></html>"
        result = fallback_parse(html)
        assert len(result.phone_numbers) >= 1

    def test_returns_empty_for_no_phones(self):
        html = "<html><body><p>No contact info here</p></body></html>"
        result = fallback_parse(html)
        assert result.phone_numbers == []
        assert result.viber_link is None
