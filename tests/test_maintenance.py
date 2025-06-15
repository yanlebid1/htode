# tests/test_maintenance.py

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from system.maintenance import (
    cleanup_old_ads,
    is_ad_inactive,
    get_ad_images,
    delete_ad,
    cleanup_expired_verification_codes
)


@pytest.fixture
def mock_old_ads():
    """Mock data for old ads"""
    return [
        {"id": 1, "external_id": "ext1", "resource_url": "https://example.com/ad1"},
        {"id": 2, "external_id": "ext2", "resource_url": "https://example.com/ad2"},
        {"id": 3, "external_id": "ext3", "resource_url": "https://example.com/ad3"}
    ]


@pytest.fixture
def mock_ad_images():
    """Mock data for ad images"""
    return [
        "https://example.com/bucket/image1.jpg",
        "https://example.com/bucket/image2.jpg"
    ]


def test_is_ad_inactive():
    """Test ad activity checking"""
    with patch("system.maintenance.make_request") as mock_request:
        # Test inactive ad (404 response)
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_request.return_value = mock_response

        assert is_ad_inactive("https://example.com/inactive") is True

        # Test active ad (200 response)
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        assert is_ad_inactive("https://example.com/active") is False

        # Test error case
        mock_request.side_effect = Exception("Connection error")

        assert is_ad_inactive("https://example.com/error") is True


def test_get_ad_images(mock_execute_query):
    """Test retrieving ad images"""
    mock_execute_query.return_value = [
        {"image_url": "https://example.com/bucket/image1.jpg"},
        {"image_url": "https://example.com/bucket/image2.jpg"}
    ]

    result = get_ad_images(1)

    assert len(result) == 2
    assert "https://example.com/bucket/image1.jpg" in result
    assert "https://example.com/bucket/image2.jpg" in result

    # Test empty case
    mock_execute_query.return_value = []

    assert get_ad_images(2) == []


def test_delete_ad(mock_execute_query):
    """Test ad deletion"""
    # Mock successful deletion
    mock_execute_query.return_value = MagicMock(rowcount=1)

    assert delete_ad(1) is True

    # Verify execute_query was called for favorite_ads and ads
    assert mock_execute_query.call_count >= 2

    # Test failure case
    mock_execute_query.side_effect = Exception("Database error")

    assert delete_ad(2) is False


@pytest.mark.asyncio
async def test_cleanup_old_ads(mock_old_ads, mock_ad_images, mock_execute_query):
    """Test the main cleanup function"""
    with patch("system.maintenance.get_old_ads_for_cleanup", return_value=mock_old_ads), \
            patch("system.maintenance.is_ad_inactive", return_value=True), \
            patch("system.maintenance.get_ad_images", return_value=mock_ad_images), \
            patch("system.maintenance.delete_ad", return_value=True), \
            patch("system.maintenance.delete_s3_image", return_value=True):
        result = cleanup_old_ads(days_old=30, check_activity=True)

        assert result["status"] == "completed"
        assert result["ads_deleted"] == 3
        assert result["images_deleted"] == 6  # 2 images per ad, 3 ads


def test_cleanup_expired_verification_codes(mock_execute_query):
    """Test cleanup of expired verification codes"""
    # Mock rowcount for both delete operations
    mock_execute_query.return_value = MagicMock(rowcount=5)

    result = cleanup_expired_verification_codes()

    assert result["verification_codes_deleted"] == 5
    assert result["email_tokens_deleted"] == 5
    assert mock_execute_query.call_count == 2