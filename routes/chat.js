const express = require('express');
const db = require('../db');
const authMiddleware = require('../middleware/auth'); // ADD THIS
const router = express.Router();

// Get all sessions for current user
router.get('/sessions', authMiddleware, async (req, res) => {
  try {
    const result = await db.query(
      `SELECT id, title, document_id, created_at 
       FROM chat_sessions 
       WHERE user_id = $1 
       ORDER BY created_at DESC`,
      [req.user.userId] // userId not id
    );
    res.json(result.rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch sessions' });
  }
});

// Create new session
router.post('/sessions', authMiddleware, async (req, res) => {
  const { title, document_id } = req.body;
  try {
    const result = await db.query(
      `INSERT INTO chat_sessions (user_id, title, document_id) 
       VALUES ($1, $2, $3) 
       RETURNING *`,
      [req.user.userId, title || 'New Chat', document_id || null] // userId not id
    );
    res.json(result.rows[0]);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to create session' });
  }
});

// Get messages for a session
router.get('/sessions/:id/messages', authMiddleware, async (req, res) => {
  try {
    const result = await db.query(
      `SELECT id, question, answer, created_at 
       FROM messages 
       WHERE session_id = $1 
       ORDER BY created_at ASC`,
      [req.params.id]
    );
    res.json(result.rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch messages' });
  }
});

// Save a question + answer pair
router.post('/sessions/:id/messages', authMiddleware, async (req, res) => {
  const { question, answer } = req.body;
  try {
    const result = await db.query(
      `INSERT INTO messages (session_id, question, answer) 
       VALUES ($1, $2, $3) 
       RETURNING *`,
      [req.params.id, question, answer || null]
    );

    // Auto-title session from first question
    await db.query(
      `UPDATE chat_sessions 
       SET title = CASE 
         WHEN title = 'New Chat' THEN LEFT($1, 50) 
         ELSE title 
       END
       WHERE id = $2`,
      [question, req.params.id]
    );

    res.json(result.rows[0]);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to save message' });
  }
});

// Delete a session
router.delete('/sessions/:id', authMiddleware, async (req, res) => {
  try {
    await db.query(
      `DELETE FROM chat_sessions WHERE id = $1 AND user_id = $2`,
      [req.params.id, req.user.userId] // userId not id
    );
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to delete session' });
  }
});

// Get document_id for a session
router.get('/sessions/:id/document', authMiddleware, async (req, res) => {
  try {
    const result = await db.query(
      `SELECT document_id FROM chat_sessions WHERE id = $1 AND user_id = $2`,
      [req.params.id, req.user.userId]
    );
    if (!result.rows.length) return res.status(404).json({ error: 'Session not found' });
    res.json({ document_id: result.rows[0].document_id });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch document_id' });
  }
});

router.get('/sessions/:id/files', authMiddleware, async (req, res) => {
  try {
    const session = await db.query(
      `SELECT document_id FROM chat_sessions WHERE id = $1 AND user_id = $2`,
      [req.params.id, req.user.userId]
    );
    if (!session.rows.length) return res.status(404).json({ error: 'Session not found' });

    const document_id = session.rows[0].document_id;
    if (!document_id) return res.json([]);

    const files = await db.query(
      `SELECT id, name, file_path, created_at 
   FROM files 
   WHERE session_id = $1 AND is_deleted = false`,
      [req.params.id]
    );
    res.json(files.rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch session files' });
  }
});

module.exports = router;