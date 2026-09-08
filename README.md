# 🚛 Fill-It-Web - Smart Logistics Platform

> *Revolutionizing the logistics industry with a modern, multi-role transportation platform*

[![Firebase](https://img.shields.io/badge/Firebase-Hosted-orange?logo=firebase)](https://firebase.google.com/)
[![HTML5](https://img.shields.io/badge/HTML5-Valid-brightgreen?logo=html5)](https://developer.mozilla.org/en-US/docs/Web/HTML)
[![CSS3](https://img.shields.io/badge/CSS3-Modern-blue?logo=css3)](https://developer.mozilla.org/en-US/docs/Web/CSS)
[![JavaScript](https://img.shields.io/badge/JavaScript-ES6+-yellow?logo=javascript)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [User Roles](#user-roles)
- [API Endpoints](#api-endpoints)
- [Environment Variables](#environment-variables)
- [Contributing](#contributing)

## 🎯 Overview

*Fill-It-Web* is a comprehensive logistics and transportation platform that connects customers with trusted drivers for seamless goods transportation. Built with modern web technologies, it provides a robust solution for managing trips, tracking shipments, and facilitating communication between all stakeholders in the logistics ecosystem.

### 🌟 Key Highlights

- *Multi-Role Platform*: Separate interfaces for customers and drivers
- *Real-time Tracking*: Live trip monitoring and status updates
- *Secure Authentication*: Firebase Auth
- *Responsive Design*: Optimized for all devices and screen sizes

## ✨ Features

### 👤 Authentication System
- *Dual Login Methods*: Email/password 
- *Role-based Registration*: Separate signup flows for customers and drivers
- *Email Verification*: Secure account activation process

### 🚚 Customer Dashboard
- *Trip Booking*: Interactive map-based location selection
- *Trip History*: Comprehensive booking history with details
- *Profile Management*: Edit personal information and preferences

### 🚛 Driver Dashboard
- *Trip Discovery*: Search and filter available trips
- *Booking Management*: Accept, complete, and release trips

## 🛠 Technology Stack

### Frontend
- *HTML5*: Semantic markup and accessibility
- *CSS3*: Modern styling with CSS Grid and Flexbox
- *JavaScript (ES6+)*: Vanilla JS with modern features
- *Firebase Hosting*: Frontend hosting

### Backend
- *Python FastAPI*: High-performance REST API
- *Firebase Authentication*: User identity and token verification
- *Firestore*: User profiles and metadata
- *Firebase Realtime Database (RTDB)*: Real-time trip status and location tracking
- *Google Maps Geocoding API*: Geolocation and routing coordinates
- *APScheduler*: Background cron jobs for trip lifecycle
- *Resend*: Transactional email service

## 🏗 Architecture

The backend implements a clear separation of concerns using FastAPI:
- `dependencies.py`: Reusable authentication and authorization dependencies (`get_current_user`, `require_customer`, `require_driver`).
- `c_book.py`, `c_triphistory.py`: Customer-only endpoints.
- `d_book.py`: Driver-only endpoints.
- `regret_scheduler.py`: Scheduled job to move expired pending trips to a `regret` state.
- `main.py`: Central FastAPI app with global exception handling and CORS.

### Concurrency and Geolocation
- **Geolocation optimization**: Geocoding is performed exactly once upon trip creation, storing `from_lat` and `from_lon`. Driver search performs local Haversine distance calculations without repeating external API calls.
- **Race Condition Prevention**: RTDB Transactions are used when drivers accept trips to ensure exactly one driver can claim a given trip at a time.

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- Firebase Project Credentials

### Installation

1. *Clone the repository*  
   ```bash
   git clone https://github.com/Mahaprasadnanda/FILL-IT.git
   cd FILL-IT
   ```

2. *Install dependencies*  
   ```bash
   pip install -r requirements.txt
   ```

3. *Run the server*  
   ```bash
   uvicorn main:app --reload
   ```

## 🔌 API Endpoints

### Authentication
- `POST /login` - User authentication
- `POST /signup` - User registration
- `POST /refresh-token` - Refresh JWT token

### Customer Endpoints
- `POST /book-trip` - Create new trip
- `GET /get-trip-history` - Fetch customer trip history
- `PUT /edit-trip/{id}` - Update a pending trip
- `DELETE /delete-trip/{id}` - Cancel a pending trip

### Driver Endpoints
- `POST /api/driver/search_trips` - Find nearby pending trips
- `POST /api/driver/accept_trip` - Accept a pending trip
- `POST /api/driver/complete_trip` - Complete an assigned trip
- `POST /api/driver/release_trip` - Release an assigned trip back to pending
- `GET /api/driver/assigned_trips` - Get currently assigned trips

## 🌐 Environment Variables

Configure the following environment variables (e.g., in a `.env` file):

```env
FIREBASE_API_KEY=your_firebase_api_key
RTDB_URL=https://your-project.firebasedatabase.app/
GOOGLE_MAPS_API_KEY=your_google_maps_key
RESEND_API_KEY=your_resend_api_key
SESSION_SECRET_KEY=secure_random_string
```
Also ensure `serviceAccountKey.json` is present at the root for Firebase Admin SDK initialization.

## 🤝 Contributing

We welcome contributions! Please open a pull request.
