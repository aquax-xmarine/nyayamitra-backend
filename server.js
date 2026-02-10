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
const lawyerRoutes = require('./routes/lawyer');
const askRoutes = require('./routes/ask');
const containerRoutes = require('./routes/containers');
const fileRoutes = require('./routes/files');
const path = require('path');

const app = express();

app.use((req, res, next) => {
  res.setHeader(
    'Content-Security-Policy',
    "frame-ancestors 'self' https://localhost:5173 http://localhost:5173"
  );
  next();
});

// IMPORTANT: Disable helmet's crossOriginResourcePolicy for images
app.use(
  helmet({
    crossOriginResourcePolicy: false,
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        frameAncestors: [
          "'self'",
          'https://localhost:5173',
          'http://localhost:5173',
        ],
      },
    },
  })
);

// CORS configuration - Allow your frontend
const allowedOrigins = [
  'https://localhost:5173',
  'http://localhost:5173',
  process.env.FRONTEND_URL
].filter(Boolean);

const corsOptions = {
  origin: function (origin, callback) {
    // Allow requests with no origin (like mobile apps, curl, Postman)
    if (!origin) return callback(null, true);

    if (allowedOrigins.indexOf(origin) !== -1) {
      callback(null, true);
    } else {
      callback(null, true); // Allow all origins for now to debug
    }
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
  allowedHeaders: ['Content-Type', 'Authorization', 'Cookie']
};

app.use(cors(corsOptions));

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(cookieParser());
app.use('/api/ask', askRoutes);



app.use('/api/auth', authRoutes);
app.use('/api/user', userRoutes);
app.use('/api/lawyer', lawyerRoutes);

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', message: 'Server is running with HTTPS' });
});

app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Something went wrong!' });
});

app.use('/api/containers', containerRoutes);
app.use('/api/files', fileRoutes);

app.use(
  '/uploads',
  express.static(path.join(__dirname, 'uploads'), {
    setHeaders: (res, filePath) => {
      if (filePath.endsWith('.pdf')) {
        res.setHeader('Content-Type', 'application/pdf');
        res.setHeader('Content-Disposition', 'inline');
      }
    },
  })
);


const PORT = process.env.PORT || 5000;

// Use HTTPS in development, HTTP in production (hosting platforms handle HTTPS)
if (process.env.NODE_ENV === 'development') {
  try {
    const options = {
      key: fs.readFileSync('./cert.key'),
      cert: fs.readFileSync('./cert.crt')
    };

    https.createServer(options, app).listen(PORT, () => {
      console.log(`HTTPS Server running on port ${PORT}`);
      console.log(`Health check: https://localhost:${PORT}/api/health`);
      console.log(`Environment: ${process.env.NODE_ENV}`);
      console.log(`SSL/TLS Encryption: ENABLED`);
    });
  } catch (error) {
    console.error('Error loading SSL certificates:', error.message);
    console.log('Falling back to HTTP...');

    http.createServer(app).listen(PORT, () => {
      console.log(`HTTP Server running on port ${PORT}`);
      console.log(`Health check: http://localhost:${PORT}/api/health`);
    });
  }
} else {
  // Production: hosting platforms handle HTTPS
  app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
    console.log(`Environment: ${process.env.NODE_ENV}`);
  });
}