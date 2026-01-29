
const express = require('express');
const upload = require('../middleware/upload');
const FormData = require('form-data');
const fs = require('fs');
const fetch = require('node-fetch').default;


const router = express.Router();




router.post(
  '/',
  upload.array('files', 10),
  async (req, res) => {
    try {
      console.log('🔥🔥🔥 NEW ROUTE FILE HIT 🔥🔥🔥');
      console.log('RAW CONTENT-TYPE:', req.headers['content-type']);
      console.log('BODY:', req.body);
      console.log('FILES:', req.files);

      const { question } = req.body;
      const files = req.files;

      const filePaths = files?.map(f => f.path) || [];
      console.log('Saved file paths:', filePaths);

      if (!question && (!files || files.length === 0)) {
        return res.status(400).json({
          error: 'Please provide a question or upload a file'
        });
      }

      if (files && files.length > 0) {
        parseInBackground(files); // 🚀 NO await
      }


      res.json({
        success: true,
        message: 'Backend received data successfully',
        question,
        files: files?.map(f => ({
          originalName: f.originalname,
          storedName: f.filename,
          size: f.size,
          type: f.mimetype
        })) || []
      });

    } catch (err) {
      console.error('Error in /api/ask:', err);
      res.status(500).json({ error: err.message });
    }
  }
);

async function parseInBackground(files) {
  try {
    const formData = new FormData();

    files.forEach(file => {
      formData.append(
        'files',
        fs.createReadStream(file.path),
        file.originalname
      );
    });

    const response = await fetch('http://127.0.0.1:8000/parse', {
      method: 'POST',
      body: formData,
      headers: formData.getHeaders()
    });

    const data = await response.json();

    console.log('✅ Parsing finished');
    console.log('📄 Parsed documents preview:');

    data.documents.forEach((doc, i) => {
      console.log(`--- Document ${i + 1} ---`);
      console.log('Filename:', doc.filename);
      console.log('Text length:', doc.text_length);
      console.log('Preview:', doc.preview?.slice(0, 300));
    });

  } catch (err) {
    console.error('❌ Parsing error:', err.message);
  }
}




module.exports = router;
