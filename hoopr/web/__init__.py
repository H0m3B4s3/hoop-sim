"""Web GUI layer: a FastAPI backend that wraps the existing engine in a JSON API.

This package is presentation only — like ``hoopr.ui`` it calls into ``sim``/``systems``/
``models`` but holds no game logic of its own. The engine and save format are untouched.
"""
