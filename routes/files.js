const express = require('express');
const multer = require('multer');
const db = require('../db');

const router = express.Router();

const upload = multer({
  dest: 'uploads/', // local storage for now
});

router.post('/upload', upload.array('files'), async (req, res) => {
  const { containerId } = req.body;

  try {
    const inserts = req.files.map(file =>
      db.query(
        `INSERT INTO files (name, container_id, path)
         VALUES ($1, $2, $3)`,
        [file.originalname, containerId || null, file.path]
      )
    );

    await Promise.all(inserts);

    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Upload failed' });
  }
});

module.exports = router;
