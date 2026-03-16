/**
 * Forge Shorts — Express API Routes
 * Mount at /api/shorts in your existing Forge Express server.
 *
 * Usage in app.js / server.js:
 *   const shortsRouter = require('./routes/shorts');
 *   app.use('/api/shorts', shortsRouter);
 *
 * Assumes your existing app uses pg (node-postgres) and exposes
 * a pool via require('../db') or similar. Adjust the import below.
 */

const express = require('express');
const path    = require('path');
const { Pool } = require('pg');

const router = express.Router();

// ── DB — adjust to match your existing pool setup ─────────────────────────────
const pool = new Pool({ connectionString: process.env.PG_DSN });

// ── Settings file (mirrors .env values, overridable via UI) ───────────────────
const SETTINGS_DEFAULTS = {
  minDur: 30, targetDur: 45, maxDur: 60,
  segCount: 4, wordsPerGroup: 4,
};
let runtimeSettings = { ...SETTINGS_DEFAULTS };

// ── GET /api/shorts/jobs ──────────────────────────────────────────────────────
router.get('/jobs', async (req, res) => {
  try {
    const { rows } = await pool.query(
      `SELECT * FROM forge_shorts_jobs ORDER BY created_at DESC LIMIT 100`
    );
    res.json(rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/shorts/jobs/:id/segments ─────────────────────────────────────────
router.get('/jobs/:id/segments', async (req, res) => {
  try {
    const { rows } = await pool.query(
      `SELECT * FROM forge_shorts_segments WHERE job_id = $1 ORDER BY segment_index`,
      [req.params.id]
    );
    res.json(rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/shorts/outputs ───────────────────────────────────────────────────
// Returns all completed segments that have an output file
router.get('/outputs', async (req, res) => {
  try {
    const { rows } = await pool.query(
      `SELECT s.*, j.source_file
       FROM forge_shorts_segments s
       JOIN forge_shorts_jobs j ON j.id = s.job_id
       WHERE s.status = 'complete' AND s.output_file IS NOT NULL
       ORDER BY s.created_at DESC`
    );
    res.json(rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/shorts/download/:segmentId ──────────────────────────────────────
router.get('/download/:segmentId', async (req, res) => {
  try {
    const { rows } = await pool.query(
      `SELECT output_file FROM forge_shorts_segments WHERE id = $1`,
      [req.params.segmentId]
    );
    if (!rows.length || !rows[0].output_file) {
      return res.status(404).json({ error: 'Output file not found' });
    }
    const filePath = rows[0].output_file;
    res.download(filePath, path.basename(filePath));
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/shorts/settings ──────────────────────────────────────────────────
router.get('/settings', (req, res) => {
  res.json(runtimeSettings);
});

// ── POST /api/shorts/settings ─────────────────────────────────────────────────
router.post('/settings', (req, res) => {
  const allowed = ['minDur', 'targetDur', 'maxDur', 'segCount', 'wordsPerGroup'];
  const updates = Object.fromEntries(
    Object.entries(req.body).filter(([k]) => allowed.includes(k))
  );
  runtimeSettings = { ...runtimeSettings, ...updates };

  // Write back to .env file so Python side picks it up on next job
  _writeEnv(runtimeSettings);

  res.json(runtimeSettings);
});

// ── POST /api/shorts/process ──────────────────────────────────────────────────
// Triggers the watcher to pick up whatever is in the inbox, or manually
// kicks off orchestrate.py against a specified file path.
router.post('/process', (req, res) => {
  const { spawn } = require('child_process');
  const forgeShortsDir = process.env.FORGE_SHORTS_DIR || '/opt/forge/shorts';
  const pythonBin = process.env.PYTHON_BIN || 'python3';

  if (req.body.file) {
    const proc = spawn(pythonBin, ['orchestrate.py', req.body.file], {
      cwd: forgeShortsDir,
      detached: true,
      stdio: 'ignore',
    });
    proc.unref();
    res.json({ started: true, file: req.body.file });
  } else {
    // Signal watcher to process everything in inbox
    // (watcher runs continuously — this just forces a scan)
    res.json({ started: false, message: 'Drop a file into clippy/shorts/ to trigger processing' });
  }
});

// ── Watcher status toggle ─────────────────────────────────────────────────────
router.post('/watcher', (req, res) => {
  const { active } = req.body;
  const { execSync } = require('child_process');
  try {
    if (active) {
      execSync('sudo systemctl start forge-shorts', { timeout: 5000 });
    } else {
      execSync('sudo systemctl stop forge-shorts', { timeout: 5000 });
    }
    res.json({ active });
  } catch (err) {
    // If systemctl isn't available (dev mode), just acknowledge
    res.json({ active, warning: err.message });
  }
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function _writeEnv(settings) {
  const fs = require('fs');
  const envPath = process.env.FORGE_SHORTS_ENV
    || '/opt/forge/shorts/.env';

  try {
    let content = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : '';
    const map = {
      minDur:       'SEGMENT_MIN_DURATION',
      targetDur:    'SEGMENT_TARGET_DURATION',
      maxDur:       'SEGMENT_MAX_DURATION',
      segCount:     'SEGMENT_TARGET_COUNT',
      wordsPerGroup:'SUBTITLE_WORDS_PER_GROUP',
    };
    for (const [key, envKey] of Object.entries(map)) {
      if (settings[key] == null) continue;
      const regex = new RegExp(`^${envKey}=.*$`, 'm');
      const line  = `${envKey}=${settings[key]}`;
      content = regex.test(content)
        ? content.replace(regex, line)
        : content + `\n${line}`;
    }
    fs.writeFileSync(envPath, content);
  } catch (err) {
    console.warn('Could not write .env settings back to disk:', err.message);
  }
}

module.exports = router;
