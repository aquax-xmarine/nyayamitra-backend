// routes/lawyer.js
const express = require('express');
const router = express.Router();
const pool = require('../db'); // You'll need to create this

// Get all provinces
router.get('/provinces', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM provinces ORDER BY province_name');
    res.json(result.rows);
  } catch (err) {
    console.error('Error fetching provinces:', err);
    res.status(500).json({ error: 'Failed to fetch provinces' });
  }
});

// Get districts by province
router.get('/districts/:provinceId', async (req, res) => {
  try {
    const { provinceId } = req.params;
    const result = await pool.query(
      'SELECT * FROM districts WHERE province_id = $1 ORDER BY district_name',
      [provinceId]
    );
    res.json(result.rows);
  } catch (err) {
    console.error('Error fetching districts:', err);
    res.status(500).json({ error: 'Failed to fetch districts' });
  }
});

// Get all practice areas
router.get('/practice-areas', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM practice_areas ORDER BY area_name');
    res.json(result.rows);
  } catch (err) {
    console.error('Error fetching practice areas:', err);
    res.status(500).json({ error: 'Failed to fetch practice areas' });
  }
});

// Get high court for a district
router.get('/high-court/:districtName', async (req, res) => {
  try {
    const { districtName } = req.params;
    const result = await pool.query(
      'SELECT get_high_court_for_district($1) as high_court',
      [districtName]
    );
    res.json({ high_court: result.rows[0]?.high_court });
  } catch (err) {
    console.error('Error fetching high court:', err);
    res.status(500).json({ error: 'Failed to fetch high court' });
  }
});

// Get lawyer profile (assumes user is authenticated)
router.get('/profile', async (req, res) => {
  try {
    const userId = req.user?.id; // Assuming you have auth middleware
    if (!userId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const result = await pool.query(
      'SELECT id, practice_area, nba_number, primary_province, primary_district, practices_in_high_court, practices_in_supreme_court FROM users WHERE id = $1',
      [userId]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Profile not found' });
    }

    res.json(result.rows[0]);
  } catch (err) {
    console.error('Error fetching profile:', err);
    res.status(500).json({ error: 'Failed to fetch profile' });
  }
});

// Get lawyer profile by ID
router.get('/profile/:userId', async (req, res) => {
  try {
    const { userId } = req.params;
    const result = await pool.query(
      'SELECT id, practice_area, nba_number, primary_province, primary_district, practices_in_high_court, practices_in_supreme_court FROM users WHERE id = $1',
      [userId]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Profile not found' });
    }

    res.json(result.rows[0]);
  } catch (err) {
    console.error('Error fetching profile:', err);
    res.status(500).json({ error: 'Failed to fetch profile' });
  }
});

// Update lawyer profile
router.put('/profile', async (req, res) => {
  try {
    const userId = req.user?.id; // From auth middleware
    if (!userId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const {
      practice_area,
      nba_number,
      primary_province,
      primary_district,
      practices_in_high_court,
      practices_in_supreme_court,
    } = req.body;

    // Validation
    if (!practice_area || !nba_number || !primary_province || !primary_district) {
      return res.status(400).json({ error: 'Missing required fields' });
    }

    const result = await pool.query(
      `UPDATE users SET 
        practice_area = $1,
        nba_number = $2,
        primary_province = $3,
        primary_district = $4,
        practices_in_high_court = $5,
        practices_in_supreme_court = $6,
        updated_at = CURRENT_TIMESTAMP
      WHERE id = $7
      RETURNING id, practice_area, nba_number, primary_province, primary_district, practices_in_high_court, practices_in_supreme_court`,
      [
        practice_area,
        nba_number,
        primary_province,
        primary_district,
        practices_in_high_court || false,
        practices_in_supreme_court || false,
        userId,
      ]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'User not found' });
    }

    res.json(result.rows[0]);
  } catch (err) {
    console.error('Error updating profile:', err);
    res.status(500).json({ error: 'Failed to update profile' });
  }
});

// Search lawyers by district and practice area
router.get('/search', async (req, res) => {
  try {
    const { district, practiceArea } = req.query;

    if (!district && !practiceArea) {
      return res.status(400).json({ error: 'Provide district or practiceArea' });
    }

    let query = 'SELECT id, practice_area, nba_number, primary_province, primary_district FROM users WHERE 1=1';
    const params = [];

    if (district) {
      query += ` AND primary_district = $${params.length + 1}`;
      params.push(district);
    }

    if (practiceArea) {
      query += ` AND practice_area = $${params.length + 1}`;
      params.push(practiceArea);
    }

    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch (err) {
    console.error('Error searching lawyers:', err);
    res.status(500).json({ error: 'Search failed' });
  }
});

module.exports = router;