-- risk state store
create table if not exists risk_state (
  key text primary key,
  value text not null,
  updated_at timestamptz not null default current_timestamp
);

insert or ignore into risk_state(key, value) values
  ('kill_switch', 'off'),
  ('daily_loss_breaker', 'off'),
  ('heartbeat_misses', '0'),
  ('run_id', 'INIT');
