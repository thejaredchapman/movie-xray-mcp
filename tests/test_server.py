"""Tests for movie-xray-mcp server.py.

- Tool tests mock _tmdb_get / _omdb_get / _get_watch_providers at the module
  boundary so no real HTTP calls are made.
- HTTP-layer tests mock httpx.get directly to test _tmdb_get and _omdb_get
  themselves.

Run with:
    pip install -r requirements-dev.txt
    pytest tests/
"""

import pytest
from unittest.mock import MagicMock, patch, call
import httpx

import server


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_movie_data(
    tmdb_id=603,
    title="The Matrix",
    imdb_id="tt0133093",
    cast_count=2,
):
    cast = [
        {
            "id": 6193 + i,
            "name": f"Actor {i}",
            "character": f"Role {i}",
            "profile_path": f"/profile{i}.jpg",
        }
        for i in range(cast_count)
    ]
    return {
        "id": tmdb_id,
        "title": title,
        "overview": "A hacker discovers the truth.",
        "release_date": "1999-03-31",
        "runtime": 136,
        "episode_run_time": [],
        "genres": [{"name": "Action"}, {"name": "Sci-Fi"}],
        "vote_average": 8.7,
        "popularity": 100.0,
        "poster_path": "/matrix.jpg",
        "external_ids": {"imdb_id": imdb_id},
        "credits": {"cast": cast},
    }


def make_tv_data(tmdb_id=1396, name="Breaking Bad"):
    return {
        "id": tmdb_id,
        "name": name,
        "overview": "A teacher turns to crime.",
        "first_air_date": "2008-01-20",
        "runtime": None,
        "episode_run_time": [47],
        "genres": [{"name": "Drama"}],
        "vote_average": 9.5,
        "popularity": 200.0,
        "poster_path": "/bb.jpg",
        "external_ids": {"imdb_id": "tt0903747"},
        "credits": {"cast": []},
    }


def make_credit(id, title, media_type="movie", character="Character", popularity=50.0):
    credit = {
        "id": id,
        "media_type": media_type,
        "character": character,
        "popularity": popularity,
    }
    if media_type == "movie":
        credit["title"] = title
        credit["release_date"] = "2020-01-01"
    else:
        credit["name"] = title
        credit["first_air_date"] = "2020-01-01"
    return credit


def providers_response(region="US", flatrate=None, rent=None, buy=None, ads=None):
    """Build the dict returned by _get_watch_providers."""
    flatrate = flatrate or []
    return {
        "region": region,
        "flatrate": flatrate,
        "rent": rent or [],
        "buy": buy or [],
        "ads": ads or [],
        "netflix_available": "Netflix" in flatrate,
    }


def mock_http_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ---------------------------------------------------------------------------
# _image_url / _imdb_title_url / _imdb_person_url
# ---------------------------------------------------------------------------

def test_image_url_with_path():
    assert server._image_url("/poster.jpg") == "https://image.tmdb.org/t/p/w500/poster.jpg"


def test_image_url_none():
    assert server._image_url(None) is None


def test_image_url_empty_string():
    assert server._image_url("") is None


def test_imdb_title_url():
    assert server._imdb_title_url("tt1234567") == "https://www.imdb.com/title/tt1234567/"


def test_imdb_title_url_none():
    assert server._imdb_title_url(None) is None


def test_imdb_person_url():
    assert server._imdb_person_url("nm0000136") == "https://www.imdb.com/name/nm0000136/"


def test_imdb_person_url_none():
    assert server._imdb_person_url(None) is None


# ---------------------------------------------------------------------------
# _tmdb_get (tests the HTTP layer directly)
# ---------------------------------------------------------------------------

@patch("httpx.get")
def test_tmdb_get_success_returns_json(mock_get):
    mock_get.return_value = mock_http_response(200, {"results": [{"id": 1}]})

    result = server._tmdb_get("/search/movie", query="Matrix")

    assert result == {"results": [{"id": 1}]}
    call_kwargs = mock_get.call_args[1]
    assert call_kwargs["params"]["api_key"] == "test_tmdb_key"
    assert call_kwargs["params"]["query"] == "Matrix"


