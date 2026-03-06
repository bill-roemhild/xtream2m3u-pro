"""Streaming and proxy utilities"""
import logging

import requests
from flask import Response

logger = logging.getLogger(__name__)


def stream_request(url, headers=None, timeout=30):
    """Make a streaming request that doesn't buffer the full response"""
    if not headers:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Connection": "keep-alive",
        }

    # Use longer timeout for streams and set both connect and read timeouts
    return requests.get(url, stream=True, headers=headers, timeout=(10, timeout))


def generate_streaming_response(response, content_type=None):
    """Generate a streaming response with appropriate headers"""
    if not content_type:
        content_type = response.headers.get("Content-Type", "application/octet-stream")

    def generate():
        try:
            bytes_sent = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    bytes_sent += len(chunk)
                    yield chunk
            logger.info(f"Stream completed, sent {bytes_sent} bytes")
        except requests.exceptions.ChunkedEncodingError as e:
            # Chunked encoding error from upstream - log and stop gracefully
            logger.warning(f"Upstream chunked encoding error after {bytes_sent} bytes: {str(e)}")
            # Don't raise - just stop yielding to close stream gracefully
        except requests.exceptions.ConnectionError as e:
            # Connection error (reset, timeout, etc.) - log and stop gracefully
            logger.warning(f"Connection error after {bytes_sent} bytes: {str(e)}")
            # Don't raise - just stop yielding to close stream gracefully
        except Exception as e:
            logger.error(f"Streaming error after {bytes_sent} bytes: {str(e)}")
            # Don't raise exceptions in generators after headers are sent!
            # Raising here causes Flask to inject "HTTP/1.1 500" into the chunked body,
        finally:
            # Always close the upstream response to free resources
            try:
                response.close()
            except:
                pass

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": content_type,
    }

    # Add content length if available and not using chunked transfer
    if "Content-Length" in response.headers and "Transfer-Encoding" not in response.headers:
        headers["Content-Length"] = response.headers["Content-Length"]
    else:
        headers["Transfer-Encoding"] = "chunked"

    return Response(generate(), mimetype=content_type, headers=headers, direct_passthrough=True)
