# AdsPower Integration Setup Guide

This guide explains how to set up and use the AdsPower integration for OLX phone extraction in your Docker environment.

## Overview

The AdsPower integration allows you to:
- Use multiple AdsPower profiles for phone extraction
- Intelligently detect when login is required for OLX ads
- Rotate between different OLX accounts to avoid rate limiting  
- Scale phone extraction while avoiding detection
- Track usage statistics and manage daily limits

## Smart Retry Logic

The system implements intelligent method selection:

1. **Login Detection**: Check if OLX ad requires login by looking for login button selector: `//div[@data-testid="ad-action-box"]//button[@data-testid="login-button"]`

2. **Method Selection**:
   - **Login Required** → Use AdsPower directly (logged-in profiles)
   - **No Login Required** → Try Camoufox first, fallback to AdsPower if needed

3. **Popup Handling**: Automatically detect and close common OLX popups:
   - Cookie banners: `button[data-testid*="cookie"]` 
   - Survey popups: `div[data-testid="survey-container"]` → close via `button[aria-label="Close"]`

4. **Benefits**:
   - Faster extraction for public ads (no need for AdsPower)
   - Automatic fallback for protected ads
   - Reduced load on AdsPower profiles
   - Better success rates
   - Handles interfering popups automatically

## Prerequisites

1. **AdsPower Desktop Application** installed and running on host system
2. **Multiple AdsPower profiles** created with different browser fingerprints
3. **Multiple OLX accounts** manually logged into each AdsPower profile
4. **Docker and Docker Compose** installed

## Setup Steps

### 1. AdsPower Configuration

1. **Start AdsPower** on your host system
2. **Create multiple profiles** in AdsPower:
   - Create at least 2-3 profiles for testing
   - Use different browser fingerprints for each profile
   - Note down the profile IDs (shown in AdsPower interface)

3. **Configure API access**:
   - AdsPower API runs on `http://localhost:50325` by default
   - Make sure this port is accessible from Docker containers

### 2. Project Configuration

1. **Update the configuration file** (`adspower_config.json`):
   ```json
   {
     "profiles": [
       {
         "profile_id": "k10no2qx",  // Your actual AdsPower profile ID
         "profile_name": "Profile 1",
         "olx_email": null,        // Optional: for reference only
         "olx_password": null,     // Optional: for reference only  
         "last_used": null,
         "usage_count": 0,
         "max_daily_usage": 50,
         "is_active": true
       },
       {
         "profile_id": "abc123def",  // Your second profile ID
         "profile_name": "Profile 2", 
         "olx_email": null,        // Optional: for reference only
         "olx_password": null,     // Optional: for reference only
         "last_used": null,
         "usage_count": 0,
         "max_daily_usage": 50,
         "is_active": true
       }
     ],
     "stats": {
       "total_extractions": 0,
       "successful_extractions": 0,
       "failed_extractions": 0,
       "last_extraction": null
     }
   }
   ```

   **To find your profile IDs:**
   - Open AdsPower
   - Go to your profile list
   - The profile ID is shown in the profile details

   **Manual Login Required:** 
   - Open each AdsPower profile
   - Manually login to OLX in each profile's browser
   - Keep the sessions active

2. **Network Configuration**:
   Add to your `docker-compose.yml` if needed:
   ```yaml
   services:
     scraper_worker_service:
       # ... existing config ...
       extra_hosts:
         - "local.adspower.net:host-gateway"  # Allow access to host AdsPower
   ```

### 3. Build and Deploy

1. **Build the updated scraper service**:
   ```bash
   docker-compose build scraper_worker_service
   ```

2. **Start the services**:
   ```bash
   docker-compose up -d
   ```

3. **Copy configuration to container**:
   ```bash
   docker cp adspower_config.json scraper_worker_service:/app/
   ```

### 4. Testing

1. **Test the integration**:
   ```bash
   docker exec -it scraper_worker_service python -m pytest tests/test_adspower_integration.py -v
   ```

2. **Test phone extraction**:
   ```bash
   docker exec -it scraper_worker_service python -c "
   from services.scraper_service.app.tasks import extract_phone_adspower
   result = extract_phone_adspower('https://www.olx.ua/d/uk/obyavlenie/your-test-ad-url.html')
   print(result)
   "
   ```

3. **Check stats**:
   ```bash
   docker exec -it scraper_worker_service python -c "
   from services.scraper_service.app.tasks import get_adspower_stats
   print(get_adspower_stats())
   "
   ```

## Usage

### Via Celery Tasks

