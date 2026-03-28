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




/**
 * MOVE container to another section (e.g., 'trash')
 */
router.patch('/:id/section', auth, async (req, res) => {
    const { id } = req.params;
    const { section } = req.body; // e.g., 'trash'
    const userId = req.user.userId;

    if (!section) {
        return res.status(400).json({ error: 'Section is required' });
    }

    try {
        const result = await db.query(
            `
            UPDATE containers
            SET section = $1
            WHERE id = $2 AND user_id = $3
            RETURNING id, name, parent_id, section
            `,
            [section, id, userId]
        );

        if (result.rowCount === 0) {
            return res.status(404).json({ error: 'Container not found or not owned by user' });
        }

        res.json(result.rows[0]);
    } catch (err) {
        console.error('Move container error:', err);
        res.status(500).json({ error: 'Failed to move container' });
    }
});



/**
 * UPDATE container parent_id
 */
router.patch('/:id/parent', auth, async (req, res) => {
  const { id } = req.params;
  const { parent_id } = req.body;
  const userId = req.user.userId;

  if (!parent_id) {
    return res.status(400).json({ error: 'parent_id is required' });
  }

  try {
    const result = await db.query(
      `
      UPDATE containers
      SET parent_id = $1
      WHERE id = $2 AND user_id = $3
      RETURNING id, name, parent_id, section
      `,
      [parent_id, id, userId]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({ error: 'Container not found or not owned by user' });
    }

    res.json(result.rows[0]);
  } catch (err) {
    console.error('Update container parent error:', err);
    res.status(500).json({ error: 'Failed to update container parent' });
  }
});




router.post('/:id/save-original-location', auth, async (req, res) => {
    const { id } = req.params;
    const userId = req.user.userId;

    try {
        // Get container and all its descendants using recursive CTE
        await db.query(
            `
            WITH RECURSIVE subcontainers AS (
                SELECT id, section, parent_id
                FROM containers
                WHERE id = $1 AND user_id = $2

                UNION ALL

                SELECT c.id, c.section, c.parent_id
                FROM containers c
                INNER JOIN subcontainers sc ON c.parent_id = sc.id
                WHERE c.user_id = $2
            )
            UPDATE containers
            SET original_section = section,
                original_parent_id = parent_id
            WHERE id IN (SELECT id FROM subcontainers)
            `,
            [id, userId]
        );

        res.json({ success: true });
    } catch (err) {
        console.error('Save original location failed:', err);
        res.status(500).json({ error: 'Failed to save original location' });
    }
});


// GET original section
router.get('/:id/original-section', auth, async (req, res) => {
  const { id } = req.params;
  const userId = req.user.userId;

  try {
    const result = await db.query(
      `SELECT original_section FROM containers WHERE id = $1 AND user_id = $2`,
      [id, userId]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({ error: 'Container not found' });
    }

    res.json({ section: result.rows[0].original_section });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch original section' });
  }
});

// GET original parent
router.get('/:id/original-parent', auth, async (req, res) => {
  const { id } = req.params;
  const userId = req.user.userId;

  try {
    const result = await db.query(
      `SELECT original_parent_id FROM containers WHERE id = $1 AND user_id = $2`,
      [id, userId]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({ error: 'Container not found' });
    }

    res.json({ parent_id: result.rows[0].original_parent_id });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch original parent' });
  }
});







module.exports = router;
