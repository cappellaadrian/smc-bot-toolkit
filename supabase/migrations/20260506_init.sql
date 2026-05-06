-- Migration: initial schema for SMC paper bot
-- Run with: supabase db push

create table if not exists positions (
    id              uuid primary key,
    symbol          text not null,
    side            text not null check (side in ('long','short')),
    entry_price     numeric not null,
    size_usd        numeric not null,
    stop_loss       numeric not null,
    take_profit_1   numeric not null,
    take_profit_2   numeric not null,
    opened_at       timestamptz not null,
    closed_at       timestamptz,
    exit_price      numeric,
    outcome         text check (outcome in ('tp1','tp2','sl','be','manual')),
    realized_pnl_usd numeric default 0,
    notes           text
);

create index if not exists positions_symbol_idx on positions (symbol);
create index if not exists positions_opened_at_idx on positions (opened_at);

create table if not exists equity_snapshots (
    id          bigserial primary key,
    ts          timestamptz not null default now(),
    equity      numeric not null,
    daily_pnl_pct numeric not null
);

create index if not exists equity_ts_idx on equity_snapshots (ts);

create table if not exists kill_switch_events (
    id      bigserial primary key,
    ts      timestamptz not null default now(),
    tripped boolean not null,
    reason  text
);
