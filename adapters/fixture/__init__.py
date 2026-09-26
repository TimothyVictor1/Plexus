"""Fixture adapters backed by the adapter_records table.

They behave like a real source system for the purposes of the pipeline: a write lands
somewhere observable, and reading it back shows the change. That makes an execution real
rather than simulated, without touching anybody's live Gmail or ClickUp.
"""

from adapters.fixture.adapter import FixtureAdapter, WriteDisabledError, get_adapter

__all__ = ["FixtureAdapter", "WriteDisabledError", "get_adapter"]
