"""
Chain 2 -- Backdrop transformation.

COVERAGE (Phase 2):
  [TESTED]  backdrop_segment() -- the pure transform-string builder. No DB, no
            Cloudinary call, no I/O. This is the core of the CEO scope:
            - transform string per mode: reflect = NO e_dropshadow,
              shadow = INCLUDES e_dropshadow
            - all 9 presets produce a valid, well-formed transform string
            - empty / invalid / None key -> '' (kill switch at the function level)
            - subject and scene are URL-quoted
            - BACKDROP_PRESETS integrity (9 presets, exactly one reflect)
  [DEFERRED] The save route (/sp-dashboard/backdrop) that UPDATEs
            dealership_team.backdrop_preset, and the storefront render path that
            reads it, use raw sqlite3.connect() to the hardcoded prod path.
            Those DB-persistence/route layers are deferred to Phase 2.5
            (see F-2). The transform LOGIC and the kill-switch decision are
            fully covered here.

The mode rule is the key quality unlock from the backdrops feature: dropshadow
grounds a car on outdoor scenes, but kills the reflection on the showroom's
polished floor -- so showroom (and only showroom) runs in reflect mode.
"""
from app.routes import backdrop_segment, BACKDROP_PRESETS


# =========================================================================
# Mode rule: shadow includes e_dropshadow, reflect omits it
# =========================================================================
def test_shadow_preset_includes_dropshadow():
    s = backdrop_segment("mountain", "2023 Toyota RAV4")
    assert "e_dropshadow/" in s


def test_reflect_preset_omits_dropshadow():
    s = backdrop_segment("showroom", "2023 Toyota RAV4")
    assert "e_dropshadow/" not in s


def test_showroom_is_the_only_reflect_preset():
    reflect = [k for k, (_scene, mode) in BACKDROP_PRESETS.items() if mode == "reflect"]
    assert reflect == ["showroom"]


def test_every_shadow_preset_includes_dropshadow():
    """All 8 outdoor presets must ground the car with a drop shadow."""
    for key, (_scene, mode) in BACKDROP_PRESETS.items():
        seg = backdrop_segment(key, "Car")
        if mode == "shadow":
            assert "e_dropshadow/" in seg, f"{key} (shadow) missing dropshadow"
        else:
            assert "e_dropshadow/" not in seg, f"{key} (reflect) should not have dropshadow"


# =========================================================================
# Kill switch: empty / invalid / None -> ''
# =========================================================================
def test_empty_key_returns_empty_string():
    assert backdrop_segment("", "x") == ""


def test_invalid_key_returns_empty_string():
    assert backdrop_segment("not_a_real_preset", "x") == ""


def test_none_key_returns_empty_string():
    assert backdrop_segment(None, "x") == ""


# =========================================================================
# All 9 presets produce a valid, well-formed transform string
# =========================================================================
def test_all_nine_presets_are_present():
    assert len(BACKDROP_PRESETS) == 9


def test_all_presets_produce_well_formed_segment():
    """Every preset's segment must contain the required Cloudinary stages."""
    for key in BACKDROP_PRESETS:
        seg = backdrop_segment(key, "2023 Toyota RAV4")
        assert seg, f"{key} produced an empty segment"
        assert seg.startswith("e_extract:prompt_"), f"{key} missing extract stage"
        assert "e_gen_background_replace:prompt_" in seg, f"{key} missing bg replace"
        assert "c_pad,w_1600,h_900,b_gen_fill/" in seg, f"{key} missing pad/canvas"
        assert "q_auto:good,f_auto,fl_progressive/" in seg, f"{key} missing delivery opts"
        assert seg.endswith("/"), f"{key} segment should end with /"


def test_every_preset_has_scene_and_mode():
    """BACKDROP_PRESETS integrity: each entry is (scene_prompt, mode)."""
    for key, entry in BACKDROP_PRESETS.items():
        assert isinstance(entry, tuple) and len(entry) == 2, f"{key} malformed"
        scene, mode = entry
        assert isinstance(scene, str) and scene, f"{key} empty scene"
        assert mode in ("shadow", "reflect"), f"{key} bad mode {mode!r}"


# =========================================================================
# URL-quoting of subject and scene
# =========================================================================
def test_subject_is_url_quoted():
    """Spaces in the subject must be percent-encoded, not raw."""
    seg = backdrop_segment("mountain", "2023 Toyota RAV4")
    assert "2023%20Toyota%20RAV4" in seg
    assert "prompt_2023 Toyota" not in seg   # raw space must not leak


def test_subject_defaults_when_blank():
    """A blank subject falls back to 'the vehicle' (url-quoted)."""
    seg = backdrop_segment("mountain", "")
    assert "the%20vehicle" in seg


def test_scene_is_url_quoted():
    """The showroom scene text must be percent-encoded in the segment."""
    seg = backdrop_segment("showroom", "Car")
    assert "Modern%20sleek%20car%20showroom" in seg
