"""The daily pipeline: stage sequencing, run reports, and the automatic loop.

The orchestrator is pure (stages are injected callables) so sequencing and
failure isolation are unit-tested without subprocesses or a database.
"""
