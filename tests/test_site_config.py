# tests/test_site_config.py

import sys
from unittest.mock import MagicMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.utils.phone_utils.site_config import (
    ExtractionService,
    RequestMethod,
    get_service_for_url,
    get_webcrawler_methods_for_url,
    should_use_camoufox,
)


# ── ExtractionService enum ──────────────────────────────────────────────────


class TestExtractionServiceEnum:
    def test_webcrawler_value(self):
        assert ExtractionService.WEBCRAWLER.value == "webcrawler"

    def test_camoufox_value(self):
        assert ExtractionService.CAMOUFOX.value == "camoufox"


# ── RequestMethod enum ──────────────────────────────────────────────────────


class TestRequestMethodEnum:
    def test_aiohttp_value(self):
        assert RequestMethod.AIOHTTP.value == "aiohttp"

    def test_curl_cffi_value(self):
        assert RequestMethod.CURL_CFFI.value == "curl_cffi"

    def test_httpx_value(self):
        assert RequestMethod.HTTPX.value == "httpx"


# ── get_service_for_url() ───────────────────────────────────────────────────


class TestGetServiceForUrl:
    def test_olx_ua_returns_camoufox(self):
        assert get_service_for_url("https://www.olx.ua/d/uk/nedvizhimost/") == ExtractionService.CAMOUFOX

    def test_dom_ria_returns_camoufox(self):
        assert get_service_for_url("https://dom.ria.com/uk/realty/123") == ExtractionService.CAMOUFOX

    def test_lun_ua_returns_webcrawler(self):
        assert get_service_for_url("https://lun.ua/uk/search") == ExtractionService.WEBCRAWLER

    def test_rieltor_ua_returns_webcrawler(self):
        assert get_service_for_url("https://rieltor.ua/flats-rent/") == ExtractionService.WEBCRAWLER

    def test_unknown_domain_returns_webcrawler_default(self):
        assert get_service_for_url("https://unknown-site.com/page") == ExtractionService.WEBCRAWLER


# ── get_webcrawler_methods_for_url() ─────────────────────────────────────────


class TestGetWebcrawlerMethodsForUrl:
    def test_lun_ua_returns_aiohttp_curl_cffi(self):
        methods = get_webcrawler_methods_for_url("https://lun.ua/uk/search")
        assert methods == [RequestMethod.AIOHTTP, RequestMethod.CURL_CFFI]

    def test_real_estate_lviv_returns_curl_cffi_httpx(self):
        methods = get_webcrawler_methods_for_url("https://real-estate.lviv.ua/listing")
        assert methods == [RequestMethod.CURL_CFFI, RequestMethod.HTTPX]

    def test_olx_ua_camoufox_site_returns_none(self):
        methods = get_webcrawler_methods_for_url("https://www.olx.ua/d/uk/nedvizhimost/")
        assert methods is None

    def test_unknown_domain_returns_default_methods(self):
        methods = get_webcrawler_methods_for_url("https://unknown-site.com/page")
        assert methods == [RequestMethod.AIOHTTP, RequestMethod.CURL_CFFI, RequestMethod.HTTPX]


# ── should_use_camoufox() ───────────────────────────────────────────────────


class TestShouldUseCamoufox:
    def test_olx_ua_returns_true(self):
        assert should_use_camoufox("https://www.olx.ua/d/uk/ad/123") is True

    def test_lun_ua_returns_false(self):
        assert should_use_camoufox("https://lun.ua/uk/search") is False

    def test_unknown_returns_false(self):
        assert should_use_camoufox("https://example.com/page") is False
