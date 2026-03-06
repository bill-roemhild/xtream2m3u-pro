"""Proxy routes for images and streams"""
import logging
import urllib.parse
import json
import os
from pathlib import Path

import requests
from flask import Blueprint, Response, jsonify, request, session

from app.utils.streaming import generate_streaming_response, stream_request

logger = logging.getLogger(__name__)

proxy_bp = Blueprint('proxy', __name__)
AUTH_STORE_PATH = Path(os.environ.get("AUTH_STORE_PATH", "/data/auth_users.json"))


def _has_users():
    try:
        if not AUTH_STORE_PATH.exists():
            return False
        raw = json.loads(AUTH_STORE_PATH.read_text(encoding="utf-8"))
        return isinstance(raw, dict) and isinstance(raw.get("users"), list) and len(raw.get("users", [])) > 0
    except Exception:
        return False


@proxy_bp.before_request
def require_authentication():
    if request.method == "OPTIONS":
        return None
    if not _has_users():
        return jsonify({"error": "Setup Required", "details": "Create the first admin account first"}), 403
    if not (bool(session.get("authenticated")) and bool(session.get("username"))):
        return jsonify({"error": "Unauthorized", "details": "Login required"}), 401
    return None


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

        response = stream_request(original_url, timeout=60)  # Longer timeout for live streams
        response.raise_for_status()

        # Determine content type
        content_type = response.headers.get("Content-Type")
        if not content_type:
            if original_url.endswith(".ts"):
                content_type = "video/MP2T"
            elif original_url.endswith(".m3u8"):
                content_type = "application/vnd.apple.mpegurl"
            else:
                content_type = "application/octet-stream"

        logger.info(f"Using content type: {content_type}")
        return generate_streaming_response(response, content_type)
    except requests.Timeout:
        logger.error(f"Timeout connecting to stream: {original_url}")
        return Response("Stream timeout", status=504)
    except requests.HTTPError as e:
        logger.error(f"HTTP error fetching stream: {e.response.status_code} - {original_url}")
        return Response(f"Failed to fetch stream: {str(e)}", status=e.response.status_code)
    except Exception as e:
        logger.error(f"Stream proxy error: {str(e)} - {original_url}")
        return Response("Failed to process stream", status=500)
