"""FastMCP server exposing Amazon Prime "X-Ray"-style movie/TV tools.

Look up a title, browse its cast, drill into an actor's bio and
filmography, cross-reference that filmography against what's currently
streaming on Netflix, and link out to IMDb.

Data sources:
- TMDb (themoviedb.org) — search, cast/crew, filmographies, IMDb ID
  resolution, and watch/providers (JustWatch-sourced streaming availability).
- OMDb (omdbapi.com) — IMDb/Rotten Tomatoes/Metacritic ratings and plot,
  keyed off the IMDb ID TMDb provides. Optional — omitted if OMDB_API_KEY
  is not set.
"""

import os
import sys
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

TMDB_API_KEY = os.environ["TMDB_API_KEY"]
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")
DEFAULT_REGION = os.environ.get("DEFAULT_REGION", "US")

TMDB_BASE = "https://api.themoviedb.org/3"
OMDB_BASE = "https://www.omdbapi.com/"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

mcp = FastMCP("movie-xray-mcp")


def _tmdb_get(path: str, **params) -> Optional[dict]:
    params["api_key"] = TMDB_API_KEY
    resp = httpx.get(f"{TMDB_BASE}{path}", params=params, timeout=10)
    if resp.status_code == 401:
        raise RuntimeError("TMDb rejected the request — check TMDB_API_KEY in .env.")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _omdb_get(**params) -> Optional[dict]:
    if not OMDB_API_KEY:
        return None
    params["apikey"] = OMDB_API_KEY
    try:
        resp = httpx.get(OMDB_BASE, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError:
        return None
    if data.get("Response") == "False":
        return None
    return data


def _image_url(path: Optional[str]) -> Optional[str]:
    return f"{IMAGE_BASE}{path}" if path else None


def _imdb_title_url(imdb_id: Optional[str]) -> Optional[str]:
    return f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else None


def _imdb_person_url(imdb_id: Optional[str]) -> Optional[str]:
    return f"https://www.imdb.com/name/{imdb_id}/" if imdb_id else None


def _resolve_person_id(person: str) -> Optional[int]:
    person = person.strip()
    if person.isdigit():
        return int(person)
    data = _tmdb_get("/search/person", query=person)
    results = (data or {}).get("results", [])
    return results[0]["id"] if results else None


def _get_watch_providers(tmdb_id: int, media_type: str, region: str) -> dict:
    data = _tmdb_get(f"/{media_type}/{tmdb_id}/watch/providers")
    region_data = (data or {}).get("results", {}).get(region.upper(), {})
    flatrate = [p["provider_name"] for p in region_data.get("flatrate", [])]
    return {
        "region": region.upper(),
        "flatrate": flatrate,
        "rent": [p["provider_name"] for p in region_data.get("rent", [])],
        "buy": [p["provider_name"] for p in region_data.get("buy", [])],
        "ads": [p["provider_name"] for p in region_data.get("ads", [])],
        "netflix_available": "Netflix" in flatrate,
    }


@mcp.tool()
def search_title(
    query: str,
    media_type: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 10,
) -> dict:
    """Search for a movie or TV show by name.

    Args:
        query: Title to search for.
        media_type: "movie", "tv", or omit to search both.
        year: Restrict results to this release year (movies) or first-air year (TV).
        limit: Maximum number of results to return (1-20).
    """
    limit = max(1, min(limit, 20))

    if media_type in ("movie", "tv"):
        params = {"query": query}
        if year:
            params["year" if media_type == "movie" else "first_air_date_year"] = year
        data = _tmdb_get(f"/search/{media_type}", **params)
        items = [{**item, "media_type": media_type} for item in (data or {}).get("results", [])]
    else:
        data = _tmdb_get("/search/multi", query=query)
        items = [i for i in (data or {}).get("results", []) if i.get("media_type") in ("movie", "tv")]

    results = []
    for item in items[:limit]:
        results.append(
            {
                "tmdb_id": item["id"],
                "media_type": item.get("media_type", media_type),
                "title": item.get("title") or item.get("name"),
                "release_date": item.get("release_date") or item.get("first_air_date"),
                "overview": item.get("overview"),
                "popularity": item.get("popularity"),
                "poster_url": _image_url(item.get("poster_path")),
            }
        )

    return {"query": query, "count": len(results), "results": results}


@mcp.tool()
def get_title_details(tmdb_id: int, media_type: str, region: Optional[str] = None) -> dict:
    """Get full details for a movie or TV show: synopsis, cast, ratings, IMDb link,
    and where it's currently streaming (including whether it's on Netflix).

    Args:
        tmdb_id: The TMDb ID of the title (from search_title).
        media_type: "movie" or "tv".
        region: ISO 3166-1 country code for streaming availability (default: DEFAULT_REGION env var, or "US").
    """
    if media_type not in ("movie", "tv"):
        return {"error": "media_type must be 'movie' or 'tv'"}

    region = (region or DEFAULT_REGION).upper()

    data = _tmdb_get(f"/{media_type}/{tmdb_id}", append_to_response="credits,external_ids")
    if data is None:
        return {"error": f"No {media_type} found with id {tmdb_id}"}

    runtime = data.get("runtime")
    if runtime is None:
        episode_runtimes = data.get("episode_run_time") or []
        runtime = episode_runtimes[0] if episode_runtimes else None

    imdb_id = (data.get("external_ids") or {}).get("imdb_id")

    cast = [
        {
            "name": member["name"],
            "character": member.get("character"),
            "person_id": member["id"],
            "profile_url": _image_url(member.get("profile_path")),
        }
        for member in (data.get("credits") or {}).get("cast", [])[:10]
    ]

    result: dict = {
        "tmdb_id": tmdb_id,
        "media_type": media_type,
        "title": data.get("title") or data.get("name"),
        "overview": data.get("overview"),
        "release_date": data.get("release_date") or data.get("first_air_date"),
        "runtime_minutes": runtime,
        "genres": [g["name"] for g in data.get("genres", [])],
        "tmdb_rating": data.get("vote_average"),
        "popularity": data.get("popularity"),
        "poster_url": _image_url(data.get("poster_path")),
        "imdb_url": _imdb_title_url(imdb_id),
        "cast": cast,
        "watch_providers": _get_watch_providers(tmdb_id, media_type, region),
    }

    if imdb_id:
        omdb = _omdb_get(i=imdb_id)
        if omdb:
            rt_rating = next(
                (r["Value"] for r in omdb.get("Ratings", []) if r["Source"] == "Rotten Tomatoes"),
                None,
            )
            result["ratings"] = {
                "imdb_rating": omdb.get("imdbRating"),
                "rotten_tomatoes": rt_rating,
                "metascore": omdb.get("Metascore"),
                "rated": omdb.get("Rated"),
                "awards": omdb.get("Awards"),
                "plot": omdb.get("Plot"),
            }

    return result


@mcp.tool()
def get_actor_info(person: str) -> dict:
    """Get an actor's bio, photo, and IMDb link.

    Args:
        person: A TMDb person ID, or an actor's name to search for.
    """
    person_id = _resolve_person_id(person)
    if person_id is None:
        return {"error": f"No person found for: {person!r}"}

    data = _tmdb_get(f"/person/{person_id}", append_to_response="external_ids")
    if data is None:
        return {"error": f"No person found with id {person_id}"}

    imdb_id = (data.get("external_ids") or {}).get("imdb_id")

    return {
        "person_id": person_id,
        "name": data.get("name"),
        "biography": data.get("biography"),
        "birthday": data.get("birthday"),
        "place_of_birth": data.get("place_of_birth"),
        "known_for_department": data.get("known_for_department"),
        "popularity": data.get("popularity"),
        "profile_url": _image_url(data.get("profile_path")),
        "imdb_url": _imdb_person_url(imdb_id),
    }


@mcp.tool()
def get_actor_filmography(person: str, media_type: Optional[str] = None, limit: int = 25) -> dict:
    """Get an actor's filmography, sorted by popularity.

    Args:
        person: A TMDb person ID, or an actor's name to search for.
        media_type: "movie", "tv", or omit for both.
        limit: Maximum number of credits to return (1-100).
    """
    person_id = _resolve_person_id(person)
    if person_id is None:
        return {"error": f"No person found for: {person!r}"}

    limit = max(1, min(limit, 100))

    data = _tmdb_get(f"/person/{person_id}/combined_credits")
    credits = (data or {}).get("cast", [])

    if media_type in ("movie", "tv"):
        credits = [c for c in credits if c.get("media_type") == media_type]

    credits = sorted(credits, key=lambda c: c.get("popularity", 0), reverse=True)[:limit]

    filmography = [
        {
            "tmdb_id": c["id"],
            "media_type": c.get("media_type"),
            "title": c.get("title") or c.get("name"),
            "character": c.get("character"),
            "release_date": c.get("release_date") or c.get("first_air_date"),
            "popularity": c.get("popularity"),
        }
        for c in credits
    ]

    return {"person_id": person_id, "count": len(filmography), "filmography": filmography}


@mcp.tool()
def get_watch_providers(tmdb_id: int, media_type: str, region: Optional[str] = None) -> dict:
    """Get streaming/rental/purchase availability for a title, including whether
    it's on Netflix.

    Args:
        tmdb_id: The TMDb ID of the title.
        media_type: "movie" or "tv".
        region: ISO 3166-1 country code (default: DEFAULT_REGION env var, or "US").
    """
    if media_type not in ("movie", "tv"):
        return {"error": "media_type must be 'movie' or 'tv'"}

    region = (region or DEFAULT_REGION).upper()
    return {
        "tmdb_id": tmdb_id,
        "media_type": media_type,
        **_get_watch_providers(tmdb_id, media_type, region),
    }


@mcp.tool()
def get_actor_netflix_titles(person: str, region: Optional[str] = None, top_n: int = 15) -> dict:
    """Find what's currently on Netflix from an actor's filmography (the
    "what else is this actor in" X-Ray feature).

    Checks the actor's most popular credits (up to top_n) against Netflix's
    catalog for the given region.

    Args:
        person: A TMDb person ID, or an actor's name to search for.
        region: ISO 3166-1 country code (default: DEFAULT_REGION env var, or "US").
        top_n: How many of the actor's most popular credits to check (1-50).
    """
    person_id = _resolve_person_id(person)
    if person_id is None:
        return {"error": f"No person found for: {person!r}"}

    region = (region or DEFAULT_REGION).upper()
    top_n = max(1, min(top_n, 50))

    data = _tmdb_get(f"/person/{person_id}/combined_credits")
    credits = (data or {}).get("cast", [])
    credits = [c for c in credits if c.get("media_type") in ("movie", "tv")]
    credits = sorted(credits, key=lambda c: c.get("popularity", 0), reverse=True)[:top_n]

    on_netflix = []
    for c in credits:
        media_type = c["media_type"]
        providers = _get_watch_providers(c["id"], media_type, region)
        if not providers["netflix_available"]:
            continue
        ext = _tmdb_get(f"/{media_type}/{c['id']}/external_ids") or {}
        on_netflix.append(
            {
                "tmdb_id": c["id"],
                "media_type": media_type,
                "title": c.get("title") or c.get("name"),
                "character": c.get("character"),
                "release_date": c.get("release_date") or c.get("first_air_date"),
                "imdb_url": _imdb_title_url(ext.get("imdb_id")),
                "tmdb_url": f"https://www.themoviedb.org/{media_type}/{c['id']}",
            }
        )

    return {
        "person_id": person_id,
        "region": region,
        "checked": len(credits),
        "on_netflix_count": len(on_netflix),
        "on_netflix": on_netflix,
    }


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "sse":
        port = int(os.environ.get("PORT", 8000))
        mcp.run(transport="sse", host="0.0.0.0", port=port)
    else:
        mcp.run()
