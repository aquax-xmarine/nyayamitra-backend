const pool = require('../db');

async function createRootContainersForNewUser(userId) {
  // Check if library root exists
  const existing = await pool.query(`
    SELECT section FROM containers WHERE user_id = $1 AND parent_id IS NULL
  `, [userId]);

  const existingSections = existing.rows.map(r => r.section);

  if (!existingSections.includes('library')) {
    await pool.query(`
      INSERT INTO containers (id, name, section, parent_id, user_id, created_at)
      VALUES (gen_random_uuid(), 'My Library', 'library', NULL, $1, NOW())
    `, [userId]);
  }

  if (!existingSections.includes('workingCases')) {
    await pool.query(`
      INSERT INTO containers (id, name, section, parent_id, user_id, created_at)
      VALUES (gen_random_uuid(), 'Current Working Cases', 'workingCases', NULL, $1, NOW())
    `, [userId]);
  }


  if (!existingSections.includes('trash')) {
    await pool.query(`
      INSERT INTO containers (id, name, section, parent_id, user_id, created_at)
      VALUES (gen_random_uuid(), 'Trash', 'trash', NULL, $1, NOW())
    `, [userId]);
  }


  // Bookmark
  if (!existingSections.includes('bookmark')) {
    await pool.query(`
      INSERT INTO containers (id, name, section, parent_id, user_id, created_at)
      VALUES (gen_random_uuid(), 'Bookmarks', 'bookmark', NULL, $1, NOW())
    `, [userId]);
  }

  // Recently Visited
  if (!existingSections.includes('recent')) {
    await pool.query(`
      INSERT INTO containers (id, name, section, parent_id, user_id, created_at)
      VALUES (gen_random_uuid(), 'Recently Visited', 'recent', NULL, $1, NOW())
    `, [userId]);
  }


}

module.exports = { createRootContainersForNewUser };