"""
Main interface for phone number extraction. Orchestrates domain-specific parsers and manages proxies.
"""

import asyncio
from typing import Optional
from common.utils import logger
from common.utils.logging_config import log_operation, log_context, LogAggregator
from common.utils.phone_utils import proxy_manager
from common.utils.phone_utils.http_client import AsyncHTTPClient, REQUEST_TIMEOUT
from common.utils.phone_utils.phone_models import ExtractionResult
from common.utils.phone_utils.parsers import (
    olx_parser,
    domria_parser,
    realestate_parser,
    rieltor_parser,
    lun_parser,
    faktor24_parser,
    fallback_parser,
)


@log_operation("extract_phone_numbers_async")
async def _extract_phone_numbers_async(
    resource_url: str, proxy: Optional[str] = None
) -> ExtractionResult:
    """
    Asynchronously extract phone numbers (and optionally a Viber link) from the given resource URL.
    If `proxy` is not provided, the system will automatically use a random proxy if available.
    """
    aggregator = LogAggregator(logger, f"extract_phone_numbers_async_{resource_url}")
    # Determine whether a proxy was explicitly provided
    user_specified_proxy = proxy is not None
    try:
        with log_context(logger, resource_url=resource_url):
            # If no proxy explicitly provided, attempt to use one from the proxy pool
            if proxy is None:
                proxy = proxy_manager.get_random_proxy()
            used_proxy = proxy is not None

            # ------------------------------------------------------------------
            # Handle Flatfy redirect links using extraction client
            # ------------------------------------------------------------------
            if "flatfy.ua/uk/redirect" in resource_url:
                logger.info(
                    "Flatfy redirect detected – resolving via extraction client"
                )

                try:
                    from common.utils.extraction_client import extraction_client

                    # Use extraction client to get the page content
                    result = await extraction_client.extract_content_async(
                        url=resource_url,
                        proxy=proxy,
                        timeout=REQUEST_TIMEOUT,
                        wait_after_load=3000,
                    )

                    if result["status"] == "success":
                        final_url = result.get("final_url", resource_url)

                        logger.info(
                            "Flatfy redirect resolved",
                            extra={
                                "initial_url": resource_url,
                                "redirected_url": final_url,
                                "service_used": result.get("service_used"),
                            },
                        )

                        if final_url and final_url != resource_url:
                            # Recursively call the extractor for the redirected URL
                            return await _extract_phone_numbers_async(
                                final_url, proxy=proxy
                            )
                        else:
                            logger.warning(
                                "Flatfy redirect did not change URL – aborting extraction"
                            )
                            aggregator.add_error(
                                "flatfy_redirect_failed", {"url": resource_url}
                            )
                            return ExtractionResult([], None)
                    else:
                        logger.error(
                            "Extraction service failed to resolve Flatfy redirect",
                            extra={
                                "resource_url": resource_url,
                                "error": result.get("error"),
                                "service_used": result.get("service_used"),
                            },
                        )
                        aggregator.add_error(
                            "extraction_service_error", {"error": result.get("error")}
                        )
                        return ExtractionResult([], None)

                except Exception as e:
                    logger.error(
                        "Flatfy redirect resolution failed",
                        exc_info=True,
                        extra={
                            "resource_url": resource_url,
                            "error_type": type(e).__name__,
                        },
                    )
                    aggregator.add_error("flatfy_extraction_error", {"error": str(e)})
                    return ExtractionResult([], None)

            # Special-case domains that require full browser simulation
            if "olx.ua" in resource_url:
                logger.info("OLX domain detected – using smart extraction method selection")
                
                # First check if login is required for this ad
                login_required = await olx_parser.check_olx_login_required(resource_url, proxy=proxy)
                
                if login_required:
                    logger.info("Login required detected – using AdsPower profiles directly")
                    result = await olx_parser.parse_olx_adspower(resource_url)
                    
                    if result.phone_numbers:
                        aggregator.add_item({"method": "adspower_direct"}, success=True)
                    else:
                        aggregator.add_item({"method": "adspower_direct"}, success=False)
                else:
                    logger.info("No login required – trying Camoufox first")
                    # Try Camoufox first since no login is needed
                    result = await olx_parser.parse_olx_camoufox(resource_url, proxy=proxy)
                    
                    if result.phone_numbers:
                        aggregator.add_item({"method": "camoufox_direct"}, success=True)
                    else:
                        # Camoufox failed, try AdsPower as final fallback
                        logger.info("Camoufox failed despite no login requirement – trying AdsPower as fallback")
                        result = await olx_parser.parse_olx_adspower(resource_url)
                        
                        if result.phone_numbers:
                            aggregator.add_item({"method": "adspower_fallback"}, success=True)
                        else:
                            aggregator.add_item({"method": "adspower_fallback"}, success=False)
                            aggregator.add_item({"method": "camoufox_direct"}, success=False)
                
                return result
            if "dom.ria" in resource_url or "dom.ria.com" in resource_url:
                logger.info("DOM.RIA domain detected – using specialized parser")
                # Use domain-specific parser (which internally uses Camoufox if needed)
                result = await domria_parser.parse_domria_page(
                    resource_url, AsyncHTTPClient(proxy=proxy)
                )
                if result.phone_numbers:
                    aggregator.add_item({"method": "camoufox_direct"}, success=True)
                else:
                    aggregator.add_item({"method": "camoufox_direct"}, success=False)
                return result
            # Create HTTP client for fetching page content
            client = AsyncHTTPClient(proxy=proxy)
            html_content: Optional[str] = None
            try:
                html_content = await client.fetch(resource_url)
            except Exception as e:
                logger.error(f"Failed to fetch {resource_url}: {e}")
                aggregator.add_error("fetch_failed", {"error": str(e)})
                # If initial fetch failed, attempt a retry with a different proxy (only if proxy was not user-specified)
                if not user_specified_proxy and proxy_manager.proxies_available():
                    new_proxy = proxy_manager.get_random_proxy()
                    if new_proxy and (proxy is None or new_proxy != proxy):
                        logger.info(f"Retrying fetch with a new proxy: {new_proxy}")
                        client = AsyncHTTPClient(proxy=new_proxy)
                        try:
                            html_content = await client.fetch(resource_url)
                        except Exception as e2:
                            logger.error(f"Retry fetch failed: {e2}")
                            aggregator.add_error(
                                "fetch_failed_retry", {"error": str(e2)}
                            )
                            return ExtractionResult([], None)
                    else:
                        return ExtractionResult([], None)
                else:
                    return ExtractionResult([], None)
            # If the page is an intermediate redirection page (e.g., flatfy.ua), follow the redirect once
            try:
                if html_content and "Перенаправлення" in html_content:
                    logger.info("Detected intermediate redirection page")
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(html_content, "html.parser")
                    redirect_tag = soup.select_one("a.redirect-link[href]")
                    if redirect_tag and redirect_tag.get("href"):
                        redirect_url = redirect_tag.get("href")
                        # Normalize the redirect URL in case it's relative
                        import urllib.parse

                        redirect_url = urllib.parse.urljoin(resource_url, redirect_url)
                        logger.info(f"Following redirect to {redirect_url}")
                        redirected_html = await client.fetch(redirect_url)
                        if redirected_html:
                            html_content = redirected_html
                            resource_url = redirect_url
            except Exception as e:
                logger.warning(f"Redirect handling failed: {e}")
            # Determine the content's effective domain and route to the appropriate parser
            result: ExtractionResult
            if "real-estate.lviv.ua" in resource_url:
                result = await realestate_parser.parse_real_estate_lviv(
                    resource_url, client
                )
            elif "rieltor.ua" in resource_url:
                result = rieltor_parser.parse_rieltor_page(html_content or "")
            elif "lun.ua" in resource_url:
                result = lun_parser.parse_lun_page(html_content or "")
            elif "faktor24.com" in resource_url:
                result = faktor24_parser.parse_faktor24_page(html_content or "")
            else:
                if html_content is None:
                    result = ExtractionResult([], None)
                else:
                    logger.warning(
                        f"Unknown domain for {resource_url} – using fallback parser"
                    )
                    result = fallback_parser.fallback_parse(html_content)
            # Log the final method used (proxy or no-proxy) as a successful operation
            method_label = "proxy" if used_proxy else "no-proxy"
            aggregator.add_item({"method": method_label}, success=True)
            return result
    except Exception as e:
        # Catch-all for any exception in extraction process
        logger.warning(
            "Extraction failed",
            extra={"resource_url": resource_url, "error_type": type(e).__name__},
        )
        aggregator.add_error("extraction_failed", {"error": str(e)})
        return ExtractionResult([], None)
    finally:
        # Summarize the logging for this operation
        aggregator.log_summary()


