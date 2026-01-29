const express = require('express');
const upload = require('../middleware/upload');

const router = express.Router();

router.post(
  '/',
  upload.array('files', 10),
  async (req, res) => {
    try {
      console.log('RAW CONTENT-TYPE:', req.headers['content-type']);
      console.log('BODY:', req.body);
      console.log('FILES:', req.files); // ✅ ARRAY

      const { question } = req.body;
      const files = req.files;

      if (!question && (!files || files.length === 0)) {
        return res.status(400).json({
          error: 'Please provide a question or upload a file'
        });
      }

      res.json({
        success: true,
        message: 'Backend received data successfully ✅',
        question,
        files: files?.map(f => ({
          originalName: f.originalname,
          storedName: f.filename,
          size: f.size,
          type: f.mimetype
        })) || []
      });

    } catch (err) {
      console.error('❌ Error in /api/ask:', err);
      res.status(500).json({ error: err.message });
    }
  }
);


module.exports = router;
