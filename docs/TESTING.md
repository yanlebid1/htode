# Parser Testing Guide

This guide explains how to test the phone number extraction parsers for different real estate websites.

## Testing Architecture

The system uses two services for content extraction:
- **WebCrawler Service** (Port 8200) - For sites that work with regular HTTP requests
- **Camoufox Service** (Port 8100) - For JavaScript-heavy sites requiring browser automation

## Quick Start

### 1. Show Current Configuration

To see which sites use which services:

```bash
python test_parser_extraction.py --show-config
```

### 2. Test a URL

#### Local Testing

First, start the services:
```bash
./run_services_local.sh
```

Then in another terminal:
```bash
# Auto-detect service based on URL
python test_parser_extraction.py "https://www.olx.ua/d/uk/obyavlenie/..."

# Force specific service
python test_parser_extraction.py "https://lun.ua/..." --service webcrawler

# Force specific HTTP method
python test_parser_extraction.py "https://lun.ua/..." --service webcrawler --method curl_cffi
```

#### Docker Testing

If services are running in Docker:
```bash
./test_parser_docker.sh "https://www.olx.ua/d/uk/obyavlenie/..."
```

## Test Options

```
test_parser_extraction.py [-h] [--service {webcrawler,camoufox,auto}]
                         [--method {aiohttp,curl_cffi,httpx}]
                         [--proxy PROXY] [--full-flow] [--show-config]
                         [url]

Options:
  url                   URL to test
  --service             Force specific service (default: auto)
  --method              Force specific method for webcrawler
  --proxy               Use proxy for requests
  --full-flow           Test complete parser flow
  --show-config         Show site configuration
```

## Site Configuration

Current configuration (from `site_config.py`):

### Sites Using Camoufox (Browser)
- `olx.ua` - Requires clicking button to reveal phone
- `dom.ria.com` - Requires interaction to show phone

### Sites Using WebCrawler
- `lun.ua` - Phone in HTML (aiohttp, curl_cffi)
- `rieltor.ua` - Phone in HTML (aiohttp)
- `real-estate.lviv.ua` - May need browser impersonation (curl_cffi, httpx)
- `faktor24.com` - Simple HTML (aiohttp)

## Understanding Test Output

A successful test shows:

```
📊 TEST RESULTS
============================================================

🌐 URL: https://lun.ua/uk/...
➡️  Final URL: https://lun.ua/uk/... (if redirected)

🛠️  Service Detection:
   - Detected: webcrawler
   - Used: webcrawler
   - Method: aiohttp

📡 Response:
   - Status Code: 200
   - Execution Time: 1.23s

✅ Success!

📞 Phone Numbers Found: 2
   1. +380501234567
   2. +380671234567

📄 Content Preview:
----------------------------------------
<!DOCTYPE html><html lang="uk">...
----------------------------------------
```

## Testing Specific Scenarios

### 1. Test Flatfy Redirect
```bash
python test_parser_extraction.py "https://flatfy.ua/uk/redirect/..."
```

### 2. Test with Proxy
```bash
python test_parser_extraction.py "https://olx.ua/..." --proxy "http://user:pass@proxy:8080"
```

### 3. Test Full Parser Flow
This tests the complete flow as used in production:
```bash
python test_parser_extraction.py "https://olx.ua/..." --full-flow
```

### 4. Force WebCrawler Methods
Test different HTTP client implementations:
```bash
# Standard HTTP
python test_parser_extraction.py "https://lun.ua/..." --service webcrawler --method aiohttp

# Browser impersonation
python test_parser_extraction.py "https://lun.ua/..." --service webcrawler --method curl_cffi

# HTTP/2 support
python test_parser_extraction.py "https://lun.ua/..." --service webcrawler --method httpx
```

## Troubleshooting

### Services Not Starting Locally

1. Check if ports are already in use:
```bash
lsof -i :8100
lsof -i :8200
```

2. Install missing dependencies:
```bash
pip install -r services/webcrawler_service/requirements.txt
pip install -r services/camoufox_service/requirements.txt
```

### Docker Testing Issues

1. Ensure containers are running:
```bash
docker-compose ps
```

2. Check service logs:
```bash
docker-compose logs camoufox_service
docker-compose logs webcrawler_service
```

### No Phone Numbers Found

1. Check if the URL is valid and accessible
2. Try forcing Camoufox service: `--service camoufox`
3. Check the content preview to see what was extracted
4. Some sites may have changed their HTML structure

## Adding New Sites

To add support for a new site:

1. Edit `common/utils/phone_utils/site_config.py`:
```python
SITE_CONFIG = {
    # ...
    "newsite.com": {
        "service": ExtractionService.WEBCRAWLER,
        "methods": [RequestMethod.AIOHTTP],
        "description": "New site description"
    }
}
```

2. Create a parser in `common/utils/phone_utils/parsers/`

3. Test with the tool:
```bash
python test_parser_extraction.py "https://newsite.com/listing/123"
```

## Logs

When running locally with `run_services_local.sh`:
- WebCrawler logs: `logs/webcrawler.log`
- Camoufox logs: `logs/camoufox.log`

## Performance Tips

1. **Use WebCrawler when possible** - It's much faster than browser automation
2. **Test with real URLs** - Some sites behave differently with test data
3. **Monitor execution time** - If >5s, consider if the site really needs Camoufox
4. **Use proxies wisely** - They add latency but may be required for some sites 