```python
from celery import Celery

app = Celery('scraper')

# Extract phone using AdsPower
result = app.send_task(
    'scraper_service.app.tasks.extract_phone_adspower',
    args=['https://www.olx.ua/d/uk/obyavlenie/your-ad-url.html']
)

print(result.get())
```

### Direct Usage

```python
from common.utils.phone_utils.adspower_manager import adspower_manager

# Extract phone with automatic profile rotation
phone = adspower_manager.extract_phone_with_rotation(
    'https://www.olx.ua/d/uk/obyavlenie/your-ad-url.html'
)

print(f"Extracted phone: {phone}")

# Get statistics
stats = adspower_manager.get_stats()
print(f"Success rate: {stats['success_rate']:.1f}%")
```

### Integration with Existing Phone Parser

The AdsPower integration is automatically used as a fallback in the existing phone parser:

```python
from common.utils.phone_utils.parsers.phone_parser import extract_phone_numbers_from_resource

# This will try Camoufox first, then fall back to AdsPower if needed
result = extract_phone_numbers_from_resource(
    'https://www.olx.ua/d/uk/obyavlenie/your-ad-url.html'
)
```

## Configuration Options

### Profile Settings

- `profile_id`: AdsPower profile identifier
- `profile_name`: Human-readable name for logging
- `olx_email/password`: Optional OLX account credentials
- `max_daily_usage`: Maximum extractions per day per profile
- `is_active`: Whether to use this profile in rotation

### Manager Settings

- `chromedriver_path`: Path to ChromeDriver 134 (default: `/tmp/chromedriver-linux64/chromedriver`)
- `adspower_api_url`: AdsPower API endpoint (default: `http://local.adspower.net:50325`)

## Monitoring and Logging

### View Logs
```bash
docker logs scraper_worker_service | grep -i adspower
```

### Statistics
```bash
docker exec -it scraper_worker_service python -c "
from common.utils.phone_utils.adspower_manager import adspower_manager
print(adspower_manager.get_stats())
"
```

### Configuration Status
```bash
docker exec -it scraper_worker_service python -c "
from common.utils.phone_utils.adspower_manager import adspower_manager
for i, p in enumerate(adspower_manager.profiles):
    print(f'Profile {i+1}: {p.profile_name} - Used: {p.usage_count}/{p.max_daily_usage}')
"
```

## Troubleshooting

### Common Issues

1. **"No AdsPower profiles configured"**
   - Update `adspower_config.json` with real profile IDs
   - Copy the file to the Docker container

2. **"Failed to start profile"**
   - Check if AdsPower is running on host
   - Verify profile IDs are correct
   - Check network connectivity (`extra_hosts` in docker-compose.yml)

3. **"ChromeDriver version mismatch"**
   - The Docker image includes ChromeDriver 134.0.6998.36
   - Make sure AdsPower profiles use Chrome 134

4. **"All profiles at daily usage limit"**
   - Reset usage counts or wait for daily reset
   - Add more profiles to the configuration

### Network Connectivity Test
```bash
docker exec -it scraper_worker_service curl -s http://local.adspower.net:50325/api/v1/browser/list
```

### Debug Mode
Add environment variable to enable debug logging:
```yaml
environment:
  LOG_LEVEL: DEBUG
```

## Security Considerations

1. **Credentials Storage**: Store OLX credentials securely
2. **Rate Limiting**: Respect OLX's usage limits
3. **Profile Rotation**: Use random delays between extractions
4. **Monitoring**: Monitor for detection and adjust settings accordingly

## Performance Tuning

1. **Profile Count**: More profiles = better distribution
2. **Daily Limits**: Adjust `max_daily_usage` based on your needs
3. **Random Delays**: Built-in random delays help avoid detection
4. **Concurrent Extraction**: Limit concurrent AdsPower sessions

## Scaling

To scale beyond 10 profiles:

1. **Add more profiles** to `adspower_config.json`
2. **Increase Docker resources** for the scraper service
3. **Monitor host system resources** (AdsPower can be resource-intensive)
4. **Consider profile cleanup** (stop unused profiles to free resources)

---

## Quick Start Checklist

- [ ] AdsPower installed and running
- [ ] 2+ AdsPower profiles created  
- [ ] Profile IDs noted from AdsPower interface
- [ ] `adspower_config.json` updated with real profile IDs
- [ ] OLX accounts created (optional)
- [ ] Docker services rebuilt and restarted
- [ ] Configuration copied to container
- [ ] Test script executed successfully
- [ ] Phone extraction tested with real URL

Once all items are checked, the AdsPower integration is ready for production use! 