"""Pure-math tests for the Erlang-C queueing formula — no warehouse needed.

Regression coverage for the "if utilization >= 1, don't invent a finite
wait" rule, and a hand-checkable reference value.
"""

from app.ml.queue_pressure import erlang_c_wait_probability


def test_low_utilization_gives_low_wait_probability():
    # A lightly loaded system (rho=0.1, 2 servers) should rarely make an
    # arrival wait.
    p = erlang_c_wait_probability(rho=0.1, c=2)
    assert 0 <= p < 0.1


def test_high_utilization_gives_high_wait_probability():
    p = erlang_c_wait_probability(rho=0.95, c=4)
    assert p > 0.8


def test_utilization_at_capacity_is_certain_wait():
    assert erlang_c_wait_probability(rho=1.0, c=3) == 1.0


def test_utilization_over_capacity_is_certain_wait():
    # Oversaturated queues are reported as certain-wait, not an error or a
    # nonsensical negative/blown-up probability — matches queue_pressure.py's
    # rule that rho >= 1 never invents a finite steady-state answer.
    assert erlang_c_wait_probability(rho=1.4, c=3) == 1.0


def test_known_reference_value_single_server():
    # M/M/1: P(wait) reduces to exactly rho for a single server.
    for rho in (0.2, 0.5, 0.8):
        assert abs(erlang_c_wait_probability(rho=rho, c=1) - rho) < 1e-9


def test_more_servers_at_same_utilization_reduces_wait_probability():
    # Pooling capacity across more servers at the same utilization should
    # improve (not worsen) the wait probability - a basic sanity property
    # of queueing systems (economies of scale in server pooling).
    p_2 = erlang_c_wait_probability(rho=0.7, c=2)
    p_8 = erlang_c_wait_probability(rho=0.7, c=8)
    assert p_8 < p_2
