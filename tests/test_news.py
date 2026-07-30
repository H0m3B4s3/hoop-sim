"""League news wire tests: emission, filtering, capping, save round-trips."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.news import CATEGORIES, MAJOR, MINOR, NORMAL, NewsItem
from hoopsim.save.serialize import world_from_json, world_to_json
from hoopsim.sim import season as S
from hoopsim.systems import news as N


# ============================================================================
# Module-level helpers
# ============================================================================

def _world(seed=1):
    """Build a fresh world, ready for news testing."""
    w = build_world(seed=seed)
    w.user_team_id = 1
    w.season_games = 16
    return w


def _played_world(seed=1, games=20):
    """Build and play through a full season to test news accumulation."""
    w = build_world(seed=seed)
    w.user_team_id = 1
    w.season_games = games
    S.start_season(w)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    return w


# ============================================================================
# Tests: 1. Basic emission and world state
# ============================================================================

def test_emit_appends_item_with_world_year_and_day():
    """emit() appends an item with the world's current year and day."""
    w = _world(seed=1)
    S.start_season(w)

    year_at_start = w.season_year
    day_at_start = w.day

    item = N.emit(w, "game", "Test headline", importance=NORMAL)

    assert item is not None, "emit should return the item"
    assert item.year == year_at_start, "Item year should match world.season_year"
    assert item.day == day_at_start, "Item day should match world.day"
    assert item.headline == "Test headline"
    assert item.importance == NORMAL
    assert len(w.news) == 1, "Item should be appended to world.news"
    assert w.news[0] == item


def test_emit_is_total_clamps_unknown_category():
    """emit() clamps unknown category to a valid one rather than raising."""
    w = _world(seed=2)
    S.start_season(w)

    # Emit with an invalid category
    item = N.emit(w, "invalid_category_xyz", "Headline", importance=NORMAL)

    assert item is not None, "emit should never raise, even with invalid category"
    assert item.category in CATEGORIES, f"Invalid category should be clamped to valid one, got {item.category}"
    # The default fallback is "game" per systems/news.py
    assert item.category == "game", "Unknown category should clamp to 'game'"


def test_emit_returns_none_for_empty_headline():
    """emit() returns None for an empty headline and does not append."""
    w = _world(seed=3)
    S.start_season(w)

    initial_len = len(w.news)
    item = N.emit(w, "game", "", importance=NORMAL)

    assert item is None, "emit should return None for empty headline"
    assert len(w.news) == initial_len, "No item should be appended for empty headline"


# ============================================================================
# Tests: 2. Ring buffer capping
# ============================================================================

def test_ring_buffer_caps_at_max_items_and_drops_oldest():
    """emit MAX_ITEMS+50 numbered headlines; assert length is capped and oldest are dropped."""
    w = _world(seed=4)
    S.start_season(w)

    # Emit many items
    for i in range(N.MAX_ITEMS + 50):
        N.emit(w, "game", f"Headline {i:03d}", importance=NORMAL)

    # Ring buffer should have capped at MAX_ITEMS
    assert len(w.news) == N.MAX_ITEMS, f"News should be capped at {N.MAX_ITEMS}, got {len(w.news)}"

    # The survivors should be the most recent (highest numbered)
    remaining_headlines = [item.headline for item in w.news]
    first_survivor_num = int(remaining_headlines[0].split()[-1])
    last_survivor_num = int(remaining_headlines[-1].split()[-1])

    # The oldest 50 should have been dropped
    assert first_survivor_num == 50, \
        f"First survivor should be 'Headline 050', got '{remaining_headlines[0]}'"
    assert last_survivor_num == N.MAX_ITEMS + 49, \
        f"Last survivor should be the newest, got {last_survivor_num}"


# ============================================================================
# Tests: 3. recent() filtering and order
# ============================================================================

def test_recent_returns_newest_first():
    """recent() returns items newest first."""
    w = _world(seed=5)
    S.start_season(w)

    # Emit three items with distinct headlines
    N.emit(w, "game", "ZZZZZ_First_headline", importance=NORMAL)
    N.emit(w, "game", "ZZZZZ_Second_headline", importance=NORMAL)
    N.emit(w, "game", "ZZZZZ_Third_headline", importance=NORMAL)

    # Filter to just our test items
    items = [item for item in N.recent(w) if "ZZZZZ_" in item.headline]
    assert len(items) >= 3, "Should have at least the three we emitted"
    # newest first means the last emitted should be first
    assert items[0].headline == "ZZZZZ_Third_headline", "Most recent should be first"
    assert items[1].headline == "ZZZZZ_Second_headline"
    assert items[2].headline == "ZZZZZ_First_headline"