@log_operation("extract_phone_numbers_from_resource")
def extract_phone_numbers_from_resource(
    resource_url: str, proxy: Optional[str] = None
) -> ExtractionResult:
    """
    Synchronously extract phone numbers (and a Viber link, if present) from the given resource URL.
    This function wraps the asynchronous extraction logic for usage in synchronous contexts.
    """
    with log_context(logger, resource_url=resource_url):
        logger.info("Starting phone number extraction", extra={"url": resource_url})
        try:
            # If already in an event loop, run asynchronously; otherwise create a new event loop.
            try:
                loop = asyncio.get_running_loop()
                future = asyncio.run_coroutine_threadsafe(
                    _extract_phone_numbers_async(resource_url, proxy=proxy), loop
                )
                result = future.result()
            except RuntimeError:
                result = asyncio.run(
                    _extract_phone_numbers_async(resource_url, proxy=proxy)
                )
            logger.info(
                "Phone extraction completed",
                extra={
                    "resource_url": resource_url,
                    "phone_count": len(result.phone_numbers),
                    "has_viber": bool(result.viber_link),
                },
            )
            return result
        except Exception as e:
            logger.exception(
                "Phone extraction failed",
                extra={"resource_url": resource_url, "error_type": type(e).__name__},
            )
            return ExtractionResult([], None)
