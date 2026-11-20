"""Durable workflows on Temporal (PR-020).

- ``workflows``: deterministic workflow code. No I/O, clocks or randomness outside Temporal.
- ``activities``: everything that touches the database or the network, each in its own
  ``onyx_worker`` transaction bound to one tenant.
- ``relay``: hands committed outbox events to Temporal, one workflow per event.
- ``worker``: the process that runs the relay and the Temporal worker.
"""
