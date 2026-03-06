"""Flask application factory and configuration"""
import ipaddress
import logging
import os
import secrets
from pathlib import Path

from flask import Flask, redirect, request
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _load_app_version():
    """Resolve app version from VERSION file."""
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


def _env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _is_local_host(host):
    if not host:
        return False
    host_value = str(host).strip()
    if host_value.startswith("[") and "]" in host_value:
        host_value = host_value[1:host_value.index("]")]
    else:
        host_value = host_value.split(":", 1)[0]

    if host_value.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host_value).is_loopback
    except ValueError:
        return False


def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__,
                static_folder='../frontend',
                template_folder='../frontend')
    app.config['SECRET_KEY'] = _load_or_create_secret_key()
    app.config['APP_VERSION'] = _load_app_version()
    app.config['FORCE_SSL_REMOTE'] = _env_bool("FORCE_SSL_REMOTE", True)

    if _env_bool("TRUST_PROXY_HEADERS", True):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    @app.before_request
    def enforce_ssl_for_remote_clients():
        """Redirect non-local HTTP requests to HTTPS."""
        if not app.config.get('FORCE_SSL_REMOTE'):
            return None
        if request.is_secure:
            return None
        if _is_local_host(request.host):
            return None
        target = request.url.replace("http://", "https://", 1)
        return redirect(target, code=301)

    # Register blueprints
    from app.routes.api import api_bp
    from app.routes.proxy import proxy_bp
    from app.routes.static import static_bp

    app.register_blueprint(static_bp)
    app.register_blueprint(proxy_bp)
    app.register_blueprint(api_bp)

    logger.info("Flask application created and configured")

    return app
