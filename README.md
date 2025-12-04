# Infi 1 Study Sync App

A smart syllabus application for tracking your Infi 1 course progress (Chapters 1-14) with automatic Google Calendar integration.

## Features

1. **Chapter Breakdown**: All 14 chapters of Infi 1 are broken down into trackable units with theorems and proofs
2. **Google Calendar Integration**: Automatically schedule study blocks for specific theorems
3. **Confidence Meter**: Rate your understanding (0-10) for each theorem/proof
4. **Automatic Review Scheduling**: If you rate confidence ≤ 3, the app automatically schedules a review session 3 days later

## Setup Instructions

### Prerequisites
- Python 3.7+
- Google Cloud account

### Installation

1. **Clone or download this project**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Google Calendar API**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Google Calendar API
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Choose "Web application"
   - Add authorized redirect URI: `http://localhost:5000/oauth2callback`
   - Download the JSON credentials file
   - Rename it to `client_secret.json` and place it in the project root

4. **Run the application**:
   ```bash
   python app.py
   ```

5. **Open your browser**:
   - Navigate to `http://localhost:5000`
   - Click "Authorize Google Calendar" to connect your account
   - Start tracking your studies!

## Usage

1. **View Chapters**: The home page shows all 14 chapters with statistics
2. **View Theorems**: Click on a chapter to see all theorems/proofs
3. **Rate Confidence**: Use the slider to rate your understanding (0-10) and click "Save Confidence"
4. **Schedule Study Sessions**: Set a date and time to schedule study blocks in your Google Calendar
5. **Automatic Reviews**: Low confidence ratings (≤3) automatically trigger review sessions 3 days later

## Database

The app uses SQLite (`study_sync.db`) to store:
- Chapters (1-14)
- Theorems/proofs for each chapter
- Confidence ratings
- Scheduled study sessions

## Project Structure

```
.
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── templates/            # HTML templates
│   ├── index.html        # Home page with chapters
│   ├── chapter.html      # Chapter detail page
│   └── setup.html        # Setup instructions
├── client_secret.json    # Google OAuth credentials (you need to add this)
└── study_sync.db         # SQLite database (created automatically)
```

## Notes

- The app runs on `http://localhost:5000` by default
- Your Google Calendar credentials are stored in the session (not persisted)
- All study sessions are added to your primary Google Calendar
- The database is initialized automatically on first run with sample data for chapters 1-14

## Security

For production use:
- Change the `SECRET_KEY` in `app.py` or set it as an environment variable
- Use proper session storage (not in-memory)
- Consider using a production WSGI server (e.g., Gunicorn)

