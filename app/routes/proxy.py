"""Proxy routes for images and streams"""
import logging
import re
import urllib.parse

import requests
from flask import Blueprint, Response, request

from app.utils import encode_url
from app.utils.streaming import generate_streaming_response, stream_request

logger = logging.getLogger(__name__)

proxy_bp = Blueprint('proxy', __name__)


def _proxied_stream_url(original_url):
    base = request.host_url.rstrip("/")
    return f"{base}/stream-proxy/{encode_url(original_url)}"


def _stream_proxy_candidates(original_url):
    """Return ordered upstream URL candidates for resilient playback."""
    base = str(original_url or "").strip()
    if not base:
        return []

    candidates = [base]
    try:
        parsed = urllib.parse.urlparse(base)
        scheme = (parsed.scheme or "").lower()
        if scheme not in {"http", "https"}:
            return candidates

        port = parsed.port
        if port is None:
            return candidates

        # Some providers report conflicting scheme/port combinations.
        if scheme == "https" and port == 80:
            candidates.append(parsed._replace(scheme="http").geturl())
        elif scheme == "http" and port == 443:
            candidates.append(parsed._replace(scheme="https").geturl())
    except Exception:
        return candidates

    deduped = []
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def _rewrite_hls_manifest(manifest_text, source_url):
    """Rewrite HLS manifest URIs so segment/key requests stay within this app proxy."""
    if not manifest_text:
        return manifest_text

    def to_absolute(uri):
        raw = str(uri or "").strip()
        if not raw:
            return raw
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw
        return urllib.parse.urljoin(source_url, raw)

    def rewrite_attr_uri(match):
        original = match.group(1)
        absolute = to_absolute(original)
        return f'URI="{_proxied_stream_url(absolute)}"'

    rewritten_lines = []
    for raw_line in manifest_text.splitlines():
        line = raw_line.rstrip("\r")
        stripped = line.strip()
        if not stripped:
            rewritten_lines.append(line)
            continue

        if stripped.startswith("#"):
            # Rewrite URI attributes in tags like EXT-X-KEY / EXT-X-MAP.
            line = re.sub(r'URI="([^"]+)"', rewrite_attr_uri, line)
            rewritten_lines.append(line)
            continue

        absolute = to_absolute(stripped)
        rewritten_lines.append(_proxied_stream_url(absolute))

    return "\n".join(rewritten_lines) + ("\n" if manifest_text.endswith("\n") else "")


@proxy_bp.route("/image-proxy/<path:image_url>")
def proxy_image(image_url):
    """Proxy endpoint for images to avoid CORS issues"""
    try:
        original_url = urllib.parse.unquote(image_url)
        logger.info(f"Image proxy request for: {original_url}")

        response = requests.get(original_url, stream=True, timeout=10)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")

        if not content_type.startswith("image/"):
            logger.error(f"Invalid content type for image: {content_type}")
            return Response("Invalid image type", status=415)

        return generate_streaming_response(response, content_type)
    except requests.Timeout:
        return Response("Image fetch timeout", status=504)
    except requests.HTTPError as e:
        return Response(f"Failed to fetch image: {str(e)}", status=e.response.status_code)
    except Exception as e:
        logger.error(f"Image proxy error: {str(e)}")
        return Response("Failed to process image", status=500)


@proxy_bp.route("/stream-proxy/<path:stream_url>")
def proxy_stream(stream_url):
    """Proxy endpoint for streams"""
    try:
        original_url = urllib.parse.unquote(stream_url)
        logger.info(f"Stream proxy request for: {original_url}")

        response = None
        selected_url = original_url
        attempts = _stream_proxy_candidates(original_url)
        last_error = None

        for candidate in attempts:
            selected_url = candidate
            try:
                response = stream_request(candidate, timeout=60)  # Longer timeout for live streams
                response.raise_for_status()
                break
            except (
                requests.exceptions.Timeout,
                requests.exceptions.HTTPError,
                requests.exceptions.RequestException,
            ) as exc:
                last_error = exc
                logger.warning(f"Stream proxy candidate failed: {candidate} ({type(exc).__name__}: {exc})")
                response = None

        if response is None:
            if isinstance(last_error, requests.exceptions.Timeout):
                return Response("Stream timeout", status=504)
            if isinstance(last_error, requests.exceptions.HTTPError) and getattr(last_error, "response", None) is not None:
                status = last_error.response.status_code
                return Response(f"Failed to fetch stream: {str(last_error)}", status=status)
            if isinstance(last_error, requests.exceptions.SSLError):
                return Response("TLS failure connecting to upstream stream", status=502)
            if isinstance(last_error, requests.exceptions.RequestException):
                return Response("Failed to fetch stream from upstream provider", status=502)
            return Response("Failed to process stream", status=500)

        # Determine content type
        content_type = response.headers.get("Content-Type")
        if not content_type:
            if selected_url.endswith(".ts"):
                content_type = "video/MP2T"
            elif selected_url.endswith(".m3u8"):
                content_type = "application/vnd.apple.mpegurl"
            else:
                content_type = "application/octet-stream"

        # Rewrite HLS manifests so subsequent segment/key requests stay in /stream-proxy.
        is_hls = (
            selected_url.endswith(".m3u8")
            or "mpegurl" in content_type.lower()
            or "m3u8" in content_type.lower()
        )
        if is_hls:
            rewritten = _rewrite_hls_manifest(response.text, response.url or selected_url)
            return Response(rewritten, status=200, mimetype=content_type)

        logger.info(f"Using content type: {content_type}")
        return generate_streaming_response(response, content_type)
    except requests.exceptions.Timeout:
        logger.error(f"Timeout connecting to stream: {original_url}")
        return Response("Stream timeout", status=504)
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error fetching stream: {e.response.status_code} - {original_url}")
        return Response(f"Failed to fetch stream: {str(e)}", status=e.response.status_code)
    except Exception as e:
        logger.error(f"Stream proxy error: {str(e)} - {original_url}")
        return Response("Failed to process stream", status=500)
