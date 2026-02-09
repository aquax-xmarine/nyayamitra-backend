const express = require('express');
const router = express.Router();
const db = require('../db');
const auth = require('../middleware/auth');

/**
 * GET containers by section (USER-SCOPED)
 */
router.get('/', auth, async (req, res, next) => {
    try {
        const { section } = req.query;


        const user_id = req.user.userId;;

        if (!section) {
            return res.status(400).json({ error: 'section is required' });
        }

        const result = await db.query(
            `
      SELECT id, name, parent_id, section
      FROM containers
      WHERE section = $1
        AND user_id = $2
      ORDER BY created_at
      `,
            [section, user_id]
        );

        res.json(result.rows);
    } catch (err) {
        next(err);
    }
});

/**
 * CREATE container
 */
router.post('/', auth, async (req, res, next) => {
    try {
        console.log('REQ.USER:', req.user);
        const { name, section, parent_id } = req.body;
        const user_id = req.user.userId;;

        const result = await db.query(
            `
      INSERT INTO containers (name, section, parent_id, user_id)
      VALUES ($1, $2, $3, $4)
      RETURNING id, name, section, parent_id
      `,
            [name, section, parent_id || null, user_id]
        );

        res.json(result.rows[0]);
    } catch (err) {
        next(err);
    }
});


/**
 * RENAME container
 */
router.patch('/:id', auth, async (req, res) => {
    const { id } = req.params;
    const { name } = req.body;
    const userId = req.user.userId;

    console.log('PATCH /containers/:id', { id, name, userId });

    if (!name || !name.trim()) {
        return res.status(400).json({ error: 'Name is required' });
    }

    try {
        const result = await db.query(
            `
      UPDATE containers
      SET name = $1
      WHERE id = $2 AND user_id = $3
      RETURNING id, name, parent_id, section
      `,
            [name.trim(), id, userId]
        );

        if (result.rowCount === 0) {
            return res.status(404).json({ error: 'Container not found' });
        }

        res.json(result.rows[0]);
    } catch (err) {
        console.error('Rename container error:', err);
        res.status(500).json({ error: 'Failed to rename container' });
    }
});







module.exports = router;
