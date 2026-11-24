from alertd.rules import news

WATCHING = '[news]\nwatchlist = ["ORVK", "KSVH"]\n'


def event(make_event, tags=(), tickers=("KSVH",), headline="Kesvora Holdings cuts full-year guidance", source="wire"):
    return make_event("news", source=source, headline=headline, published_at="2026-11-03T09:58:00Z",
                      tickers=list(tickers), tags=list(tags))


def evaluate(make_event, make_settings, text="", **fields):
    return news.evaluate(event(make_event, **fields), make_settings(text).section("news"))


def test_a_story_with_nothing_the_desk_watches(make_event, make_settings):
    assert evaluate(make_event, make_settings, tags=["earnings"]) is None


def test_a_watched_tag_is_a_warning(make_event, make_settings):
    found = evaluate(make_event, make_settings, tags=["guidance", "earnings"])
    assert (found.level, found.reasons) == ("warning", ["tag"])
    assert found.detail == "wire, tags: guidance"


def test_a_critical_tag(make_event, make_settings):
    assert evaluate(make_event, make_settings, tags=["halt"]).level == "critical"


def test_a_watchlist_ticker_alone_is_info(make_event, make_settings):
    found = evaluate(make_event, make_settings, WATCHING, tags=[])
    assert (found.level, found.reasons, found.detail) == ("info", ["watchlist"], "wire")


def test_a_watched_tag_on_a_watchlist_ticker_is_one_level_up(make_event, make_settings):
    found = evaluate(make_event, make_settings, WATCHING, tags=["downgrade"])
    assert (found.level, found.reasons) == ("critical", ["tag", "watchlist"])


def test_the_subject_is_the_first_ticker_or_the_source(make_event, make_settings):
    assert evaluate(make_event, make_settings, tags=["halt"], tickers=["KSVH", "ORVK"]).subject == "KSVH"
    assert evaluate(make_event, make_settings, tags=["halt"], tickers=[]).subject == "wire"


def test_a_long_headline_is_shortened(make_event, make_settings):
    found = evaluate(make_event, make_settings, tags=["halt"], headline="Kesvora " * 20)
    assert len(found.what) == 80 and found.what.endswith("...")


def test_the_key(make_event):
    assert news.key(event(make_event)) == "news:wire:KSVH"
    assert news.key(event(make_event, tickers=[])) == "news:wire:-"
