"""
Forge Shorts — PostgreSQL Job Tracker
Mirrors the existing Forge tracking pattern.
Tables are created on first run if they don't exist.

Tables:
  forge_shorts_jobs      — one row per source video processed
  forge_shorts_segments  — one row per Short segment generated
"""
import json
import logging
from enum import Enum
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras

import config

log = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED       = "queued"
    DISCOVERING  = "discovering"
    TRANSCRIBING = "transcribing"
    SELECTING    = "selecting"
    BUILDING     = "building"
    RENDERING    = "rendering"
    EXPORTING    = "exporting"
    COMPLETE     = "complete"
    FAILED       = "failed"


# ── Connection ────────────────────────────────────────────────────────────────

def _conn():
    return psycopg2.connect(config.PG_DSN)


# ── Schema bootstrap ──────────────────────────────────────────────────────────

def init_db():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS forge_shorts_jobs (
                    id          SERIAL PRIMARY KEY,
                    source_file TEXT        NOT NULL,
                    status      TEXT        NOT NULL DEFAULT 'queued',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    error       TEXT,
                    metadata    JSONB       NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS forge_shorts_segments (
                    id             SERIAL PRIMARY KEY,
                    job_id         INTEGER REFERENCES forge_shorts_jobs(id) ON DELETE CASCADE,
                    segment_index  INTEGER,
                    title          TEXT,
                    start_sec      FLOAT,
                    end_sec        FLOAT,
                    hook           TEXT,
                    rationale      TEXT,
                    status         TEXT    NOT NULL DEFAULT 'pending',
                    output_file    TEXT,
                    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_fss_job_id
                    ON forge_shorts_segments(job_id);
            """)
        conn.commit()
    log.info("Forge Shorts DB schema ready")


# ── Job CRUD ──────────────────────────────────────────────────────────────────

def create_job(source_file: Path) -> int:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO forge_shorts_jobs (source_file, status) "
                "VALUES (%s, %s) RETURNING id",
                (str(source_file), JobStatus.QUEUED),
            )
            job_id = cur.fetchone()[0]
        conn.commit()
    log.info(f"Job #{job_id} created for {source_file.name}")
    return job_id


def update_job(
    job_id: int,
    status: JobStatus,
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE forge_shorts_jobs
                SET status     = %s,
                    updated_at = NOW(),
                    error      = COALESCE(%s, error),
                    metadata   = metadata || %s::jsonb
                WHERE id = %s
            """, (status, error, json.dumps(metadata or {}), job_id))
        conn.commit()


# ── Segment CRUD ──────────────────────────────────────────────────────────────

def create_segment(job_id: int, index: int, seg) -> int:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO forge_shorts_segments
                    (job_id, segment_index, title, start_sec, end_sec, hook, rationale)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                job_id, index,
                seg.title, seg.start, seg.end,
                seg.hook, seg.rationale,
            ))
            seg_id = cur.fetchone()[0]
        conn.commit()
    return seg_id


def update_segment(seg_id: int, status: str, output_file: Optional[Path] = None):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE forge_shorts_segments "
                "SET status=%s, output_file=%s WHERE id=%s",
                (status, str(output_file) if output_file else None, seg_id),
            )
        conn.commit()


# ── Read queries (used by shorts_api.py) ─────────────────────────────────────

def list_jobs(limit: int = 100) -> list:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM forge_shorts_jobs ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]


def list_segments(job_id: int) -> list:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM forge_shorts_segments WHERE job_id = %s ORDER BY segment_index",
                (job_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def list_completed_outputs() -> list:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT s.*, j.source_file
                FROM forge_shorts_segments s
                JOIN forge_shorts_jobs j ON j.id = s.job_id
                WHERE s.status = 'complete' AND s.output_file IS NOT NULL
                ORDER BY s.created_at DESC
            """)
            return [dict(row) for row in cur.fetchall()]


def get_segment_output_file(segment_id: int) -> Optional[str]:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT output_file FROM forge_shorts_segments WHERE id = %s",
                (segment_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None
