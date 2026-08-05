"""Dobles reutilizables para pruebas sin servicios externos."""

from tests.fakes.supabase import FakeResult, FakeSupabase, FakeTableQuery, StrictSupabase

__all__ = ["FakeResult", "FakeSupabase", "FakeTableQuery", "StrictSupabase"]
