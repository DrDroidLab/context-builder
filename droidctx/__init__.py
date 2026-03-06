"""droidctx - Infrastructure context builder for coding agents."""

__version__ = "0.1.0"


def _detect_local_version() -> str:
    """Append '+local' suffix when running from an editable (local) install."""
    try:
        from importlib.metadata import distribution
        dist = distribution("droidctx")
        # Editable installs use a direct_url.json with "dir_info"
        direct_url = dist.read_text("direct_url.json")
        if direct_url and "dir_info" in direct_url:
            return __version__ + "+local"
    except Exception:
        pass
    return __version__


__resolved_version__ = _detect_local_version()
