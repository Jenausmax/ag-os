CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    model TEXT NOT NULL,
    runtime TEXT NOT NULL CHECK (runtime IN ('host', 'docker')),
    type TEXT NOT NULL CHECK (type IN ('permanent', 'dynamic')),
    status TEXT NOT NULL DEFAULT 'stopped' CHECK (status IN ('stopped', 'idle', 'working', 'awaiting_confirmation')),
    current_task TEXT DEFAULT '',
    tmux_window TEXT DEFAULT '',
    container_id TEXT DEFAULT '',
    config JSON DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'private' CHECK (scope IN ('private', 'shared', 'global')),
    shared_with JSON DEFAULT '[]',
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    ttl TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cron_expression TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    clear_before INTEGER NOT NULL DEFAULT 1,
    last_run TIMESTAMP,
    last_result TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS guard_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    regex_result TEXT,
    llm_result TEXT,
    final_result TEXT NOT NULL CHECK (final_result IN ('pass', 'block', 'suspicious')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
