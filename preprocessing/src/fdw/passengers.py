"""Passenger key repair (ruling R4).

The source fact carries a few PassengerID values that do not exist in the
passenger dimension (a source defect). Only those rows are remapped, to
passenger IDs that exist in the dimension and are not yet used by any fact row.
The dimension is never changed and no passenger row is invented.
"""
import numpy as np
import pandas as pd


def repair_passenger_keys(tables: dict, seed: int) -> dict:
    """Return new tables whose fact PassengerIDs all exist in the passenger dim.

    Rows whose PassengerID is already in the dimension are untouched. Each
    orphan row gets a distinct, previously unused dimension passenger chosen
    with a seeded generator (deterministic for a given input and seed).
    Raises ValueError when the dimension has too few unused passengers.
    """
    fact = tables["fact"]
    dim_ids = tables["passenger"]["PassengerID"].dropna()
    orphan = ~fact["PassengerID"].isin(dim_ids)          # null IDs count as orphans too
    new = dict(tables)
    if not orphan.any():
        new["fact"] = fact.copy()
        return new

    used = set(fact.loc[~orphan, "PassengerID"].dropna().astype("int64"))
    candidates = np.array(sorted(set(dim_ids.astype("int64")) - used), dtype="int64")
    n = int(orphan.sum())
    if len(candidates) < n:
        raise ValueError(f"{n} fact rows need a passenger but only "
                         f"{len(candidates)} unused passengers exist in the dimension")
    rng = np.random.default_rng(seed)
    chosen = rng.choice(candidates, size=n, replace=False)

    fixed = fact.copy()
    fixed.loc[orphan, "PassengerID"] = pd.array(chosen, dtype="Int64")
    new["fact"] = fixed
    return new
