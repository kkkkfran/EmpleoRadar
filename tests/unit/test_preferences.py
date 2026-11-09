from types import SimpleNamespace

from app.profile.preferences import build_default_match_criteria, criteria_from_db_preferences


def test_saved_locations_are_not_replaced_with_defaults():
    prefs = SimpleNamespace(preferred_regions='["Metropolitana"]',
                            priority_comunas='["Santiago"]')
    criteria = criteria_from_db_preferences(prefs)
    assert criteria.preferred_regions == ["Metropolitana"]
    assert criteria.priority_comunas == ["Santiago"]


def test_invalid_json_type_uses_list_defaults():
    criteria = criteria_from_db_preferences(SimpleNamespace(preferred_regions='42'))
    assert isinstance(criteria.preferred_regions, list)
    assert criteria.preferred_regions


def test_new_preferences_focus_on_chillan_and_chillan_viejo():
    criteria = build_default_match_criteria()
    assert criteria.preferred_regions == ["Ñuble"]
    assert criteria.preferred_comunas == ["Chillán", "Chillán Viejo"]
    assert criteria.priority_comunas == ["Chillán", "Chillán Viejo"]
