"""Add monitoring jobs and alerts tables

Revision ID: fad9dc5a3036
Revises: 03d11f55c301
Create Date: 2026-10-03 12:21:13.962552

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fad9dc5a3036'
down_revision: Union[str, Sequence[str], None] = '03d11f55c301'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns to alerts table (SQLite-compatible)
    op.add_column('alerts', sa.Column('job_id', sa.String(length=36), nullable=True))
    op.add_column('alerts', sa.Column('sector_id', sa.String(length=50), nullable=True))
    op.add_column('alerts', sa.Column('sites_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('alerts', sa.Column('total_area_m2', sa.Float(), nullable=True, server_default='0.0'))
    op.add_column('alerts', sa.Column('max_threat_level', sa.String(length=20), nullable=True))
    
    # Create indexes
    op.create_index('ix_alerts_job_created', 'alerts', ['job_id', 'created_at'], unique=False)
    
    # Create foreign keys (SQLite requires explicit naming)
    op.create_foreign_key('fk_alerts_job_id_monitoring_jobs', 'alerts', 'monitoring_jobs', ['job_id'], ['id'])
    op.create_foreign_key('fk_alerts_sector_id_sectors', 'alerts', 'sectors', ['sector_id'], ['id'])
    
    # Create monitoring_jobs table if not exists
    op.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_jobs (
            id VARCHAR(36) PRIMARY KEY,
            job_id VARCHAR(50) UNIQUE NOT NULL,
            user_id VARCHAR(36) NOT NULL,
            sector_id VARCHAR(50),
            name VARCHAR(255) NOT NULL,
            description TEXT,
            bbox JSON NOT NULL,
            confidence_threshold FLOAT DEFAULT 0.7,
            lookback_days INTEGER DEFAULT 14,
            schedule_type VARCHAR(20) DEFAULT 'interval',
            cron_expression VARCHAR(100),
            interval_hours INTEGER DEFAULT 24,
            is_active BOOLEAN DEFAULT 1,
            last_run DATETIME,
            next_run DATETIME,
            run_count INTEGER DEFAULT 0,
            last_error TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (sector_id) REFERENCES sectors (id)
        )
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_monitoring_jobs_user_active 
        ON monitoring_jobs (user_id, is_active)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop monitoring_jobs table
    op.execute("DROP TABLE IF EXISTS monitoring_jobs")
    
    # Drop foreign keys from alerts
    op.drop_constraint('fk_alerts_sector_id_sectors', 'alerts', type_='foreignkey')
    op.drop_constraint('fk_alerts_job_id_monitoring_jobs', 'alerts', type_='foreignkey')
    
    # Drop index
    op.drop_index('ix_alerts_job_created', table_name='alerts')
    
    # Drop columns from alerts (SQLite doesn't support DROP COLUMN easily, so we skip)
    # In production, you'd recreate the table without these columns