@patch("httpx.get")
def test_tmdb_get_404_returns_none(mock_get):
    mock_get.return_value = mock_http_response(404)
    assert server._tmdb_get("/movie/999999") is None


@patch("httpx.get")
def test_tmdb_get_401_raises_runtime_error(mock_get):
    mock_get.return_value = mock_http_response(401)
    with pytest.raises(RuntimeError, match="TMDb rejected"):
        server._tmdb_get("/movie/1")


@patch("httpx.get")
def test_tmdb_get_builds_correct_base_url(mock_get):
    mock_get.return_value = mock_http_response(200, {})
    server._tmdb_get("/person/6193")
    url = mock_get.call_args[0][0]
    assert url == "https://api.themoviedb.org/3/person/6193"


@patch("httpx.get")
def test_tmdb_get_injects_api_key(mock_get):
    mock_get.return_value = mock_http_response(200, {})
    server._tmdb_get("/movie/1")
    assert mock_get.call_args[1]["params"]["api_key"] == "test_tmdb_key"


# ---------------------------------------------------------------------------
# _omdb_get (tests the HTTP layer directly)
# ---------------------------------------------------------------------------

@patch("httpx.get")
def test_omdb_get_success(mock_get):
    mock_get.return_value = mock_http_response(
        200, {"Title": "The Matrix", "Response": "True"}
    )
    result = server._omdb_get(i="tt0133093")
    assert result["Title"] == "The Matrix"


@patch("httpx.get")
def test_omdb_get_response_false_returns_none(mock_get):
    mock_get.return_value = mock_http_response(
        200, {"Response": "False", "Error": "Movie not found!"}
    )
    assert server._omdb_get(i="tt9999999") is None


def test_omdb_get_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(server, "OMDB_API_KEY", None)
    assert server._omdb_get(i="tt0133093") is None


@patch("httpx.get")
def test_omdb_get_http_error_returns_none(mock_get):
    mock_get.side_effect = httpx.ConnectError("connection refused")
    assert server._omdb_get(i="tt0133093") is None


@patch("httpx.get")
def test_omdb_get_injects_api_key(mock_get):
    mock_get.return_value = mock_http_response(200, {"Response": "True"})
    server._omdb_get(i="tt0133093")
    assert mock_get.call_args[1]["params"]["apikey"] == "test_omdb_key"


# ---------------------------------------------------------------------------
# _resolve_person_id
# ---------------------------------------------------------------------------

@patch("server._tmdb_get")
def test_resolve_person_id_from_numeric_string(mock_tmdb):
    assert server._resolve_person_id("6193") == 6193
    mock_tmdb.assert_not_called()


@patch("server._tmdb_get")
def test_resolve_person_id_from_name_search(mock_tmdb):
    mock_tmdb.return_value = {"results": [{"id": 6193}]}
    assert server._resolve_person_id("Keanu Reeves") == 6193
    mock_tmdb.assert_called_once_with("/search/person", query="Keanu Reeves")


@patch("server._tmdb_get")
def test_resolve_person_id_not_found_returns_none(mock_tmdb):
    mock_tmdb.return_value = {"results": []}
    assert server._resolve_person_id("zzz nobody zzz") is None


@patch("server._tmdb_get")
def test_resolve_person_id_strips_whitespace(mock_tmdb):
    assert server._resolve_person_id("  12345  ") == 12345
    mock_tmdb.assert_not_called()


@patch("server._tmdb_get")
def test_resolve_person_id_takes_first_result(mock_tmdb):
    mock_tmdb.return_value = {"results": [{"id": 100}, {"id": 200}]}
    assert server._resolve_person_id("Common Name") == 100


# ---------------------------------------------------------------------------
# _get_watch_providers
# ---------------------------------------------------------------------------

