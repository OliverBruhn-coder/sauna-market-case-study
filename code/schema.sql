PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS sessions (
  actor TEXT NOT NULL,
  session_id TEXT NOT NULL,
  city TEXT,
  location_name TEXT,
  location_id TEXT,
  location_address TEXT,
  sauna_id TEXT,
  sauna_name TEXT,
  session_date TEXT,
  session_start_time TEXT,
  session_end_time TEXT,
  session_duration_minutes INTEGER,
  weekday INTEGER,
  week_number INTEGER,
  holdtype TEXT,
  session_title TEXT,
  instructor_name_raw TEXT,
  instructor_id TEXT,
  instructor_gender TEXT,
  session_posted_at TEXT,
  session_first_seen_timestamp TEXT,
  session_last_seen_timestamp TEXT,
  PRIMARY KEY (actor, session_id)
);

CREATE TABLE IF NOT EXISTS session_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  session_id TEXT NOT NULL,
  capacity_total INTEGER,
  booked_count INTEGER,
  spots_available INTEGER,
  is_waitlist INTEGER,
  is_sold_out INTEGER,
  scrape_timestamp TEXT NOT NULL,
  FOREIGN KEY (actor, session_id) REFERENCES sessions(actor, session_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_date
  ON sessions(session_date);

CREATE INDEX IF NOT EXISTS idx_snapshots_session
  ON session_snapshots(actor, session_id);

CREATE INDEX IF NOT EXISTS idx_snapshots_scrape
  ON session_snapshots(scrape_timestamp);

CREATE TABLE IF NOT EXISTS session_change_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  session_id TEXT NOT NULL,
  change_timestamp TEXT NOT NULL,
  change_type TEXT NOT NULL,
  change_fields TEXT,
  session_date TEXT,
  session_start_time TEXT,
  location_name TEXT,
  session_title TEXT
);

CREATE INDEX IF NOT EXISTS idx_change_events_timestamp
  ON session_change_events(change_timestamp);

CREATE INDEX IF NOT EXISTS idx_change_events_session
  ON session_change_events(actor, session_id);
