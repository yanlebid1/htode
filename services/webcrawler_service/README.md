# WebCrawler Service

A lightweight HTTP client service for web scraping with multiple request methods.

## Purpose

This service provides various HTTP client implementations for websites that work with regular HTTP requests:
- Standard HTTP requests with aiohttp
- Browser impersonation with curl_cffi
- HTTP/2 support with httpx
- Progressive fallback between methods

## Features

- Multiple HTTP client implementations
- Automatic method selection and fallback
- Proxy support across all methods
- Browser impersonation capabilities
- HTTP/2 support
- Configurable timeout and headers
- Lightweight and fast

## API Endpoints

### POST `/crawl`
Fetch a web page using the specified or auto-selected method.

**Request Body:**
```json
{
    "url": "https://example.com",
    "method": "aiohttp",  // optional: "aiohttp", "curl_cffi", "httpx"
    "proxy": "http://proxy:8080",
    "timeout": 30,
    "headers": {
        "User-Agent": "Mozilla/5.0..."
    },
    "follow_redirects": true,
    "impersonate": "chrome110"  // for curl_cffi
}
```

**Response:**
```json
{
    "status": "success",
    "content": "<html>...</html>",
    "status_code": 200,
    "final_url": "https://example.com/redirected",
    "method_used": "aiohttp"
}
```

### GET `/health`
Health check endpoint.

**Response:**
```json
{
    "status": "healthy",
    "service": "webcrawler"
}
```

## Request Methods

### 1. AIOHTTP (Default)
- Fast asynchronous HTTP client
- Good for most standard websites
- Supports proxies and custom headers

### 2. CURL_CFFI
- Uses curl with browser impersonation
- Bypasses many anti-bot systems
- Supports various browser profiles (chrome, firefox, safari)

### 3. HTTPX
- Modern HTTP client with HTTP/2 support
- Better for modern websites
- Supports advanced features

## Method Selection

If no method is specified, the service tries methods in this order:
1. aiohttp (fastest)
2. curl_cffi (if aiohttp fails)
3. httpx (if curl_cffi fails)

You can specify a preferred method in the request.

## Environment Variables

- `PYTHONUNBUFFERED` - Set to 1 for immediate log output

## Performance

- Uses 4 worker processes by default
- Lightweight - only 512MB RAM limit
- Can handle hundreds of requests per second
- No browser overhead

## When to Use This Service

Use WebCrawler service when:
- The website works with regular HTTP requests
- No JavaScript execution is needed
- Content is available in the initial HTML response
- You need high performance and low resource usage

For JavaScript-heavy sites that require browser automation, use the Camoufox service instead.

## Docker Configuration

The service runs in a Docker container with:
- 512MB RAM limit (256MB reserved)
- 1 CPU core limit (0.5 core reserved)
- 4 uvicorn workers for concurrent handling
- Health checks every 30s

## Usage Example

```python
import httpx

# Fetch content from a regular website
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://webcrawler_service:8200/crawl",
        json={
            "url": "https://example.com",
            "method": "curl_cffi",
            "impersonate": "chrome110",
            "proxy": "http://proxy:8080"
        }
    )
    
    result = response.json()
    if result["status"] == "success":
        content = result["content"]
        method = result["method_used"]
        print(f"Fetched with {method}")
```

## Error Handling

The service automatically falls back to other methods if one fails:
- Network errors trigger next method
- 4xx/5xx status codes are returned as-is
- Timeout errors trigger fallback
- All methods failing returns error response 