@patch("server._tmdb_get")
def test_get_watch_providers_netflix_in_flatrate(mock_tmdb):
    mock_tmdb.return_value = {
        "results": {
            "US": {
                "flatrate": [{"provider_name": "Netflix"}, {"provider_name": "Hulu"}],
                "rent": [],
                "buy": [],
                "ads": [],
            }
        }
    }
    result = server._get_watch_providers(603, "movie", "US")
    assert result["netflix_available"] is True
    assert "Netflix" in result["flatrate"]
    assert "Hulu" in result["flatrate"]
    assert result["region"] == "US"


@patch("server._tmdb_get")
def test_get_watch_providers_netflix_not_in_flatrate(mock_tmdb):
    mock_tmdb.return_value = {
        "results": {
            "US": {
                "flatrate": [{"provider_name": "Amazon Prime Video"}],
                "rent": [{"provider_name": "Apple TV"}],
                "buy": [],
                "ads": [],
            }
        }
    }
    result = server._get_watch_providers(603, "movie", "US")
    assert result["netflix_available"] is False
    assert result["rent"] == ["Apple TV"]


@patch("server._tmdb_get")
def test_get_watch_providers_missing_region_data(mock_tmdb):
    mock_tmdb.return_value = {"results": {"GB": {}}}
    result = server._get_watch_providers(603, "movie", "US")
    assert result["netflix_available"] is False
    assert result["flatrate"] == []
    assert result["rent"] == []


@patch("server._tmdb_get")
def test_get_watch_providers_null_response(mock_tmdb):
    mock_tmdb.return_value = None
    result = server._get_watch_providers(603, "movie", "US")
    assert result["netflix_available"] is False


@patch("server._tmdb_get")
def test_get_watch_providers_upcases_region(mock_tmdb):
    mock_tmdb.return_value = {"results": {}}
    result = server._get_watch_providers(603, "movie", "gb")
    assert result["region"] == "GB"


# ---------------------------------------------------------------------------
# search_title
# ---------------------------------------------------------------------------

@patch("server._tmdb_get")
def test_search_title_movie(mock_tmdb):
    mock_tmdb.return_value = {
        "results": [
            {
                "id": 603,
                "title": "The Matrix",
                "release_date": "1999-03-31",
                "overview": "A hacker discovers...",
                "popularity": 85.0,
                "poster_path": "/path.jpg",
            }
        ]
    }
    result = server.search_title("The Matrix", media_type="movie")
    assert result["count"] == 1
    item = result["results"][0]
    assert item["tmdb_id"] == 603
    assert item["title"] == "The Matrix"
    assert item["media_type"] == "movie"
    assert item["poster_url"] == "https://image.tmdb.org/t/p/w500/path.jpg"
    mock_tmdb.assert_called_once_with("/search/movie", query="The Matrix")


@patch("server._tmdb_get")
def test_search_title_tv(mock_tmdb):
    mock_tmdb.return_value = {
        "results": [
            {
                "id": 1396,
                "name": "Breaking Bad",
                "first_air_date": "2008-01-20",
                "overview": "Chemistry teacher",
                "popularity": 100.0,
                "poster_path": None,
            }
        ]
    }
    result = server.search_title("Breaking Bad", media_type="tv")
    item = result["results"][0]
    assert item["title"] == "Breaking Bad"
    assert item["media_type"] == "tv"
    assert item["release_date"] == "2008-01-20"
    mock_tmdb.assert_called_once_with("/search/tv", query="Breaking Bad")


@patch("server._tmdb_get")
def test_search_title_tv_with_year_uses_first_air_date_year(mock_tmdb):
    mock_tmdb.return_value = {"results": []}
    server.search_title("Friends", media_type="tv", year=1994)
    mock_tmdb.assert_called_once_with(
        "/search/tv", query="Friends", first_air_date_year=1994
    )


@patch("server._tmdb_get")
def test_search_title_movie_with_year(mock_tmdb):
    mock_tmdb.return_value = {"results": []}
    server.search_title("Aliens", media_type="movie", year=1986)
    mock_tmdb.assert_called_once_with("/search/movie", query="Aliens", year=1986)


