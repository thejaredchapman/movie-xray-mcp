# Set env vars before server.py is imported during test collection.
import os

os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key")
os.environ.setdefault("OMDB_API_KEY", "test_omdb_key")
os.environ.setdefault("DEFAULT_REGION", "US")
