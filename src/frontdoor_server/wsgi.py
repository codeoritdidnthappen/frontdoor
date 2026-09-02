"""WSGI entrypoint for the container (TICK-062)."""

from frontdoor_server.app import create_app

app = create_app()