@patch("server._tmdb_get")
def test_search_title_multi_filters_out_people(mock_tmdb):
    mock_tmdb.return_value = {
        "results": [
            {
                "id": 1,
                "title": "Movie A",
                "media_type": "movie",
                "release_date": "2020-01-01",
                "overview": "...",
                "popularity": 50.0,
                "poster_path": None,
            },
            {"id": 2, "name": "Famous Actor", "media_type": "person"},
            {
                "id": 3,
                "name": "Show B",
                "media_type": "tv",
                "first_air_date": "2021-01-01",
                "overview": "...",
                "popularity": 40.0,
                "poster_path": None,
            },
        ]
    }
    result = server.search_title("something")
    assert result["count"] == 2
    types = {r["media_type"] for r in result["results"]}
    assert types == {"movie", "tv"}


@patch("server._tmdb_get")
def test_search_title_limit_clamped_to_20(mock_tmdb):
    mock_tmdb.return_value = {
        "results": [
            {
                "id": i,
                "title": f"Movie {i}",
                "release_date": "2020",
                "overview": "",
                "popularity": 1.0,
                "poster_path": None,
            }
            for i in range(30)
        ]
    }
    result = server.search_title("x", media_type="movie", limit=999)
    assert result["count"] == 20


@patch("server._tmdb_get")
def test_search_title_null_poster_path(mock_tmdb):
    mock_tmdb.return_value = {
        "results": [
            {
                "id": 1,
                "title": "No Poster",
                "release_date": "2020",
                "overview": "",
                "popularity": 1.0,
                "poster_path": None,
            }
        ]
    }
    result = server.search_title("No Poster", media_type="movie")
    assert result["results"][0]["poster_url"] is None


# ---------------------------------------------------------------------------
# get_title_details
# ---------------------------------------------------------------------------

@patch("server._omdb_get")
@patch("server._get_watch_providers")
@patch("server._tmdb_get")
def test_get_title_details_movie_full(mock_tmdb, mock_wp, mock_omdb):
    mock_tmdb.return_value = make_movie_data(cast_count=2)
    mock_wp.return_value = providers_response(flatrate=["Netflix"])
    mock_omdb.return_value = {
        "imdbRating": "8.7",
        "Metascore": "73",
        "Rated": "R",
        "Awards": "Won 4 Oscars.",
        "Plot": "A hacker discovers the truth.",
        "Ratings": [{"Source": "Rotten Tomatoes", "Value": "88%"}],
        "Response": "True",
    }

    result = server.get_title_details(603, "movie")

    assert result["title"] == "The Matrix"
    assert result["media_type"] == "movie"
    assert result["runtime_minutes"] == 136
    assert "Action" in result["genres"]
    assert result["imdb_url"] == "https://www.imdb.com/title/tt0133093/"
    assert result["watch_providers"]["netflix_available"] is True
    assert result["ratings"]["imdb_rating"] == "8.7"
    assert result["ratings"]["rotten_tomatoes"] == "88%"
    assert result["ratings"]["rated"] == "R"
    assert len(result["cast"]) == 2


@patch("server._omdb_get")
@patch("server._get_watch_providers")
@patch("server._tmdb_get")
def test_get_title_details_tv_uses_episode_runtime(mock_tmdb, mock_wp, mock_omdb):
    mock_tmdb.return_value = make_tv_data()
    mock_wp.return_value = providers_response()
    mock_omdb.return_value = None

    result = server.get_title_details(1396, "tv")

    assert result["title"] == "Breaking Bad"
    assert result["runtime_minutes"] == 47
    assert result["release_date"] == "2008-01-20"


@patch("server._omdb_get")
@patch("server._get_watch_providers")
@patch("server._tmdb_get")
def test_get_title_details_cast_capped_at_10(mock_tmdb, mock_wp, mock_omdb):
    data = make_movie_data(cast_count=15)
    mock_tmdb.return_value = data
    mock_wp.return_value = providers_response()
    mock_omdb.return_value = None

    result = server.get_title_details(603, "movie")
    assert len(result["cast"]) == 10


