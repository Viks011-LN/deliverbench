from alertd import registry


def test_the_existing_kinds_are_registered():
    for kind in ("price_move", "limit_usage", "stale_feed", "news"):
        assert registry.rule_for(kind) is not None, kind
        assert kind in registry.kinds()


def test_an_unknown_kind_has_no_rule():
    assert registry.rule_for("fx_fixing") is None


def test_every_rule_module_provides_the_interface():
    for kind, module in registry.RULES.items():
        assert module.KIND == kind
        assert callable(module.key) and callable(module.evaluate)
