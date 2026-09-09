"""The effect key, as properties (§9.6).

    effect_key = sha256(run_root_id ‖ step_index ‖ tool_name ‖ canonical_args)[:32]

Four things must be true of it at once, and each one is a defence against a different failure:

    stable   across attempts and recoveries   → the receiver can deduplicate
    unique   per logical effect in a run root → two effects can never share a key
    distinct across forks                     → a counterfactual cannot collide with the real run
    blind    to credentials                   → rotating a secret cannot trip nondeterminism

It is the only defence a fence cannot give, because a fence protects the journal and nothing in the
outside world.
"""

from __future__ import annotations

import os
import string
import uuid

from hypothesis import given, settings
from hypothesis import strategies as st

from keel.core.hashing import args_hash, canonical_args, effect_key

RUN_IDS = st.builds(uuid.uuid4)
STEPS = st.integers(min_value=0, max_value=10_000)
NAMES = st.sampled_from(["search", "write_file", "create_issue", "send_email", "charge"])
SCALARS = st.one_of(
    st.none(), st.booleans(), st.integers(), st.text(max_size=32), st.floats(allow_nan=False)
)
ARGS = st.dictionaries(st.text(min_size=1, max_size=8), SCALARS, max_size=6)
# What an environment variable may actually hold: printable, no NUL. The generator is describing a
# credential store, not Unicode.
SECRETS = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=24
)
PROP = settings(max_examples=100, deadline=None)


@PROP
@given(run_root=RUN_IDS, step=STEPS, name=NAMES, args=ARGS)
def test_the_key_is_stable_and_well_formed(run_root, step, name, args) -> None:
    key = effect_key(run_root, step, name, args)
    assert key == effect_key(run_root, step, name, args), "an attempt must not change the key"
    assert len(key) == 32 and set(key) <= set(string.hexdigits.lower())


@PROP
@given(run_root=RUN_IDS, step=STEPS, name=NAMES, args=ARGS, other=STEPS)
def test_a_different_logical_effect_is_a_different_key(run_root, step, name, args, other) -> None:
    key = effect_key(run_root, step, name, args)
    if other != step:
        assert effect_key(run_root, other, name, args) != key, "step_index is part of the identity"
    for different_name in ("search", "charge"):
        if different_name != name:
            assert effect_key(run_root, step, different_name, args) != key
    assert effect_key(run_root, step, name, {**args, "__extra__": 1}) != key, "args are the identity"


@PROP
@given(base=RUN_IDS, fork=RUN_IDS, step=STEPS, name=NAMES, args=ARGS)
def test_a_fork_can_never_collide_with_its_base(base, fork, step, name, args) -> None:
    """A fork gets a new `run_root_id`, so replaying history in a what-if branch cannot present a
    key the real run already presented (§10.6)."""
    assert effect_key(base, step, name, args) != effect_key(fork, step, name, args)


@PROP
@given(args=ARGS)
def test_argument_order_is_not_part_of_the_identity(args) -> None:
    """`canonical_args` is sorted-key JSON, so the same call written two ways is the same effect —
    otherwise a dict literal reordered by a refactor would silently become a second effect."""
    reversed_args = dict(reversed(list(args.items())))
    assert canonical_args(args) == canonical_args(reversed_args)
    assert args_hash(args) == args_hash(reversed_args)
    run, step = uuid.uuid4(), 3
    assert effect_key(run, step, "charge", args) == effect_key(run, step, "charge", reversed_args)


@PROP
@given(run_root=RUN_IDS, step=STEPS, args=ARGS, secret=SECRETS)
def test_rotating_a_credential_cannot_change_a_key(run_root, step, args, secret) -> None:
    """The secrets contract, as arithmetic. Credentials are never arguments — a tool reads them
    from its environment at execution time — so they are never hashed and never journaled, and
    rotating one can neither move an effect key nor trip nondeterminism detection (Appendix A §2).
    """
    before = effect_key(run_root, step, "charge", args)
    old = os.environ.get("KEEL_PROP_SECRET")
    try:
        os.environ["KEEL_PROP_SECRET"] = secret
        assert effect_key(run_root, step, "charge", args) == before
    finally:
        if old is None:
            os.environ.pop("KEEL_PROP_SECRET", None)
        else:
            os.environ["KEEL_PROP_SECRET"] = old