@patch("server._omdb_get")
@patch("server._get_watch_providers")
@patch("server._tmdb_get")
def test_get_title_details_cast_includes_profile_url(mock_tmdb, mock_wp, mock_omdb):
    mock_tmdb.return_value = make_movie_data(cast_count=1)
    mock_wp.return_value = providers_response()
    mock_omdb.return_value = None

    result = server.get_title_details(603, "movie")
    cast_member = result["cast"][0]
    assert "profile_url" in cast_member
    assert cast_member["profile_url"].startswith("https://image.tmdb.org")


@patch("server._omdb_get")
@patch("server._get_watch_providers")
@patch("server._tmdb_get")
def test_get_title_details_without_omdb_no_ratings_key(mock_tmdb, mock_wp, mock_omdb):
    mock_tmdb.return_value = make_movie_data()
    mock_wp.return_value = providers_response()
    mock_omdb.return_value = None  # OMDb unavailable

    result = server.get_title_details(603, "movie")
    assert "ratings" not in result


@patch("server._omdb_get")
@patch("server._get_watch_providers")
@patch("server._tmdb_get")
def test_get_title_details_rt_rating_extracted_from_ratings_list(mock_tmdb, mock_wp, mock_omdb):
    mock_tmdb.return_value = make_movie_data()
    mock_wp.return_value = providers_response()
    mock_omdb.return_value = {
        "imdbRating": "8.7",
        "Metascore": "73",
        "Rated": "R",
        "Awards": "",
        "Plot": "Plot",
        "Ratings": [
            {"Source": "Internet Movie Database", "Value": "8.7/10"},
            {"Source": "Rotten Tomatoes", "Value": "88%"},
            {"Source": "Metacritic", "Value": "73/100"},
        ],
        "Response": "True",
    }

    result = server.get_title_details(603, "movie")
    assert result["ratings"]["rotten_tomatoes"] == "88%"


@patch("server._omdb_get")
@patch("server._get_watch_providers")
@patch("server._tmdb_get")
def test_get_title_details_rt_rating_none_when_missing(mock_tmdb, mock_wp, mock_omdb):
    mock_tmdb.return_value = make_movie_data()
    mock_wp.return_value = providers_response()
    mock_omdb.return_value = {
        "imdbRating": "8.7",
        "Metascore": "73",
        "Rated": "R",
        "Awards": "",
        "Plot": "Plot",
        "Ratings": [],  # no RT rating
        "Response": "True",
    }

    result = server.get_title_details(603, "movie")
    assert result["ratings"]["rotten_tomatoes"] is None


@patch("server._tmdb_get")
def test_get_title_details_not_found_returns_error(mock_tmdb):
    mock_tmdb.return_value = None
    result = server.get_title_details(999999, "movie")
    assert "error" in result


@patch("server._tmdb_get")
def test_get_title_details_invalid_media_type(mock_tmdb):
    result = server.get_title_details(1, "music")
    assert "error" in result
    mock_tmdb.assert_not_called()


@patch("server._omdb_get")
@patch("server._get_watch_providers")
@patch("server._tmdb_get")
def test_get_title_details_region_passed_to_providers(mock_tmdb, mock_wp, mock_omdb):
    mock_tmdb.return_value = make_movie_data()
    mock_wp.return_value = providers_response(region="GB")
    mock_omdb.return_value = None

    server.get_title_details(603, "movie", region="gb")
    mock_wp.assert_called_once_with(603, "movie", "GB")


@patch("server._omdb_get")
@patch("server._get_watch_providers")
@patch("server._tmdb_get")
def test_get_title_details_no_imdb_id_skips_omdb(mock_tmdb, mock_wp, mock_omdb):
    data = make_movie_data()
    data["external_ids"] = {"imdb_id": None}
    mock_tmdb.return_value = data
    mock_wp.return_value = providers_response()

    server.get_title_details(603, "movie")
    mock_omdb.assert_not_called()


# ---------------------------------------------------------------------------
# get_actor_info
# ---------------------------------------------------------------------------

