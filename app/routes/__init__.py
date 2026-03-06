"""Routes package - Register blueprints here"""
from .api import api_bp
from .proxy import proxy_bp
from .static import static_bp

__all__ = ['static_bp', 'proxy_bp', 'api_bp']
