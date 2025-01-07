import streamlit as st
import os
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import isodate
import pytz
from typing import List, Dict
import re
from collections import Counter
import requests

def get_api_key() -> str:
    """Read API key from Streamlit secrets or environment."""
    try:
        return st.secrets["youtube_api_key"]
    except:
        return os.getenv("YOUTUBE_API_KEY", "")

class YouTubeLiteAnalyzer:
    def __init__(self, api_key: str):
        """Initialize YouTube API client with enhanced configuration."""
        self.youtube = build('youtube', 'v3', developerKey=api_key)
        self.regions = {
            'US': 'United States',
            'GB': 'United Kingdom',
            'CA': 'Canada',
            'AU': 'Australia',
            'BR': 'Brazil',
            'PH': 'Philippines',
            'IN': 'India',
            'DE': 'Germany',
            'FR': 'France',
            'JP': 'Japan'
        }
        self.duration_ranges = {
            'short': 'short',        # < 4 minutes
            'medium': 'medium',      # 4-20 minutes
            'long': 'long',         # > 20 minutes
            'any': None             # Any duration
        }
        
        # Engagement indicators for better segment detection
        self.engagement_indicators = [
            'highlight', 'best', 'top', 'important', 'key', 'main',
            'crucial', 'must see', 'amazing', 'awesome', 'perfect',
            'favorite', 'best part', 'dont miss', "don't miss",
            'watch this', 'check out', 'look at'
        ]

    def calculate_quota_cost(self, max_results: int) -> dict:
        """Calculate estimated API quota usage with comment analysis."""
        search_cost = 100
        video_details_cost = 1
        comments_cost = 1
        captions_cost = 50  # Cost for caption retrieval
        
        total_video_costs = video_details_cost * max_results
        total_comments_costs = comments_cost * max_results
        total_captions_costs = captions_cost * max_results
        
        total_cost = search_cost + total_video_costs + total_comments_costs + total_captions_costs
        
        return {
            'search_cost': search_cost,
            'video_details_cost': total_video_costs,
            'comments_cost': total_comments_costs,
            'captions_cost': total_captions_costs,
            'total_cost': total_cost,
            'daily_limit': 10000,
            'remaining_after': 10000 - total_cost
        }

    def _get_engagement_metrics(self, video_id: str) -> List[Dict]:
        """Get engagement metrics for video segments from comments."""
        try:
            engagement_data = []
            
            # Get comments
            comments_response = self.youtube.commentThreads().list(
                part='snippet',
                videoId=video_id,
                maxResults=100,
                order='relevance'
            ).execute()

            # Process timestamps from comments
            timestamp_pattern = r'(\d+h)?(\d+m)?(\d+s)?|(\d+:)?(\d+):(\d+)'
            timestamp_counts = Counter()
            
            for item in comments_response.get('items', []):
                comment = item['snippet']['topLevelComment']['snippet']['textDisplay'].lower()
                matches = re.finditer(timestamp_pattern, comment)
                
                for match in matches:
                    try:
                        parts = match.group().split(':')
                        seconds = sum(x * int(t) for x, t in zip([3600, 60, 1], parts[-3:]))
                        timestamp_counts[seconds] += 1
                    except:
                        continue
            
            # Convert timestamp counts to engagement data
            if timestamp_counts:
                max_count = max(timestamp_counts.values())
                for timestamp, count in timestamp_counts.most_common(10):
                    engagement_data.append({
                        'start_time': timestamp,
                        'frequency': count,
                        'relevance_score': count / max_count,
                        'source': 'comments'
                    })
            
            return engagement_data
            
        except Exception as e:
            st.warning(f"Error getting engagement metrics: {str(e)}")
            return []

    def _get_most_replayed_segments(self, video_id: str) -> List[Dict]:
        """Fetch most replayed segments for a YouTube video."""
        try:
            # Fetch the video's webpage
            url = f"https://www.youtube.com/watch?v={video_id}"
            response = requests.get(url)
            response.raise_for_status()

            # Check if heatmap data exists in the HTML
            if 'heatmap=' not in response.text:
                st.warning(f"No heatmap data found for video {video_id}.")
                return []

            # Extract heatmap data
            heatmap_data = response.text.split('heatmap=')[1].split(';')[0]

            # Safely evaluate the heatmap data
            try:
                heatmap_data = eval(heatmap_data)  # Convert string to dictionary
            except Exception as e:
                st.warning(f"Error parsing heatmap data for video {video_id}: {str(e)}")
                return []

            # Process heatmap data
            segments = []
            for segment in heatmap_data:
                segments.append({
                    'start_time': segment['start'],
                    'end_time': segment['end'],
                    'intensity': segment['intensity']
                })

            return segments
        except Exception as e:
            st.warning(f"Error fetching most replayed segments: {str(e)}")
            return []

    def _analyze_segments(self, video_data: Dict, query_keywords: List[str]) -> Dict:
        """Analyze segments using comments, description, and most replayed data."""
        hooks = {
            'comments': [],
            'description': [],
            'most_replayed': []
        }
        search_terms = set(word.lower() for word in query_keywords)
        
        # Get engagement-based segments from comments
        engagement_segments = self._get_engagement_metrics(video_data['video_id'])
        for segment in engagement_segments:
            hooks['comments'].append({
                'start_time': segment['start_time'],
                'duration': 5,
                'url': f"{video_data['url']}&t={int(segment['start_time'])}s",
                'relevance_score': segment['relevance_score'],
                'segment_type': 'user_engagement',
                'title': f"Popular Segment (mentioned {segment['frequency']} times)"
            })
        
        # Parse description for chapters
        description_lines = video_data.get('description', '').split('\n')
        chapters = []
        
        for line in description_lines:
            if ':' in line and any(char.isdigit() for char in line):
                try:
                    parts = line.split(' ', 1)
                    if len(parts) < 2:
                        continue
                        
                    time_str, title = parts
                    if ':' not in time_str:
                        continue
                    
                    time_parts = time_str.split(':')
                    seconds = sum(x * int(t) for x, t in zip([3600, 60, 1], time_parts[-3:]))
                    
                    if seconds >= video_data['duration']['seconds']:
                        continue
                    
                    # Relevance scoring
                    title_lower = title.lower()
                    title_words = set(title_lower.split())
                    matching_words = search_terms.intersection(title_words)
                    relevance_score = len(matching_words) / len(search_terms) if search_terms else 0.5
                    
                    # Engagement detection
                    engagement_score = sum(1 for indicator in self.engagement_indicators if indicator in title_lower)
                    engagement_boost = (engagement_score / len(self.engagement_indicators)) * 0.3
                    
                    # Combined scoring
                    final_score = relevance_score + engagement_boost
                    
                    chapters.append({
                        'start_time': seconds,
                        'title': title.strip(),
                        'relevance_score': final_score,
                        'segment_type': 'keyword_match',
                        'duration': 5,
                        'url': f"{video_data['url']}&t={int(seconds)}s"
                    })
                    
                except Exception as e:
                    continue
        
        hooks['description'] = sorted(chapters, key=lambda x: x['relevance_score'], reverse=True)[:5]
        
        # Get most replayed segments
        most_replayed_segments = self._get_most_replayed_segments(video_data['video_id'])
        hooks['most_replayed'] = most_replayed_segments
        
        return hooks

    def analyze_videos(self, query: str, max_results: int = 5, 
                    duration_type: str = 'any',
                    order_by: str = 'viewCount',
                    region_code: str = 'US',
                    days_ago: int = 5) -> List[Dict]:
        """Enhanced video analysis with engagement metrics."""
        try:
            st.text("🔍 Searching videos...")
            past_date = (datetime.utcnow() - timedelta(days=days_ago)).strftime('%Y-%m-%dT%H:%M:%SZ')
            
            search_params = {
                'q': query,
                'type': 'video',
                'part': 'id',
                'maxResults': max_results,
                'order': order_by,
                'regionCode': region_code,
                'publishedAfter': past_date
            }
            
            if duration_type != 'any':
                search_params['videoDuration'] = self.duration_ranges[duration_type]

            search_response = self.youtube.search().list(**search_params).execute()

            if not search_response.get('items'):
                return []

            video_ids = [item['id']['videoId'] for item in search_response['items']]
            
            st.text("📋 Getting video details and engagement metrics...")
            videos_response = self.youtube.videos().list(
                part='snippet,statistics,contentDetails',
                id=','.join(video_ids)
            ).execute()

            analyzed_videos = []
            query_keywords = [word.strip() for word in query.lower().split() if len(word.strip()) > 2]
            
            for video in videos_response['items']:
                try:
                    duration_str = video['contentDetails']['duration']
                    duration_sec = isodate.parse_duration(duration_str).total_seconds()
                    
                    view_count = int(video['statistics'].get('viewCount', 0))
                    like_count = int(video['statistics'].get('likeCount', 0))
                    comment_count = int(video['statistics'].get('commentCount', 0))
                    
                    publish_date = datetime.strptime(
                        video['snippet']['publishedAt'], 
                        '%Y-%m-%dT%H:%M:%SZ'
                    ).replace(tzinfo=pytz.UTC)
                    
                    days_since_publish = (datetime.now(pytz.UTC) - publish_date).days
                    
                    video_data = {
                        'title': video['snippet']['title'],
                        'video_id': video['id'],
                        'url': f"https://www.youtube.com/watch?v={video['id']}",
                        'view_count': view_count,
                        'like_count': like_count,
                        'comment_count': comment_count,
                        'engagement_rate': round((like_count / view_count * 100), 2) if view_count > 0 else 0,
                        'duration': {
                            'seconds': duration_sec,
                            'formatted': str(timedelta(seconds=int(duration_sec)))
                        },
                        'days_since_publish': days_since_publish,
                        'views_per_day': round(view_count / max(days_since_publish, 1)),
                        'tags': video['snippet'].get('tags', []),
                        'description': video['snippet']['description'],
                        'channel_title': video['snippet']['channelTitle'],
                        'category_id': video['snippet'].get('categoryId', 'N/A'),
                        'publish_date': publish_date.strftime('%Y-%m-%d'),
                        'region': self.regions[region_code]
                    }
                    
                    # Add enhanced segment analysis
                    video_data['hooks'] = self._analyze_segments(video_data, query_keywords)
                    analyzed_videos.append(video_data)
                    
                except Exception as e:
                    st.warning(f"Error processing video {video.get('id', 'unknown')}: {str(e)}")
                    continue

            st.text("✅ Analysis complete!")
            return analyzed_videos
            
        except Exception as e:
            st.error(f"Error in video analysis: {str(e)}")
            return []

    def display_video_segments(self, video: Dict):
        """Display segments from comments, description, and most replayed."""
        st.write("**🎯 Relevant Segments:**")
        
        # Display segments from comments
        if video['hooks']['comments']:
            st.write("**🔥 Popular Segments from Comments:**")
            for hook in video['hooks']['comments']:
                st.markdown(
                    f"""
                    <div style="padding: 10px; background-color: rgba(255, 99, 71, 0.2); border-radius: 5px; margin: 5px 0;">
                        <strong>{hook['title']}</strong><br>
                        Time: {str(timedelta(seconds=int(hook['start_time'])))} | Relevance: {hook['relevance_score'] * 100:.1f}%<br>
                        <a href="{hook['url']}" target="_blank">🎥 Watch Segment</a>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        
        # Display segments from description
        if video['hooks']['description']:
            st.write("**📖 Relevant Segments from Description:**")
            for hook in video['hooks']['description']:
                st.markdown(
                    f"""
                    <div style="padding: 10px; background-color: rgba(0, 128, 0, 0.2); border-radius: 5px; margin: 5px 0;">
                        <strong>{hook['title']}</strong><br>
                        Time: {str(timedelta(seconds=int(hook['start_time'])))} | Relevance: {hook['relevance_score'] * 100:.1f}%<br>
                        <a href="{hook['url']}" target="_blank">🎥 Watch Segment</a>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        
        # Display most replayed segments
        if video['hooks']['most_replayed']:
            st.write("**📊 Most Replayed Segments:**")
            for hook in video['hooks']['most_replayed']:
                st.markdown(
                    f"""
                    <div style="padding: 10px; background-color: rgba(0, 0, 255, 0.2); border-radius: 5px; margin: 5px 0;">
                        <strong>Most Replayed Segment</strong><br>
                        Time: {str(timedelta(seconds=int(hook['start_time'])))} - {str(timedelta(seconds=int(hook['end_time'])))}<br>
                        Intensity: {hook['intensity'] * 100:.1f}%<br>
                        <a href="{video['url']}&t={int(hook['start_time'])}s" target="_blank">🎥 Watch Segment</a>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

def main():
    st.set_page_config(
        page_title="YouTube Video Analyzer",
        page_icon="🎥",
        layout="wide"
    )
    
    st.title("🎥 YouTube Video Analyzer")
    
    # API Key handling in sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        api_key = st.text_input(
            "YouTube API Key",
            type="password",
            help="Enter your YouTube Data API v3 key"
        )
        
        st.markdown("---")
        st.markdown("""
        ### 📖 Quick Guide
        1. Enter your API key
        2. Set search parameters
        3. Click Search
        4. Analyze results
        
        [Get API Key](https://console.cloud.google.com/apis/credentials)
        """)
    
    if not api_key:
        st.warning("⚠️ Please enter your YouTube API Key in the sidebar")
        st.info("Need an API Key? [Get one here](https://console.cloud.google.com/apis/credentials)")
        st.stop()
    
    try:
        analyzer = YouTubeLiteAnalyzer(api_key)
        
        st.header("🔍 Search Parameters")
        
        query = st.text_input("Enter search query (e.g., 'mobile game ads')")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            region_code = st.selectbox(
                "Region",
                options=list(analyzer.regions.keys()),
                format_func=lambda x: analyzer.regions[x],
                help="Select the region to search videos from"
            )
            
            duration_type = st.selectbox(
                "Duration",
                options=["any", "short", "medium", "long"],
                format_func=lambda x: {
                    "any": "Any duration",
                    "short": "Short (< 4 minutes)",
                    "medium": "Medium (4-20 minutes)",
                    "long": "Long (> 20 minutes)"
                }[x]
            )
        
        with col2:
            days_ago = st.slider(
                "Published within days",
                min_value=1,
                max_value=30,
                value=5,
                help="Filter videos published within the selected number of days"
            )
            
            order_by = st.selectbox(
                "Sort By",
                options=["viewCount", "rating", "relevance", "date"],
                format_func=lambda x: {
                    "viewCount": "View Count",
                    "rating": "Rating",
                    "relevance": "Relevance",
                    "date": "Upload Date"
                }[x]
            )
        
        with col3:
            max_results = st.slider(
                "Number of results",
                min_value=1,
                max_value=10,
                value=5,
                help="Maximum number of videos to analyze"
            )
            
            quota_info = analyzer.calculate_quota_cost(max_results)
            st.info(f"""
            **📊 Quota Usage Estimate:**
            - Search: {quota_info['search_cost']} units
            - Video details: {quota_info['video_details_cost']} units
            - Comments analysis: {quota_info['comments_cost']} units
            - Total: {quota_info['total_cost']} units
            Daily limit: {quota_info['daily_limit']} units
            """)
        
        # Search button
        if st.button("🔎 Search Videos", type="primary"):
            if not query:
                st.error("❌ Please enter a search query")
                return
            
            progress_text = st.empty()
            progress_text.text("🔍 Analyzing videos...")
            
            # Perform search
            videos = analyzer.analyze_videos(
                query=query,
                max_results=max_results,
                duration_type=duration_type,
                order_by=order_by,
                region_code=region_code,
                days_ago=days_ago
            )
            
            if videos:
                st.header("📊 Results")
                
                # Add enhanced export
                if st.download_button(
                    label="📥 Export Results",
                    data=str(videos),
                    file_name="youtube_analysis.json",
                    mime="application/json"
                ):
                    st.success("Results exported successfully!")
                
                # Results summary
                total_segments = sum(len(v.get('hooks', {}).get('comments', [])) + len(v.get('hooks', {}).get('description', [])) + len(v.get('hooks', {}).get('most_replayed', [])) for v in videos)
                st.markdown(f"Found **{len(videos)}** videos with **{total_segments}** relevant segments")
                
                # Enhanced video display
                for video in videos:
                    with st.expander(f"📺 {video['title']}", expanded=True):
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            st.markdown(f"""
                            **Channel:** {video['channel_title']}  
                            **Region:** {video['region']}  
                            **Duration:** {video['duration']['formatted']}  
                            **Published:** {video['publish_date']} ({video['days_since_publish']} days ago)  
                            **Views:** {video['view_count']:,} ({video['views_per_day']:,} per day)  
                            **Engagement:** {video['engagement_rate']}% | 👍 {video['like_count']:,} | 💬 {video.get('comment_count', 0):,}
                            """)
                            
                            if video['tags']:
                                st.write("**Tags:**", ", ".join(video['tags'][:5]))
                        
                        with col2:
                            st.markdown(f"[🔗 Watch Full Video]({video['url']})")
                            
                            if st.button(f"📋 Copy URL", key=f"copy_{video['video_id']}"):
                                st.code(video['url'])
                        
                        analyzer.display_video_segments(video)
                        st.markdown("---")
            else:
                st.warning("No videos found matching your criteria")

    except Exception as e:
        st.error(f"Error: {str(e)}")
        st.error("Please check if your API key is valid and you have quota remaining")

if __name__ == "__main__":
    main()
