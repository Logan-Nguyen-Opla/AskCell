"""
build_reference_cache.py
=========================
Fit and cache the healthy cytometry reference at *build* time, not startup.

Fitting a reference this size is expensive enough that doing it inside the
app's startup hook risks exceeding a host's port-bind timeout -- which is
exactly what happened on Render's free tier: the app never got as far as
opening a port before the platform gave up and marked the deploy "Timed Out".

Running the same fit here, during the build step (which gets a much more
generous time budget than container startup), means a fitted reference.npz
already exists on disk by the time the container starts. Startup then just
loads that cache file -- a fraction of a second -- instead of refitting from
scratch on every cold start.

This reuses app.main._autoload_reference() itself rather than duplicating its
logic, so there is exactly one place that knows how the reference is built
and cached.
"""

from app.main import _autoload_reference

if __name__ == "__main__":
    _autoload_reference()