def make_person_data(id=6193, name="Keanu Reeves", imdb_id="nm0000136"):
    return {
        "id": id,
        "name": name,
        "biography": "Born in Beirut...",
        "birthday": "1964-09-02",
        "place_of_birth": "Beirut, Lebanon",
        "known_for_department": "Acting",
        "popularity": 120.0,
        "profile_path": "/keanu.jpg",
        "external_ids": {"imdb_id": imdb_id},
    }


@patch("server._tmdb_get")
def test_get_actor_info_by_name(mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        make_person_data(),
    ]
    result = server.get_actor_info("Keanu Reeves")

    assert result["name"] == "Keanu Reeves"
    assert result["person_id"] == 6193
    assert result["imdb_url"] == "https://www.imdb.com/name/nm0000136/"
    assert result["birthday"] == "1964-09-02"
    assert result["profile_url"] == "https://image.tmdb.org/t/p/w500/keanu.jpg"


@patch("server._tmdb_get")
def test_get_actor_info_by_numeric_id_skips_search(mock_tmdb):
    mock_tmdb.return_value = make_person_data()

    result = server.get_actor_info("6193")

    assert result["person_id"] == 6193
    mock_tmdb.assert_called_once_with("/person/6193", append_to_response="external_ids")


@patch("server._tmdb_get")
def test_get_actor_info_not_found_returns_error(mock_tmdb):
    mock_tmdb.return_value = {"results": []}
    result = server.get_actor_info("zzz nobody")
    assert "error" in result


@patch("server._tmdb_get")
def test_get_actor_info_all_fields_present(mock_tmdb):
    mock_tmdb.side_effect = [{"results": [{"id": 6193}]}, make_person_data()]
    result = server.get_actor_info("Keanu Reeves")
    for field in ("person_id", "name", "biography", "birthday", "place_of_birth",
                  "known_for_department", "popularity", "profile_url", "imdb_url"):
        assert field in result


@patch("server._tmdb_get")
def test_get_actor_info_null_imdb_id(mock_tmdb):
    data = make_person_data(imdb_id=None)
    mock_tmdb.side_effect = [{"results": [{"id": 6193}]}, data]
    result = server.get_actor_info("Keanu Reeves")
    assert result["imdb_url"] is None


# ---------------------------------------------------------------------------
# get_actor_filmography
# ---------------------------------------------------------------------------

@patch("server._tmdb_get")
def test_filmography_sorted_by_popularity_desc(mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [
            make_credit(1, "Low Pop", popularity=10.0),
            make_credit(2, "High Pop", popularity=90.0),
            make_credit(3, "Mid Pop", popularity=50.0),
        ]},
    ]
    result = server.get_actor_filmography("Keanu Reeves")
    pops = [c["popularity"] for c in result["filmography"]]
    assert pops == sorted(pops, reverse=True)


@patch("server._tmdb_get")
def test_filmography_filters_by_movie(mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [
            make_credit(1, "Movie A", media_type="movie"),
            make_credit(2, "TV Show B", media_type="tv"),
        ]},
    ]
    result = server.get_actor_filmography("Keanu Reeves", media_type="movie")
    assert all(c["media_type"] == "movie" for c in result["filmography"])
    assert result["count"] == 1


@patch("server._tmdb_get")
def test_filmography_filters_by_tv(mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [
            make_credit(1, "Movie A", media_type="movie"),
            make_credit(2, "TV Show B", media_type="tv"),
        ]},
    ]
    result = server.get_actor_filmography("Keanu Reeves", media_type="tv")
    assert result["count"] == 1
    assert result["filmography"][0]["title"] == "TV Show B"


@patch("server._tmdb_get")
def test_filmography_no_filter_returns_both(mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [
            make_credit(1, "Movie A", media_type="movie"),
            make_credit(2, "TV Show B", media_type="tv"),
        ]},
    ]
    result = server.get_actor_filmography("Keanu Reeves")
    assert result["count"] == 2


