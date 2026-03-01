# IELTS Listening Test Platform

A Flask-based web application for IELTS listening test practice with audio playback, timed tests, and automatic grading.

## Features

- User registration and authentication
- Admin dashboard for test management
- Bulk question import via markdown format
- Audio playback with automatic timer start
- Real-time progress tracking
- Automatic test submission on timeout
- Detailed result analysis

## Deployment to Railway

### Prerequisites
- A Railway account (sign up at https://railway.app)
- Git installed on your machine

### Steps

1. **Initialize Git Repository** (if not already done)
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   ```

2. **Deploy to Railway**
   - Go to https://railway.app
   - Click "New Project"
   - Select "Deploy from GitHub repo" (or "Deploy from local repo")
   - Connect your GitHub account and select this repository
   - Railway will automatically detect the Flask app and deploy it

3. **Environment Variables** (Optional)
   Railway will automatically set the PORT variable. No additional configuration needed.

4. **Access Your App**
   - Once deployed, Railway will provide a URL (e.g., `your-app.railway.app`)
   - Default admin credentials:
     - Email: `admin@ielts.com`
     - Password: `admin123`

### Alternative: Deploy via Railway CLI

1. **Install Railway CLI**
   ```bash
   npm i -g @railway/cli
   ```

2. **Login to Railway**
   ```bash
   railway login
   ```

3. **Initialize and Deploy**
   ```bash
   railway init
   railway up
   ```

4. **Generate Domain**
   ```bash
   railway domain
   ```

## Local Development

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Application**
   ```bash
   python app.py
   ```

3. **Access Locally**
   - Open http://localhost:5000
   - Login with admin credentials above

## Bulk Question Import Format

```
1. What is the capital of France?
A) London
B) Berlin
C) Paris*
D) Madrid

2. Which planet is known as the Red Planet?
A) Venus
B) Mars*
C) Jupiter
D) Saturn
```

Mark the correct answer with an asterisk (*).

## Tech Stack

- Flask 3.0
- SQLite
- Bootstrap 5.3
- Vanilla JavaScript
