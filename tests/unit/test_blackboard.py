"""Unit tests for blackboard state machine."""

import pytest

from porous_designer.blackboard.persistence import load_blackboard, save_blackboard
from porous_designer.blackboard.state import Blackboard
from porous_designer.blackboard.state_machine import InvalidTransitionError, StateMachine
from porous_designer.domain.enums import RunStatus
from porous_designer.domain.specification import load_legacy_spec


def test_happy_path_transitions():
    bb = Blackboard()
    sm = StateMachine(bb)

    sm.transition(RunStatus.PARSING)
    sm.transition(RunStatus.NEEDS_USER_REVIEW)
    sm.transition(RunStatus.SPECIFICATION_APPROVED)
    sm.transition(RunStatus.FEASIBILITY_CHECKING)
    sm.transition(RunStatus.PREVIEW_GENERATING)
    sm.transition(RunStatus.PREVIEW_READY)
    sm.transition(RunStatus.FINAL_GENERATING)
    sm.transition(RunStatus.VALIDATING)
    sm.transition(RunStatus.PASSED)
    sm.transition(RunStatus.EXPORTED)

    assert bb.status == RunStatus.EXPORTED
    assert len(bb.events) >= 10


def test_invalid_transition_raises():
    bb = Blackboard()
    sm = StateMachine(bb)
    with pytest.raises(InvalidTransitionError):
        sm.transition(RunStatus.VALIDATING)


def test_cancel_from_parsing():
    bb = Blackboard()
    sm = StateMachine(bb)
    sm.transition(RunStatus.PARSING)
    sm.cancel("test cancel")
    assert bb.status == RunStatus.CANCELLED


def test_blackboard_persistence_roundtrip():
    import shutil
    from pathlib import Path

    tmp = Path("runs/_test_tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    bb = Blackboard(raw_request="test request")
    spec = load_legacy_spec("sample_spec.txt")
    bb.set_parsed_spec(spec)
    path = tmp / "blackboard.json"
    save_blackboard(bb, path)
    loaded = load_blackboard(path)
    assert loaded.run_id == bb.run_id
    assert loaded.parsed_specification is not None
    assert loaded.get_approved_spec() is None
    shutil.rmtree(tmp)


def test_unresolved_ambiguities():
    from porous_designer.domain.run_state import AmbiguityRecord

    bb = Blackboard(
        ambiguities=[
            AmbiguityRecord(
                term="hexagonal packing",
                possible_meanings=["hcp_spherical_pores", "honeycomb_solid"],
                recommended="hcp_spherical_pores",
            )
        ]
    )
    assert not bb.critical_ambiguities_resolved()
    bb.ambiguities[0].resolved = "hcp_spherical_pores"
    bb.ambiguities[0].user_confirmed = True
    assert bb.critical_ambiguities_resolved()
