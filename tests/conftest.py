import os

# `specific exec cli` injects SUTH_API_TOKEN for the demo scripts. suth.api.app
# reads it once at import, so drop it before any test imports the app — the
# auth middleware itself is covered against a stand-in app in test_api_auth.py.
os.environ.pop("SUTH_API_TOKEN", None)
