"""Flask application factory and configuration"""
import logging
import os
import secrets
from pathlib import Path

from flask import Flask

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _load_app_version():
    """Resolve app version from env or VERSION file."""
    env_version = str(os.environ.get("APP_VERSION", "")).strip()
    if env_version:
        return env_version

    version_file = Path(os.environ.get("APP_VERSION_FILE", "/app/VERSION"))
    try:
        if version_file.exists():
            value = version_file.read_text(encoding="utf-8").strip()
            if value:
                return value
    except Exception as error:
        logger.warning("Failed reading app version file %s: %s", version_file, error)

    return "0.0.0-dev"


def _load_or_create_secret_key():
    """Return stable Flask secret key across workers/restarts."""
    env_secret = os.environ.get("FLASK_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if env_secret:
        return env_secret

    secret_file = Path(os.environ.get("FLASK_SECRET_FILE", "/data/flask_secret_key"))
    try:
        if secret_file.exists():
            value = secret_file.read_text(encoding="utf-8").strip()
            if value:
                return value
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        value = secrets.token_hex(32)
        secret_file.write_text(value, encoding="utf-8")
        return value
    except Exception as error:
        logger.warning("Failed to persist Flask secret key at %s: %s", secret_file, error)
        return secrets.token_hex(32)


def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__,
                static_folder='../frontend',
                template_folder='../frontend')
    app.config['SECRET_KEY'] = _load_or_create_secret_key()
    app.config['APP_VERSION'] = _load_app_version()

    # Get default proxy URL from environment variable
    app.config['DEFAULT_PROXY_URL'] = os.environ.get("PROXY_URL")

    # Register blueprints
    from app.routes.api import api_bp
    from app.routes.proxy import proxy_bp
    from app.routes.static import static_bp

    app.register_blueprint(static_bp)
    app.register_blueprint(proxy_bp)
    app.register_blueprint(api_bp)

    logger.info("Flask application created and configured")

    return app
