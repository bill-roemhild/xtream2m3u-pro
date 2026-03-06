"""Xtream2M3U - Xtream Codes API to M3U converter

This is the main entry point for the application.
Run with: python run.py [--port PORT]
"""
import argparse
import logging

from app import create_app
from app.utils import setup_custom_dns

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize custom DNS resolver globally so it runs for Gunicorn too
setup_custom_dns()

# Create the Flask app globally so Gunicorn can find 'app'
app = create_app()


def main():
    """Main entry point for the application"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run the Xtream2M3U Flask app.")
    parser.add_argument(
        "--port", type=int, default=5000, help="Port number to run the app on (default: 5000)"
    )
    args = parser.parse_args()

    # Run the app
    logger.info(f"Starting Xtream2M3U server on port {args.port}")
    app.run(debug=True, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