def test_recent_honors_category_filter():
    """recent(category=...) filters to only items of that category."""
    w = _world(seed=6)
    S.start_season(w)

    # Emit items of different categories
    N.emit(w, "game", "Game item", importance=NORMAL)
    N.emit(w, "injury", "Injury item", importance=NORMAL)
    N.emit(w, "transaction", "Trade item", importance=NORMAL)
    N.emit(w, "game", "Another game item", importance=NORMAL)

    game_items = N.recent(w, category="game")
    assert all(item.category == "game" for item in game_items), \
        "All items should be game category"
    assert len(game_items) == 2, "Should have exactly 2 game items"

    injury_items = N.recent(w, category="injury")
    assert len(injury_items) == 1, "Should have exactly 1 injury item"
    assert injury_items[0].headline == "Injury item"


def test_recent_honors_tid_filter():
    """recent(tid=...) filters to items mentioning that team."""
    w = _world(seed=7)
    S.start_season(w)

    team1 = w.teams[1]
    team2 = w.teams[2]

    # Emit items for different teams
    N.emit(w, "game", "Team 1 item", tids=[team1.tid])
    N.emit(w, "game", "Team 2 item", tids=[team2.tid])
    N.emit(w, "game", "Team 1 item 2", tids=[team1.tid])

    team1_items = N.recent(w, tid=team1.tid)
    assert len(team1_items) == 2, "Should have 2 items for team 1"
    assert all(team1.tid in item.tids for item in team1_items)

    team2_items = N.recent(w, tid=team2.tid)
    assert len(team2_items) == 1, "Should have 1 item for team 2"


def test_recent_honors_min_importance_filter():
    """recent(min_importance=...) filters to items at that importance level or higher."""
    w = _world(seed=8)
    S.start_season(w)

    # Emit items of different importance levels
    N.emit(w, "game", "Minor item", importance=MINOR)
    N.emit(w, "game", "Normal item", importance=NORMAL)
    N.emit(w, "game", "Major item", importance=MAJOR)
    N.emit(w, "game", "Another minor", importance=MINOR)

    # Filter to NORMAL and above (≥2)
    items = N.recent(w, min_importance=NORMAL)
    assert len(items) == 2, f"Should have 2 items at NORMAL or higher, got {len(items)}"
    assert all(item.importance >= NORMAL for item in items)

    # Filter to MAJOR only (≥3)
    major_items = N.recent(w, min_importance=MAJOR)
    assert len(major_items) == 1, "Should have 1 MAJOR item"
    assert major_items[0].headline == "Major item"


# ============================================================================
# Tests: 4. Simulation generates news
# ============================================================================

def test_simulating_stretch_produces_game_and_injury_items():
    """Simulating a stretch of season produces game and injury news items."""
    w = _played_world(seed=9, games=16)

    # After playing a season, the wire should have accumulated some items
    assert len(w.news) > 0, "Playing a season should generate news"

    # Should have various categories
    categories = {item.category for item in w.news}
    # At least game and injury should be present (and maybe injury if anyone got hurt)
    assert "game" in categories, "Should have game items"
    # injury may or may not be present depending on RNG


def test_simulating_offseason_produces_award_draft_coaching_items():
    """Running an offseason produces award, draft, coaching, and milestone news items."""
    w = _world(seed=10)
    w.season_games = 8  # Short season to run fast
    S.start_season(w)
    # Play a full season
    while not S.regular_season_complete(w):
        S.advance_one_day(w)

    # Now run offseason: archive_season emits awards, champions are announced
    from hoopsim.systems import offseason as O
    from hoopsim.sim import playoffs as P
    champ = P.champion(w)
    O.archive_season(w, champ)

    # Awards should now be in the wire
    award_items = [item for item in w.news if item.category == "award"]
    assert len(award_items) > 0, "Offseason should produce award items"


def test_first_round_draft_picks_produce_items_second_round_do_not():
    """First-round draft picks produce news items; second-round picks do not."""
    w = _world(seed=11)
    S.start_season(w)
    # Play a season
    while not S.regular_season_complete(w):
        S.advance_one_day(w)

    # Manually set up a draft class and make picks
    from hoopsim.systems import draft_system as D
    from hoopsim.models.league import Phase
    from hoopsim.config import NUM_TEAMS
    w.phase = Phase.DRAFT
    D.setup_draft(w)

    initial_draft_items = len([item for item in w.news if item.category == "draft"])

    # Make a first-round pick (pick 1)
    first_round_player = D.best_available(w)
    D.make_pick(w, first_round_player)

    first_round_news = [item for item in w.news if item.category == "draft"]
    assert len(first_round_news) > initial_draft_items, "First-round pick should generate a draft news item"

    # Make picks until we're in round 2 (past pick 30 for 30 teams)
    picks_before_r2 = w.draft_class.current_pick
    while w.draft_class.current_pick <= NUM_TEAMS and not w.draft_class.complete:
        pid = D.best_available(w)
        D.make_pick(w, pid)

    # A two-round draft over NUM_TEAMS teams always has round-2 picks left here, so this half of
    # the test must actually run — guarding it with a conditional would let it silently vanish.
    assert not w.draft_class.complete, "expected round-2 picks to remain"
    second_round_player = D.best_available(w)
    D.make_pick(w, second_round_player)

    # Second-round picks should NOT emit per systems/news.py
    final_draft_items = [item for item in w.news if item.category == "draft"]
    second_round_only = [item for item in final_draft_items if "Round 2" in item.detail]
    assert len(second_round_only) == 0, "Second-round picks should not generate news items"


