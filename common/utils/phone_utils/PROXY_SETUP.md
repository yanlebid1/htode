# Proxy API Setup Guide

This guide explains how to configure the dynamic proxy fetching system using the proxy-sale.com API.

## Overview

The proxy management system now fetches proxies dynamically from the proxy-sale.com API instead of storing credentials in files. This provides better security and automatic proxy updates.

## Features

- **Secure**: API key stored in environment variables, no credentials in code
- **Cached**: Proxies cached for 30 days since they don't update frequently
- **Automatic**: Fetches from API when cache expires or is missing
- **Fallback**: Graceful degradation if API is unavailable
- **Rotation**: Random proxy selection for load balancing

## Setup Instructions

### 1. Set Environment Variable

Add your proxy-sale.com API key to your environment:

```bash
# For current session
export PROXY_SALE_API_KEY=ff2fffd65937c5866d6dbd14bfece9c8

# For permanent setup (add to ~/.bashrc or ~/.profile)
echo 'export PROXY_SALE_API_KEY=ff2fffd65937c5866d6dbd14bfece9c8' >> ~/.bashrc
source ~/.bashrc
```

### 2. Test the Setup

Run the test script to verify everything works:

```bash
cd /path/to/your/project
python -m common.utils.phone_utils.proxy_manager
```

Expected output:
```
Testing Proxy API Integration
========================================
✅ API key found: ff2fffd6...
🔄 Loading proxies...
✅ Successfully loaded 5 proxies
🎲 Testing random proxy selection:
  Proxy 1: http://***:***@127.0.0.1:80
  Proxy 2: http://***:***@192.168.1.1:8080
  Proxy 3: http://***:***@10.0.0.1:3128
✅ All tests passed!
```

### 3. Using in Code

The proxy system works transparently with existing code:

```python
from common.utils.phone_utils import extract_phone_numbers_from_resource

# Proxy will be automatically selected from API
result = extract_phone_numbers_from_resource("https://example.com/ad")
```

Or manually get a proxy:

```python
from common.utils.phone_utils.proxy_manager import get_random_proxy

proxy = get_random_proxy()
if proxy:
    print(f"Using proxy: {proxy}")
```

## API Response Format

The system expects this JSON structure from proxy-sale.com:

```json
{
  "status": "success",
  "data": {
    "items": [
      {
        "id": 10,
        "ip": "127.0.0.1",
        "port_http": 80,
        "login": "username",
        "password": "password",
        "status": "ACTIVE"
      }
    ]
  },
  "errors": []
}
```

## Cache Management

### Cache Location
- File: `proxy_cache.json` in project root
- Contains: Fetched proxies + timestamp
- Validity: 30 days

### Manual Cache Refresh

Force refresh when needed:

```python
from common.utils.phone_utils.proxy_manager import refresh_proxies

refresh_proxies()  # Forces API fetch, bypassing cache
```

### Cache File Structure

```json
{
  "timestamp": 1703097600.0,
  "proxies": [
    {
      "id": 10,
      "ip": "127.0.0.1",
      "port_http": 80,
      "login": "username",
      "password": "password",
      "status": "ACTIVE"
    }
  ]
}
```

## Error Handling

The system handles various error scenarios:

- **Missing API key**: Logs error, continues without proxies
- **API unavailable**: Uses cached proxies if available
- **Invalid response**: Logs warning, continues without proxies
- **Network errors**: Retries with exponential backoff

## Security Notes

- ✅ **API key in environment variables** - not in code
- ✅ **Credentials not logged** - masked in debug output
- ✅ **HTTPS API calls** - encrypted transmission
- ✅ **Local cache only** - no remote credential storage

## Troubleshooting

### No proxies loaded
1. Check API key: `echo $PROXY_SALE_API_KEY`
2. Test API manually: `curl -X GET "https://proxy-sale.com/personal/api/v1/YOUR_KEY/proxy/list/ipv4"`
3. Check logs for error messages
4. Verify network connectivity

### Cache issues
1. Delete cache file: `rm proxy_cache.json`
2. Force refresh: Call `refresh_proxies()`
3. Check file permissions

### API errors
- **401 Unauthorized**: Invalid API key
- **403 Forbidden**: API key lacks permissions
- **429 Too Many Requests**: Rate limit exceeded
- **500 Server Error**: proxy-sale.com issues

## Migration from File-based System

If upgrading from the old file-based system:

1. Set up environment variable (step 1 above)
2. Remove old `TxtProxy.txt` file
3. Test with the new system
4. Old `load_proxies(file_path)` calls still work (with deprecation warning)

The system is backward compatible but will ignore file paths and use the API instead. 