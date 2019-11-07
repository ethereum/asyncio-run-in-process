import pytest

from asyncio_run_in_process.state import (
    State,
)


@pytest.mark.parametrize('state', State)
def test_state_properties(state):
    all_states = tuple(State)
    before_states = all_states[:state]
    after_states = all_states[state.value + 1:]

    assert state.is_on_or_after(state)
    assert not state.is_before(state)
    assert not state.is_next(state)

    assert all(other.is_before(state) for other in before_states)
    assert all(state.is_on_or_after(other) for other in before_states)
    if before_states:
        assert before_states[-1].is_next(state)

    assert all(other.is_on_or_after(state) for other in after_states)
    assert all(state.is_before(other) for other in after_states)

    if after_states:
        assert state.is_next(after_states[0])