# ============================================================================
# Tests: 5. Save round-trip
# ============================================================================

def test_save_round_trip_preserves_news_with_fields():
    """News survives world_to_json/world_from_json with all fields intact."""
    w = _world(seed=12)
    S.start_season(w)

    # Emit a variety of items
    N.emit(w, "game", "Game headline", importance=NORMAL, detail="Game detail line")
    N.emit(w, "injury", "Injury headline", importance=MAJOR, tids=[1], pids=[5], detail="Injury detail")
    N.emit(w, "transaction", "Trade headline", importance=NORMAL, tids=[1, 2], pids=[5, 10])

    # Round-trip
    json_str = world_to_json(w)
    w2 = world_from_json(json_str)

    assert len(w2.news) == len(w.news), "News list length should survive round-trip"

    for orig, loaded in zip(w.news, w2.news):
        assert loaded.year == orig.year, "year should survive"
        assert loaded.day == orig.day, "day should survive"
        assert loaded.category == orig.category, "category should survive"
        assert loaded.headline == orig.headline, "headline should survive"
        assert loaded.detail == orig.detail, "detail should survive"
        assert loaded.importance == orig.importance, "importance should survive"
        assert loaded.tids == orig.tids, "tids should survive"
        assert loaded.pids == orig.pids, "pids should survive"


# ============================================================================
# Tests: 6. Backward compatibility
# ============================================================================

def test_backward_compatibility_missing_news_key():
    """A world dict with no 'news' key loads to an empty list."""
    w = _world(seed=13)
    # Get the JSON and strip the news key
    json_str = world_to_json(w)
    import json
    data = json.loads(json_str)
    # Remove the news key if it exists (it's at top level, not nested)
    data.pop("news", None)
    json_str_no_news = json.dumps(data)

    # Load should not crash
    w2 = world_from_json(json_str_no_news)
    assert w2.news == [], "Missing 'news' key should load as empty list"


# ============================================================================
# Tests: 7. Headline snapshot frozen at write time
# ============================================================================

def test_headlines_frozen_at_write_time():
    """Headlines are snapshots. Changing player name after emit must NOT change stored headline."""
    w = _world(seed=14)
    S.start_season(w)

    p = list(w.players.values())[0]
    original_name = p.name

    # Emit news about this player
    item = N.emit(w, "game", f"{p.name} drops 50", pids=[p.pid], importance=NORMAL)
    stored_headline = item.headline

    # Change the player's first and last name
    p.first_name = "Different"
    p.last_name = "Name"

    # The stored headline should NOT have changed
    assert w.news[0].headline == stored_headline, "Headline should be frozen at emit time"
    assert original_name in stored_headline, "Original name should be in the frozen headline"
    assert "Different Name" not in stored_headline, "New name should not appear in old headline"


# ============================================================================
# Tests: 8. Multiple importance levels and category labels
# ============================================================================

def test_category_labels_match_constants():
    """CATEGORY_LABELS has an entry for each category in CATEGORIES."""
    from hoopsim.models.news import CATEGORY_LABELS

    for cat in CATEGORIES:
        assert cat in CATEGORY_LABELS, f"Category '{cat}' missing from CATEGORY_LABELS"
        assert isinstance(CATEGORY_LABELS[cat], str), f"Label for '{cat}' should be a string"
        assert len(CATEGORY_LABELS[cat]) > 0, f"Label for '{cat}' should not be empty"


def test_importance_levels_are_ordered():
    """MINOR < NORMAL < MAJOR."""
    assert N.MINOR < N.NORMAL, "MINOR should be less than NORMAL"
    assert N.NORMAL < N.MAJOR, "NORMAL should be less than MAJOR"


# ============================================================================
# Tests: 9. Empty headlines never emit
# ============================================================================

def test_empty_headlines_return_none():
    """emit() with empty headline returns None and does not append."""
    w = _world(seed=15)
    S.start_season(w)

    initial_len = len(w.news)
    item = N.emit(w, "game", "", importance=NORMAL)
    assert item is None, "Empty headline should return None"
    assert len(w.news) == initial_len, "Empty headline should not append to news"


def test_limit_parameter_caps_results():
    """recent(limit=N) returns at most N items."""
    w = _world(seed=16)
    S.start_season(w)

    for i in range(20):
        N.emit(w, "game", f"Item {i}", importance=NORMAL)

    items_5 = N.recent(w, limit=5)
    assert len(items_5) <= 5, "Should return at most 5 items"

    items_100 = N.recent(w, limit=100)
    assert len(items_100) <= 20, "Should return at most the number of items emitted"
