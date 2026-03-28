const express = require('express');
const upload = require('../middleware/upload');
const FormData = require('form-data');
const fs = require('fs');
const fetch = require('node-fetch').default;

const router = express.Router();

router.post('/', upload.array('files', 10), async (req, res) => {
  try {
    const { question } = req.body;
    const files = req.files;

    if (!files || files.length === 0) {
      return res.status(400).json({ error: 'Please upload at least one file' });
    }

    const result = await processFilesWithFastAPI(files, question);

    if (result.error) {
      return res.status(500).json({ error: result.error });
    }

    res.json({ success: true, ...result });

  } catch (err) {
    console.error('Error in /api/ask:', err);
    res.status(500).json({ error: err.message });l
  }
});

async function processFilesWithFastAPI(files, question) {
  try {
    const formData = new FormData();

    files.forEach(file => {
      formData.append('files', fs.createReadStream(file.path), file.originalname);
    });

    if (question) formData.append('question', question);

    const response = await fetch('http://127.0.0.1:8000/api/ask', {
      method: 'POST',
      body: formData,
      headers: formData.getHeaders()
    });

    const data = await response.json();

    if (data.error) {
      console.error("FastAPI returned an error:", data.error);
      return { error: "Error from backend" };
    }

    return data;

  } catch (err) {
    console.error('Error sending files to FastAPI:', err.message);
    return { error: "Could not connect to backend" };
  }
}

module.exports = router;