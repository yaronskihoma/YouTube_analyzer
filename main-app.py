import streamlit as st
import os
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import isodate
import pytz
from config import get_api_key, validate_api_key

class YouTubeLiteAnalyzer:
    def __init__(self, api_key: str):
        """Initialize YouTube API client."""
        self.youtube = build('youtube', 'v3', developerKey=api_key)
        self.region = 'US'
        
        self.duration_ranges = {
            'short': 'short',
            'medium': 'medium',
            'long': 'long',
            'any': None
        }

    def analyze_videos(self, query: str, max_results: int = 5, 
                      duration_type: str = 'any',
                      order_by: str = 'viewCount') -> list:
        """Search and analyze videos."""
        try:
            # Calculate date 5 days ago
            five_days_ago = (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%dT%H:%M:%SZ')
            
            # Search parameters
            search_params = {
                'q': query,
                'type': 'video',
                'part': 'id',
                'maxResults': max_results,
                'order': order_by,
                'regionCode': self.region,
                'publishedAfter': five_days_ago
            }
            
            if duration_type != 'any':
                search_params['videoDuration'] = self.duration_ranges[duration_type]

            with st.spinner('Searching videos...'):
                search_response = self.youtube.search().list(**search_params).execute()

                if not search_response.get('items'):
                    st.warning("No videos found")
                    return []

                video_ids = [item['id']['videoId'] for item in search_response['items']]
                
                # Get detailed video information
                videos_response = self.youtube.videos().list(
                    part='snippet,statistics,contentDetails',
                    id=','.join(video_ids)
                ).execute()

            analyzed_videos = []
            for video in videos_response['items']:
                # Basic video info
                duration_str = video['contentDetails']['duration']
                duration_sec = isodate.parse_duration(duration_str).total_seconds()
                
                view_count = int(video['statistics'].get('viewCount', 0))
                like_count = int(video['statistics'].get('likeCount', 0))
                
                publish_date = datetime.strptime(
                    video['snippet']['publishedAt'], 
                    '%Y-%m-%dT%H:%M:%SZ'
                ).replace(tzinfo=pytz.UTC)
                
                days_since_publish = (datetime.now(pytz.UTC) - publish_date).days
                
                # Compile video data
                video_data = {
                    'title': video['snippet']['title'],
                    'video_id': video['id'],
                    'url': f"https://www.youtube.com/watch?v={video['id']}",
                    'view_count': view_count,
                    'like_count': like_count,
                    'engagement_rate': round((like_count / view_count * 100), 2) if view_count > 0 else 0,
                    'duration': {
                        'seconds': duration_sec,
                        'formatted': str(timedelta(seconds=int(duration_sec)))
                    },
                    'days_since_publish': days_since_publish,
                    'views_per_day': round(view_count / max(days_since_publish, 1)),
                    'tags': video['snippet'].get('tags', []),
                    'channel_title': video['snippet']['channelTitle']
                }
                
                # Add hooks
                video_data['hooks'] = self._find_hooks(video_data, video['snippet']['description'])
                analyzed_videos.append(video_data)

            return analyzed_videos
            
        except Exception as e:
            st.error(f"Error in video analysis: {str(e)}")
            return []

    def _find_hooks(self, video_data: dict, description: str) -> list:
        """Identify potential hook segments in the video."""
        hooks = []
        
        # Add opening hook
        hooks.append({
            'type': 'opening',
            'start_time': 0,
            'duration': 5,
            'url': f"{video_data['url']}&t=0s"
        })
        
        # Parse description for timestamps
        for line in description.split('\n'):
            if ':' in line and any(char.isdigit() for char in line):
                try:
                    # Extract timestamp
                    time_part = line.split(' ')[0]
                    if ':' in time_part:
                        time_parts = time_part.split(':')
                        seconds = sum(x * int(t) for x, t in zip([3600, 60, 1], time_parts[-3:]))
                        
                        if seconds > 10 and seconds < video_data['duration']['seconds'] - 5:
                            hooks.append({
                                'type': 'segment',
                                'start_time': seconds,
                                'duration': 5,
                                'title': ' '.join(line.split(' ')[1:]).strip(),
                                'url': f"{video_data['url']}&t={seconds}s"
                            })
                except:
                    continue
        
        return hooks

def main():
    st.set_page_config(
        page_title="YouTube Video Analyzer",
        page_icon="🎥",
        layout="wide"
    )
    
    st.title("🎥 YouTube Video Analyzer")
    
    # API Key handling
    api_key = st.session_state.get('api_key', '')
    
    with st.sidebar:
        st.header("Settings")
        new_api_key = st.text_input("Enter YouTube API Key", 
                                   value=api_key,
                                   type="password",
                                   help="Your YouTube Data API v3 key")
        
        if new_api_key != api_key:
            if validate_api_key(new_api_key):
                st.session_state.api_key = new_api_key
                st.success("API Key validated!")
            else:
                st.error("Invalid API Key")
                st.stop()
    
    if not api_key:
        st.warning("Please enter your YouTube API Key in the sidebar")
        st.info("Don't have an API Key? [Get one here](https://console.cloud.google.com/apis/credentials)")
        st.stop()
    
    try:
        analyzer = YouTubeLiteAnalyzer(api_key)
        
        # Search parameters
        query = st.text_input("🔍 Enter search query (e.g., 'mobile game ads')")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            duration_type = st.selectbox(
                "Duration",
                ["any", "short", "medium", "long"],
                format_func=lambda x: {
                    "any": "Any duration",
                    "short": "Short (< 4 minutes)",
                    "medium": "Medium (4-20 minutes)",
                    "long": "Long (> 20 minutes)"
                }[x]
            )
            
        with col2:
            order_by = st.selectbox(
                "Sort By",
                ["viewCount", "rating", "relevance", "date"],
                format_func=lambda x: x.title()
            )
        
        with col3:
            max_results = st.slider("Number of results", 1, 10, 5)
        
        if st.button("🔎 Search Videos", type="primary"):
            if not query:
                st.error("Please enter a search query")
                return
            
            videos = analyzer.analyze_videos(
                query=query,
                max_results=max_results,
                duration_type=duration_type,
                order_by=order_by
            )
            
            if videos:
                st.session_state.last_results = videos
                
                # Display results
                for video in videos:
                    with st.expander(f"📺 {video['title']}", expanded=True):
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            st.markdown(f"""
                            **Channel:** {video['channel_title']}  
                            **Duration:** {video['duration']['formatted']}  
                            **Views:** {video['view_count']:,} ({video['views_per_day']:,} per day)  
                            **Engagement Rate:** {video['engagement_rate']}%  
                            """)
                            
                            if video['tags']:
                                st.write("**Tags:**", ", ".join(video['tags'][:5]))
                        
                        with col2:
                            st.markdown(f"[🔗 Open Video]({video['url']})")
                        
                        st.write("**Potential Hooks:**")
                        for hook in video['hooks']:
                            st.markdown(
                                f"- **{hook['type'].title()}**\n"
                                f"  - Start Time: {hook['start_time']} seconds\n"
                                f"  - [Watch Segment]({hook['url']})"
                            )
            else:
                st.warning("No videos found matching your criteria")

    except Exception as e:
        st.error(f"Error: {str(e)}")
        st.error("Please check if your API key is valid and you have quota remaining")

if __name__ == "__main__":
    main()