@patch("server._tmdb_get")
def test_filmography_limit_respected(mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [make_credit(i, f"Movie {i}", popularity=float(100 - i)) for i in range(50)]},
    ]
    result = server.get_actor_filmography("Keanu Reeves", limit=5)
    assert result["count"] == 5


@patch("server._tmdb_get")
def test_filmography_limit_clamped_to_100(mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [make_credit(i, f"Movie {i}", popularity=float(i)) for i in range(200)]},
    ]
    result = server.get_actor_filmography("Keanu Reeves", limit=999)
    assert result["count"] == 100


@patch("server._tmdb_get")
def test_filmography_person_not_found(mock_tmdb):
    mock_tmdb.return_value = {"results": []}
    result = server.get_actor_filmography("zzz nobody")
    assert "error" in result


@patch("server._tmdb_get")
def test_filmography_fields_present(mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [make_credit(603, "The Matrix", media_type="movie", character="Neo")]},
    ]
    result = server.get_actor_filmography("Keanu Reeves")
    entry = result["filmography"][0]
    assert entry["tmdb_id"] == 603
    assert entry["title"] == "The Matrix"
    assert entry["character"] == "Neo"
    assert entry["media_type"] == "movie"


# ---------------------------------------------------------------------------
# get_watch_providers (tool wrapper)
# ---------------------------------------------------------------------------

@patch("server._get_watch_providers")
def test_get_watch_providers_tool_netflix_available(mock_wp):
    mock_wp.return_value = providers_response(flatrate=["Netflix"])
    result = server.get_watch_providers(603, "movie")
    assert result["netflix_available"] is True
    assert result["tmdb_id"] == 603
    assert result["media_type"] == "movie"
    mock_wp.assert_called_once_with(603, "movie", "US")


@patch("server._get_watch_providers")
def test_get_watch_providers_tool_custom_region(mock_wp):
    mock_wp.return_value = providers_response(region="GB")
    server.get_watch_providers(603, "movie", region="gb")
    mock_wp.assert_called_once_with(603, "movie", "GB")


@patch("server._get_watch_providers")
def test_get_watch_providers_tool_region_upcased(mock_wp):
    mock_wp.return_value = providers_response(region="CA")
    server.get_watch_providers(603, "movie", region="ca")
    mock_wp.assert_called_once_with(603, "movie", "CA")


@patch("server._get_watch_providers")
def test_get_watch_providers_invalid_media_type(mock_wp):
    result = server.get_watch_providers(1, "music")
    assert "error" in result
    mock_wp.assert_not_called()


@patch("server._get_watch_providers")
def test_get_watch_providers_all_provider_lists_returned(mock_wp):
    mock_wp.return_value = {
        "region": "US",
        "flatrate": ["Netflix"],
        "rent": ["Apple TV"],
        "buy": ["Amazon Video"],
        "ads": ["Pluto TV"],
        "netflix_available": True,
    }
    result = server.get_watch_providers(603, "movie")
    assert result["rent"] == ["Apple TV"]
    assert result["buy"] == ["Amazon Video"]
    assert result["ads"] == ["Pluto TV"]


# ---------------------------------------------------------------------------
# get_actor_netflix_titles
# ---------------------------------------------------------------------------

@patch("server._tmdb_get")
@patch("server._get_watch_providers")
def test_netflix_titles_finds_matching_titles(mock_wp, mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},          # person search
        {"cast": [                              # combined_credits
            make_credit(603, "The Matrix", media_type="movie", popularity=200.0),
            make_credit(604, "John Wick", media_type="movie", popularity=180.0),
        ]},
        {"imdb_id": "tt0133093"},              # external_ids for The Matrix only
    ]
    mock_wp.side_effect = [
        providers_response(flatrate=["Netflix"]),  # The Matrix — on Netflix
        providers_response(flatrate=[]),           # John Wick — not on Netflix
    ]

    result = server.get_actor_netflix_titles("Keanu Reeves", region="US", top_n=2)

    assert result["on_netflix_count"] == 1
    assert result["checked"] == 2
    assert result["on_netflix"][0]["title"] == "The Matrix"
    assert result["on_netflix"][0]["imdb_url"] == "https://www.imdb.com/title/tt0133093/"
    assert "tmdb_url" in result["on_netflix"][0]


