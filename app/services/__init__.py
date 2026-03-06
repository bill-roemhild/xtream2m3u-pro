"""Services package"""
from .m3u_generator import generate_m3u_playlist
from .xtream_api import (
    build_stream_link_candidates,
    build_stream_link,
    fetch_catalog,
    fetch_api_data,
    fetch_categories_and_channels,
    fetch_full_epg,
    fetch_series_episodes,
    fetch_series_info,
    fetch_short_epg,
    fetch_vod_info,
    normalize_server_info,
    normalize_user_info,
    validate_xtream_credentials,
)

__all__ = [
    'fetch_api_data',
    'validate_xtream_credentials',
    'fetch_categories_and_channels',
    'fetch_series_episodes',
    'generate_m3u_playlist',
    'fetch_short_epg',
    'fetch_full_epg',
    'fetch_vod_info',
    'fetch_series_info',
    'fetch_catalog',
    'build_stream_link_candidates',
    'build_stream_link',
    'normalize_user_info',
    'normalize_server_info',
]
