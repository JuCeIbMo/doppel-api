"""ERP module: catalog, inventory, sales, clients, finance, reports.

Lives inside the existing `app/` service. Each module follows the same two-layer
pattern as the rest of doppel-api: a thin router calls a service that holds all
business logic and talks to Supabase directly (atomic operations go through
Postgres RPC functions defined in migration_v8_erp.sql).
"""