@patch("server._tmdb_get")
@patch("server._get_watch_providers")
def test_netflix_titles_no_matches(mock_wp, mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [make_credit(1, "Movie", media_type="movie")]},
    ]
    mock_wp.return_value = providers_response(flatrate=[])

    result = server.get_actor_netflix_titles("Keanu Reeves", top_n=1)
    assert result["on_netflix_count"] == 0
    assert result["on_netflix"] == []


@patch("server._tmdb_get")
def test_netflix_titles_person_not_found(mock_tmdb):
    mock_tmdb.return_value = {"results": []}
    result = server.get_actor_netflix_titles("zzz nobody")
    assert "error" in result


@patch("server._tmdb_get")
@patch("server._get_watch_providers")
def test_netflix_titles_top_n_limits_checks(mock_wp, mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [make_credit(i, f"Movie {i}", popularity=float(100 - i)) for i in range(20)]},
    ]
    mock_wp.return_value = providers_response(flatrate=[])

    result = server.get_actor_netflix_titles("Keanu Reeves", top_n=5)
    assert result["checked"] == 5
    assert mock_wp.call_count == 5


@patch("server._tmdb_get")
@patch("server._get_watch_providers")
def test_netflix_titles_top_n_clamped_to_50(mock_wp, mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [make_credit(i, f"Movie {i}", popularity=float(i)) for i in range(100)]},
    ]
    mock_wp.return_value = providers_response(flatrate=[])

    result = server.get_actor_netflix_titles("Keanu Reeves", top_n=999)
    assert result["checked"] == 50


@patch("server._tmdb_get")
@patch("server._get_watch_providers")
def test_netflix_titles_skips_unknown_media_type(mock_wp, mock_tmdb):
    credit = make_credit(1, "Something", media_type="movie")
    credit["media_type"] = "unknown"  # override after build
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [credit]},
    ]

    result = server.get_actor_netflix_titles("Keanu Reeves", top_n=5)
    mock_wp.assert_not_called()
    assert result["on_netflix_count"] == 0


@patch("server._tmdb_get")
@patch("server._get_watch_providers")
def test_netflix_titles_region_upcased(mock_wp, mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": []},
    ]
    result = server.get_actor_netflix_titles("Keanu Reeves", region="gb")
    assert result["region"] == "GB"


@patch("server._tmdb_get")
@patch("server._get_watch_providers")
def test_netflix_titles_imdb_url_none_when_no_external_id(mock_wp, mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [make_credit(603, "The Matrix", popularity=100.0)]},
        {"imdb_id": None},  # no imdb id in external_ids
    ]
    mock_wp.return_value = providers_response(flatrate=["Netflix"])

    result = server.get_actor_netflix_titles("Keanu Reeves", top_n=1)
    assert result["on_netflix"][0]["imdb_url"] is None


@patch("server._tmdb_get")
@patch("server._get_watch_providers")
def test_netflix_titles_sorted_by_popularity(mock_wp, mock_tmdb):
    mock_tmdb.side_effect = [
        {"results": [{"id": 6193}]},
        {"cast": [
            make_credit(1, "Less Popular", popularity=50.0),
            make_credit(2, "Most Popular", popularity=200.0),
            make_credit(3, "Mid", popularity=100.0),
        ]},
        {"imdb_id": "tt1"},
        {"imdb_id": "tt2"},
        {"imdb_id": "tt3"},
    ]
    mock_wp.return_value = providers_response(flatrate=["Netflix"])

    result = server.get_actor_netflix_titles("Keanu Reeves", top_n=3)
    # All three are on Netflix — order should follow popularity desc
    titles = [t["title"] for t in result["on_netflix"]]
    assert titles[0] == "Most Popular"
    assert titles[1] == "Mid"
    assert titles[2] == "Less Popular"
