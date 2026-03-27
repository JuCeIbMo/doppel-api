-- migration_auth.sql
-- Ejecutar DESPUÉS de migration.sql
-- Tabla para rastrear intentos fallidos de login (rate limiting)

create table login_attempts (
  id bigint generated always as identity primary key,
  email text not null,
  ip_address text,
  attempted_at timestamptz default now()
);

create index idx_login_attempts_email on login_attempts(email, attempted_at);
create index idx_login_attempts_ip on login_attempts(ip_address, attempted_at);

alter table login_attempts enable row level security;

-- Nota: Supabase Auth maneja el registro/login de usuarios.
-- Activar o desactivar confirmación de email en:
-- Supabase Dashboard → Authentication → Providers → Email → "Confirm email"
-- Para MVP se recomienda desactivar la confirmación y activarla cuando el producto madure.
