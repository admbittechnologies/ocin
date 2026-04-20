"""
Manual migration runner to avoid Alembic async connection issues.
This script directly executes the required SQL migrations.
"""
import os
import psycopg2
from sqlalchemy import text

# Load database URL from app config
from app.config import settings as app_settings
database_url = app_settings.DATABASE_URL

# Convert to sync URL for psycopg2
sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

print(f"Connecting to: {sync_url}")

# Connect to database
conn = psycopg2.connect(sync_url)
conn.autocommit = True
cursor = conn.cursor()

try:
    # Migration 001: Create approvals table
    print("Running migration: 001_create_approvals_table")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
            run_id UUID REFERENCES runs(id) ON DELETE CASCADE,
            schedule_id UUID REFERENCES schedules(id) ON DELETE SET NULL,
            kind VARCHAR(64) NOT NULL,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            payload JSONB DEFAULT '{}',
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            resolution_note TEXT,
            expires_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)

    # Create indexes for approvals table
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS approvals_user_id_status_idx ON approvals(user_id, status);
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS approvals_user_id_status_agent_id_idx ON approvals(user_id, status, agent_id);
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS approvals_user_id_run_id_idx ON approvals(user_id, run_id);
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS approvals_user_id_schedule_id_idx ON approvals(user_id, schedule_id);
    """)

    print("[OK] Migration 001_create_approvals_table completed")

    # Migration 002: Add parent_run_id column to runs table
    print("Running migration: 002_add_parent_run_id_column")
    cursor.execute("""
        ALTER TABLE runs ADD COLUMN IF NOT EXISTS parent_run_id UUID REFERENCES runs(id) ON DELETE SET NULL;
    """)
    print("[OK] Migration 002_add_parent_run_id_column completed")

    print("\n[OK] All migrations completed successfully!")

except Exception as e:
    print(f"[ERROR] Migration failed: {e}")
    raise
finally:
    cursor.close()
    conn.close()
