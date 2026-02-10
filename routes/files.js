const express = require('express');
const multer = require('multer');
const db = require('../db');

const router = express.Router();


const upload = multer({
  dest: 'uploads/', // local storage for now
});

router.get('/', async (req, res) => {
  const { containerId } = req.query;

  if (!containerId) {
    return res.status(400).json({ error: 'containerId is required' });
  }

  try {
    const result = await db.query(
      `SELECT id, name, file_path
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
  const { containerId } = req.body;

  console.log('UPLOAD containerId:', containerId);
  console.log('FILES:', req.files);

  if (!containerId) {
    return res.status(400).json({ error: 'containerId missing' });
  }

  if (!req.files || req.files.length === 0) {
    return res.status(400).json({ error: 'No files uploaded' });
  }

  try {
    // Insert all files
    for (const file of req.files) {
      await db.query(
        `INSERT INTO files (name, container_id, file_path)
         VALUES ($1, $2, $3)`,
        [file.originalname, containerId, file.path]
      );
    }

    res.json({
      success: true,
      filesUploaded: req.files.length
    });
  } catch (err) {
    console.error('Upload error:', err);
    res.status(500).json({ error: 'Failed to upload files' });
  }
});

module.exports = router;
