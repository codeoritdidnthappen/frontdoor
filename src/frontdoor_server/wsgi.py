"""WSGI entrypoint for the container (TICK-062)."""

from frontdoor.storage import load_local_env
from frontdoor_server.app import create_app

# Before the app is built, because the views read the environment as they go: /screen wants
# ANTHROPIC_API_KEY, /upload wants FRONTDOOR_UPLOAD_KEY and the bucket credentials.
#
# Here rather than inside create_app() on purpose. create_app() is what the test suite calls,
# and several tests delete a variable to assert the keyless behaviour -- loading .env in there
# would hand the key back and make those tests pass or fail depending on whether the developer
# happens to have a .env, which is worse than the bug it fixes.
#
# Real environment variables still win (override=False), so the container, where Fly injects
# secrets and no .env exists, is unaffected.
load_local_env()

app = create_app()
