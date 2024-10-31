# YouTube Video Analyzer

A Streamlit application to analyze YouTube videos and find potential hooks for advertising creatives.

## Features

- Search YouTube videos with flexible criteria
- Analyze video performance metrics
- Identify potential hook segments
- Filter by duration and sort options
- Secure API key handling

## Setup

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/yourusername/youtube-video-analyzer.git
cd youtube-video-analyzer
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install requirements:
```bash
pip install -r requirements.txt
```

4. Set up your environment:
   - Copy `.env.template` to `.env`
   - Add your YouTube API key to `.env`

5. Run the app:
```bash
streamlit run app.py
```

### Streamlit Cloud Deployment

1. Fork this repository
2. Go to [Streamlit Cloud](https://streamlit.io/cloud)
3. Deploy from your GitHub repository
4. In Streamlit Cloud settings, add your `youtube_api_key` secret

## Getting a YouTube API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable YouTube Data API v3
4. Create credentials (API key)
5. Copy the API key to use in the app

## Security Notes

- Never commit API keys to the repository
- Use environment variables or Streamlit secrets
- Each user should use their own API key
- Monitor API quota usage

## Usage

1. Enter your YouTube API key
2. Input search query
3. Select duration and sorting options
4. Click "Search Videos"
5. Analyze results and hook segments

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License - see LICENSE file for details
