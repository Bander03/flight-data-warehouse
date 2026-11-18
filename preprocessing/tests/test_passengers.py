import pandas as pd
import pytest

from fdw import config
from fdw.passengers import repair_passenger_keys

REAL_ORPHANS = {8871, 11387, 11899, 24773, 28393, 36842, 44143, 52821, 58935}


def _with_orphans(tables, rows, ids):
    """Copy of ``tables`` whose fact rows ``rows`` carry PassengerIDs ``ids``."""
    fact = tables["fact"].copy()
    fact.loc[rows, "PassengerID"] = pd.array(ids, dtype="Int64")
    return {**tables, "fact": fact}


def test_only_orphan_rows_are_remapped(valid_tables):
    t = _with_orphans(valid_tables, [3, 10], [99991, 99992])
    out = repair_passenger_keys(t, config.SEED)
    old, new = t["fact"], out["fact"]
    changed = old["PassengerID"].ne(new["PassengerID"])
    assert list(changed[changed].index) == [3, 10]
    # every other column of every row is untouched
    others = [c for c in old.columns if c != "PassengerID"]
    pd.testing.assert_frame_equal(old[others], new[others])
    assert str(new["PassengerID"].dtype) == "Int64"


def test_new_ids_exist_in_dim_and_were_unused(valid_tables):
    t = _with_orphans(valid_tables, [3, 10], [99991, 99992])
    used_before = set(t["fact"]["PassengerID"].dropna())
    out = repair_passenger_keys(t, config.SEED)
    new_ids = list(out["fact"].loc[[3, 10], "PassengerID"])
    assert len(set(new_ids)) == 2                          # distinct from each other
    for pid in new_ids:
        assert pid in set(t["passenger"]["PassengerID"])
        assert pid not in used_before
    assert out["fact"]["PassengerID"].isin(t["passenger"]["PassengerID"]).all()


def test_dimension_never_gets_new_rows(valid_tables):
    t = _with_orphans(valid_tables, [3], [99991])
    out = repair_passenger_keys(t, config.SEED)
    pd.testing.assert_frame_equal(out["passenger"], t["passenger"])
    for k in t:
        if k != "fact":
            assert out[k] is t[k] or out[k].equals(t[k])


def test_no_orphans_is_a_noop(valid_tables):
    out = repair_passenger_keys(valid_tables, config.SEED)
    pd.testing.assert_frame_equal(out["fact"], valid_tables["fact"])


def test_deterministic(valid_tables):
    t = _with_orphans(valid_tables, [3, 10], [99991, 99992])
    a = repair_passenger_keys(t, config.SEED)["fact"]
    b = repair_passenger_keys(t, config.SEED)["fact"]
    pd.testing.assert_frame_equal(a, b)


def test_input_not_mutated(valid_tables):
    t = _with_orphans(valid_tables, [3, 10], [99991, 99992])
    before = t["fact"].copy()
    repair_passenger_keys(t, config.SEED)
    pd.testing.assert_frame_equal(t["fact"], before)


def test_not_enough_unused_passengers_raises(valid_tables):
    # the fact uses ids 1000..1054; keep only 2 unused dim passengers (1055, 1056)
    t = _with_orphans(valid_tables, [55, 56, 57], [90001, 90002, 90003])
    t["passenger"] = t["passenger"][t["passenger"]["PassengerID"] <= 1056]
    with pytest.raises(ValueError, match="unused"):
        repair_passenger_keys(t, config.SEED)


def test_real_data_nine_orphans_repaired(real_tables):
    fact = real_tables["fact"]
    dim_ids = set(real_tables["passenger"]["PassengerID"])
    orphan_mask = ~fact["PassengerID"].isin(dim_ids)
    assert set(fact.loc[orphan_mask, "PassengerID"]) == REAL_ORPHANS
    assert int(orphan_mask.sum()) == 9

    out = repair_passenger_keys(real_tables, config.SEED)["fact"]
    assert out["PassengerID"].isin(dim_ids).all()
    changed = fact["PassengerID"].ne(out["PassengerID"])
    assert changed.equals(orphan_mask)                      # nothing else was touched
    used_before = set(fact.loc[~orphan_mask, "PassengerID"])
    assert not (set(out.loc[orphan_mask, "PassengerID"]) & used_before)
    assert out["PassengerID"].nunique() == fact["PassengerID"].nunique()
