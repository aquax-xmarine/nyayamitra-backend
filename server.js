const express = require('express');
const https = require('https');
const http = require('http');
const fs = require('fs');
const cors = require('cors');
const cookieParser = require('cookie-parser');
const helmet = require('helmet');
require('dotenv').config();

const authRoutes = require('./routes/auth');
const userRoutes = require('./routes/user');

const app = express();

// Security middleware
app.use(helmet());

// CORS configuration
app.use(cors({
  origin: process.env.FRONTEND_URL || 'https://localhost:5173',
  credentials: true
}));

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(cookieParser());
app.use('/uploads', express.static('uploads'));

app.use('/api/auth', authRoutes);
app.use('/api/user', userRoutes);

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', message: 'Server is running with HTTPS' });
});

app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Something went wrong!' });
});

const PORT = process.env.PORT || 5000;

// Use HTTPS in development, HTTP in production (hosting platforms handle HTTPS)
if (process.env.NODE_ENV === 'development') {
  try {
    const options = {
      key: fs.readFileSync('./cert.key'),
      cert: fs.readFileSync('./cert.crt')
    };

    https.createServer(options, app).listen(PORT, () => {
      console.log(`🚀 HTTPS Server running on port ${PORT}`);
      console.log(`📍 Health check: https://localhost:${PORT}/api/health`);
      console.log(`🔒 Environment: ${process.env.NODE_ENV}`);
      console.log(`✅ SSL/TLS Encryption: ENABLED`);
    });
  } catch (error) {
    console.error('❌ Error loading SSL certificates:', error.message);
    console.log('⚠️ Falling back to HTTP...');
    
    http.createServer(app).listen(PORT, () => {
      console.log(`🚀 HTTP Server running on port ${PORT}`);
      console.log(`📍 Health check: http://localhost:${PORT}/api/health`);
    });
  }
} else {
  // Production: hosting platforms handle HTTPS
  app.listen(PORT, () => {
    console.log(`🚀 Server running on port ${PORT}`);
    console.log(`🔒 Environment: ${process.env.NODE_ENV}`);
  });
}