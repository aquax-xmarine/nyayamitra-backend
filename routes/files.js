const express = require('express');
const multer = require('multer');
const db = require('../db');

const router = express.Router();
const path = require('path');

const crypto = require('crypto');
const fs = require('fs');


const storage = multer.diskStorage({
  destination: 'uploads/',
  filename: (req, file, cb) => {
    const ext = path.extname(file.originalname);
    const uniqueName = Date.now() + '-' + Math.round(Math.random() * 1e9);
    cb(null, uniqueName + ext);
  }
});

const upload = multer({ storage });



router.get('/', async (req, res) => {
  const { containerId } = req.query;

  if (!containerId) {
    return res.status(400).json({ error: 'containerId is required' });
  }

  try {
    const result = await db.query(
      `SELECT id, name, file_path, is_bookmarked, original_file_id
       FROM files
       WHERE container_id = $1
       ORDER BY id DESC`,
      [containerId]
    );

    res.json(result.rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch files' });
  }
});



router.post('/upload', upload.array('files', 10), async (req, res) => {
  const { containerId, source, sessionId } = req.body;
  console.log('\n📥 [UPLOAD] New upload request received');

  console.log('\n📥 [UPLOAD] New upload request received');
  console.log('   source:', source);
  console.log('   containerId:', containerId || 'none (chat upload)');
  console.log('   sessionId:', sessionId || 'none');
  console.log('   files received:', req.files?.map(f => f.originalname));

  if (!req.files || req.files.length === 0) return res.status(400).json({ error: 'No files uploaded' });
  if (source !== 'chat' && !containerId) return res.status(400).json({ error: 'containerId missing' });

  try {
    const results = [];

    for (const file of req.files) {
      console.log(`\n🔍 [PROCESSING] ${file.originalname}`);
      console.log('   temp path:', file.path);
      console.log('   size:', file.size, 'bytes');

      const fileBuffer = fs.readFileSync(file.path);
      const hash = crypto.createHash('sha256').update(fileBuffer).digest('hex');
      console.log('   SHA-256 hash:', hash);

      const existing = await db.query(
        `SELECT id, name, file_path, file_hash, source FROM files WHERE file_hash = $1 LIMIT 1`,
        [hash]
      );

      if (existing.rows.length > 0) {
        console.log(`   ✅ DUPLICATE FOUND — matches existing file:`);
        console.log('      id:', existing.rows[0].id);
        console.log('      name:', existing.rows[0].name);
        console.log('      source:', existing.rows[0].source);
        console.log('      file_path:', existing.rows[0].file_path);
        console.log('   🗑️  Deleting temp file:', file.path);

        fs.unlinkSync(file.path);

        if (containerId || sessionId) {
          await db.query(
            `UPDATE files SET container_id = $1, source = 'document', session_id = $2 WHERE id = $3`,
            [containerId, sessionId || null, existing.rows[0].id]
          );
        }

        results.push({ ...existing.rows[0], duplicate: true });
      } else {
        console.log('   🆕 NEW FILE — inserting into DB');
        console.log('   container_id:', source === 'chat' ? 'null (chat)' : containerId);

        const inserted = await db.query(
          `INSERT INTO files (name, container_id, file_path, file_hash, source, session_id)
   VALUES ($1, $2, $3, $4, $5, $6)
   RETURNING id, name, file_path, file_hash, source, session_id`,
          [
            file.originalname,
            source === 'chat' ? null : containerId,
            file.filename,
            hash,
            source || 'document',
            sessionId || null  // ADD THIS
          ]
        );

        console.log('   ✅ Inserted successfully:');
        console.log('      id:', inserted.rows[0].id);
        console.log('      name:', inserted.rows[0].name);
        console.log('      file_path:', inserted.rows[0].file_path);
        console.log('      source:', inserted.rows[0].source);

        results.push({ ...inserted.rows[0], duplicate: false });
      }
    }

    console.log('\n📤 [UPLOAD COMPLETE] Summary:');
    results.forEach(r => {
      console.log(`   - ${r.name}: ${r.duplicate ? '♻️  duplicate (reused existing)' : '✅ newly saved'}`);
    });

    res.json({ success: true, files: results });
  } catch (err) {
    console.error('\n❌ [UPLOAD ERROR]', err.message);
    res.status(500).json({ error: 'Failed to upload files' });
  }
});


router.patch('/:id/container', async (req, res) => {
  const { id } = req.params;
  const { container_id } = req.body;
  if (!container_id) return res.status(400).json({ error: 'container_id required' });

  try {
    await db.query(`UPDATE files SET container_id = $1 WHERE id = $2`, [container_id, id]);
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to update file container' });
  }
});


router.post('/:id/save-original-location', async (req, res) => {
  const { id } = req.params;
  try {
    await db.query(
      `UPDATE files SET original_container_id = container_id WHERE id = $1`,
      [id]
    );
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to save original location' });
  }
});


router.get('/:id/original-parent-files', async (req, res) => {
  const { id } = req.params;
  try {
    const result = await db.query(
      `SELECT original_container_id FROM files WHERE id = $1`,
      [id]
    );
    if (result.rowCount === 0) return res.status(404).json({ error: 'File not found' });
    res.json({ parent_id: result.rows[0].original_container_id });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch original parent' });
  }
});

// PATCH /files/:id/rename
router.patch('/:id/rename', async (req, res) => {
  const { id } = req.params;
  const { name } = req.body;

  if (!name || !name.trim()) {
    return res.status(400).json({ error: 'New file name is required' });
  }

  try {
    const result = await db.query(
      `UPDATE files
       SET name = $1
       WHERE id = $2
       RETURNING id, name, container_id, file_path`,
      [name.trim(), id]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({ error: 'File not found' });
    }

    res.json({ success: true, file: result.rows[0] });
  } catch (err) {
    console.error('Failed to rename file:', err);
    res.status(500).json({ error: 'Failed to rename file' });
  }
});


router.post('/:fileId/copy', async (req, res) => {
  const { fileId } = req.params;
  const { containerId } = req.body;

  try {
    // Fetch original file
    const fileResult = await db.query('SELECT * FROM files WHERE id=$1', [fileId]);
    if (!fileResult.rows.length) return res.status(404).send('File not found');

    const originalFile = fileResult.rows[0];

    // Insert a copy
    const newFileResult = await db.query(
      `INSERT INTO files (name, container_id, file_path, original_container_id, is_bookmarked, original_file_id)
       VALUES ($1, $2, $3, $4, $5, $6)
       RETURNING *`,
      [originalFile.name, containerId, originalFile.file_path, originalFile.original_container_id, true, fileId]
    );

    res.json(newFileResult.rows[0]);
  } catch (err) {
    console.error(err);
    res.status(500).send('Failed to copy file');
  }
});


// Toggle bookmark
router.put('/:id/bookmark', async (req, res) => {
  const { id } = req.params;
  const { bookmarked } = req.body; // true or false

  try {
    const result = await db.query(
      `UPDATE files SET is_bookmarked=$1 WHERE id=$2 RETURNING *`,
      [bookmarked, id]
    );

    if (!result.rows.length) return res.status(404).json({ error: 'File not found' });

    res.json({ success: true, file: result.rows[0] });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to update bookmark' });
  }
});

router.delete('/:id', async (req, res) => {
  const { id } = req.params;
  try {
    const result = await db.query(`DELETE FROM files WHERE id = $1 RETURNING *`, [id]);
    if (result.rowCount === 0) return res.status(404).json({ error: 'File not found' });
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to delete file' });
  }
});


router.post('/:id/record-recent', async (req, res) => {
  const { id } = req.params;

  try {
    // Get the recent root container
    const recentResult = await db.query(
      `SELECT id FROM containers WHERE section = 'recent' AND parent_id IS NULL LIMIT 1`
    );
    if (!recentResult.rows.length) return res.status(404).json({ error: 'Recent container not found' });
    const recentRootId = recentResult.rows[0].id;

    // Get original file
    const fileResult = await db.query(`SELECT * FROM files WHERE id = $1`, [id]);
    if (!fileResult.rows.length) return res.status(404).json({ error: 'File not found' });
    const originalFile = fileResult.rows[0];

    // Check if a recent copy already exists
    const existing = await db.query(
      `SELECT id FROM files WHERE original_file_id = $1 AND container_id = $2`,
      [id, recentRootId]
    );

    if (existing.rows.length) {
      // Update last_opened_at
      await db.query(
        `UPDATE files SET last_opened_at = NOW() WHERE id = $1`,
        [existing.rows[0].id]
      );
    } else {
      // Insert a new copy into recent
      await db.query(
        `INSERT INTO files (name, container_id, file_path, original_file_id, last_opened_at)
         VALUES ($1, $2, $3, $4, NOW())`,
        [originalFile.name, recentRootId, originalFile.file_path, id]
      );
    }

    res.json({ success: true });
  } catch (err) {
    console.error('Failed to record recent file:', err);
    res.status(500).json({ error: 'Failed to record recent file' });
  }
});





module.exports = router;
