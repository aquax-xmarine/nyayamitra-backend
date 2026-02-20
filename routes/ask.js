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
      const { question } = req.body;
      const files = req.files;

      if (!question && (!files || files.length === 0)) {
        return res.status(400).json({ error: 'Please provide a question or upload a file' });
      }

      //  AWAIT the answer before responding
      const answer = await getGroqAnswer(files, question);

      //  Send answer to frontend
      res.json({
        success: true,
        answer,  // frontend reads this
        question
      });

    } catch (err) {
      console.error('Error in /api/ask:', err);
      res.status(500).json({ error: err.message });
    }
  }
);

//  Renamed and returns answer
async function getGroqAnswer(files, question) {
  try {
    const formData = new FormData();

    files.forEach(file => {
      formData.append('files', fs.createReadStream(file.path), file.originalname);
    });
    formData.append('question', question);

    const response = await fetch('http://127.0.0.1:8000/api/ask', {
      method: 'POST',
      body: formData,
      headers: formData.getHeaders()
    });

    const data = await response.json();

    if (data.error) {
      console.error("Groq returned an error:", data.error);
      return "Sorry, an error occurred.";
    }

    console.log("=== Groq Answer ===", data.answer);
    return data.answer; //  Return it

  } catch (err) {
    console.error('Error sending files to Groq:', err.message);
    return "Sorry, could not connect to the AI service.";
  }
}

module.exports = router;