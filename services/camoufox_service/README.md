# Camoufox Service

A browser automation service for JavaScript-heavy websites that require full browser execution.

## Purpose

This service provides browser automation capabilities using Camoufox for websites that:
- Require JavaScript execution to reveal content
- Need user interaction (clicking buttons, waiting for dynamic content)
- Have sophisticated anti-bot protection that requires real browser behavior

## Features

- Browser pool management for concurrent requests
- Support for proxies with authentication
- JavaScript execution capability
- CSS selector waiting
- Redirect handling
- Headless browser operation with human-like behavior

## API Endpoints

### POST `/browse`
Load a page in browser and return content.

**Request Body:**
```json
{
    "url": "https://example.com/listing",
    "proxy": "http://user:pass@proxy:8080",
    "timeout": 30,
    "wait_after_load": 3000,
    "execute_script": "document.querySelector('.phone-button').click();",
    "wait_for_selector": ".phone-number"
}
```

**Response:**
```json
{
    "status": "success",
    "content": "<html>...</html>",
    "final_url": "https://example.com/listing",
    "status_code": 200,
    "script_result": null
}
```

### GET `/health`
Health check endpoint.

**Response:**
```json
{
    "status": "healthy",
    "service": "camoufox"
}
```

## Environment Variables

- `BROWSER_POOL_SIZE` - Number of browser instances (default: 3)
- `PYTHONUNBUFFERED` - Set to 1 for immediate log output

## Performance Considerations

- The service maintains a pool of browser instances for efficiency
- Each browser instance uses ~200-300MB of RAM
- Recommended pool size: 3-5 instances for most workloads
- Browser instances are reused across requests
- Shared memory volume (`/dev/shm`) is used for better performance

## When to Use This Service

Use Camoufox service when:
- The website loads content dynamically with JavaScript
- Phone numbers or other data are revealed only after user interaction
- Simple HTTP requests return incomplete or obfuscated content
- The site has strong anti-bot protection

For simpler sites that work with regular HTTP requests, use the WebCrawler service instead.

## Docker Configuration

The service runs in a Docker container with:
- 2GB RAM limit (1GB reserved)
- 2 CPU cores limit (1 core reserved)
- Shared memory volume for browser performance
- Health checks with 40s startup period
- Automatic restart on failure

## Usage Example

```python
import httpx

# Extract content from a JavaScript-heavy page
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://camoufox_service:8100/browse",
        json={
            "url": "https://olx.ua/d/uk/obyavlenie/...",
            "wait_after_load": 3000,
            "execute_script": "document.querySelector('.phone-button')?.click();",
            "wait_for_selector": ".phone-number",
            "proxy": "http://proxy:8080"
        }
    )
    
    result = response.json()
    if result["status"] == "success":
        content = result["content"]
        # Process the content
```

## Camoufox Features

The service uses Camoufox browser with:
- **Headless mode** for server environments
- **Human-like behavior** to avoid detection
- **WebRTC blocking** for privacy
- **GeoIP support** for location-based content
- **Windows OS spoofing** for better compatibility
- **Ukrainian locale** as default 