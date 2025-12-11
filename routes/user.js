const express = require('express');
const router = express.Router();
const pool = require('../db');
const authMiddleware = require('../middleware/auth');
const multer = require('multer');
const path = require('path');

const storage = multer.diskStorage({
  destination: './uploads/',
  filename: (req, file, cb) => {
    cb(null, `profile-${req.user.userId}-${Date.now()}${path.extname(file.originalname)}`);
  }
});

const upload = multer({
  storage: storage,
  limits: { fileSize: 5000000 },
  fileFilter: (req, file, cb) => {
    const filetypes = /jpeg|jpg|png|gif/;
    const extname = filetypes.test(path.extname(file.originalname).toLowerCase());
    const mimetype = filetypes.test(file.mimetype);

    if (mimetype && extname) {
      return cb(null, true);
    } else {
      cb('Error: Images only!');
    }
  }
});

// Update profile
router.put('/profile', authMiddleware, async (req, res) => {
  try {
    const { name, email } = req.body;
    const userId = req.user.userId;

    if (email) {
      const emailExists = await pool.query(
        'SELECT * FROM users WHERE email = $1 AND user_id != $2',
        [email, userId]
      );

      if (emailExists.rows.length > 0) {
        return res.status(400).json({ error: 'Email already in use' });
      }
    }

    const updatedUser = await pool.query(
      'UPDATE users SET name = COALESCE($1, name), email = COALESCE($2, email) WHERE user_id = $3 RETURNING user_id, email, name, profile_picture',
      [name, email, userId]
    );

    res.json({
      message: 'Profile updated successfully',
      user: updatedUser.rows[0]
    });
  } catch (error) {
    console.error('Update profile error:', error);
    res.status(500).json({ error: 'Server error' });
  }
});


// Endpoint 2: Used by Onboarding page (NEW - Add this)
router.put('/display-name', authMiddleware, async (req, res) => {
  try {
    const { displayName } = req.body;
    const userId = req.user.userId;

    console.log('Updating name for user:', userId, 'to:', displayName);

    // Validate
    if (!displayName || displayName.trim().length === 0) {
      return res.status(400).json({
        success: false,
        message: 'Name is required'
      });
    }

    if (displayName.trim().length > 50) {
      return res.status(400).json({
        success: false,
        message: 'Name must be less than 50 characters'
      });
    }

    // Update the name field (same as /profile endpoint)
    const result = await pool.query(
      'UPDATE users SET name = $1 WHERE user_id = $2 RETURNING user_id, email, name, profile_picture',
      [displayName.trim(), userId]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        message: 'User not found'
      });
    }

    console.log('Name updated successfully');

    res.json({
      success: true,
      message: 'Name updated successfully',
      displayName: displayName.trim(),
      user: result.rows[0]
    });
  } catch (error) {
    console.error('Error updating name:', error);
    res.status(500).json({
      success: false,
      message: 'Server error while updating name',
      error: error.message
    });
  }
});


// Upload profile picture
router.post('/profile/picture', authMiddleware, upload.single('profilePicture'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No file uploaded' });
    }

    const profilePicturePath = `/uploads/${req.file.filename}`;

    const updatedUser = await pool.query(
      'UPDATE users SET profile_picture = $1 WHERE user_id = $2 RETURNING user_id, email, name, profile_picture',
      [profilePicturePath, req.user.userId]
    );

    res.json({
      message: 'Profile picture updated successfully',
      user: updatedUser.rows[0]
    });
  } catch (error) {
    console.error('Upload picture error:', error);
    res.status(500).json({ error: 'Server error' });
  }
});

module.exports = router;