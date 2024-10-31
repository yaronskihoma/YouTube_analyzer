import streamlit as st
import os
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import isodate
import pytz
from typing import List, Dict

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

    def calculate_quota_cost(self, max_results: int) -> dict:
        """Calculate estimated API quota usage."""
        search_cost = 100  # Search request cost
        video_details_cost = 1  # Cost per video details request
        total_video_costs = video_details_cost * max_results
        
        total_cost = search_cost + total_video_costs
        
        return {
            'search_cost': search_cost,
            'video_details_cost': total_video_costs,
            'total_cost': total_cost,
            'daily_limit': 10000,
            'remaining_after': 10000 - total_cost
        }

    def analyze_videos(self, query: str, max_results: int = 5, 
                      duration_type: str = 'any',
                      order_by: str = 'viewCount',
                      region_code: str = 'US',
                      days_ago: int = 5) -> List[Dict]:
        """
        Search and analyze videos with enhanced filters.
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of videos to return
            duration_type (str): Duration filter ('any', 'short', 'medium', 'long')
            order_by (str): Sort order ('viewCount', 'rating', 'relevance', 'date')
            region_code (str): Region code for search (e.g., 'US', 'GB')
            days_ago (int): Number of days to look back for videos
        """
        try:
            with st.status("🔍 Searching videos...") as status:
                # Calculate date based on days_ago parameter
                past_date = (datetime.utcnow() - timedelta(days=days_ago)).strftime('%Y-%m-%dT%H:%M:%SZ')
                
                status.update(label="Building search parameters...")
                # Build search parameters
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

                status.update(label="Executing search...")
                search_response = self.youtube.search().list(**search_params).execute()

                if not search_response.get('items'):
                    return []

                video_ids = [item['id']['videoId'] for item in search_response['items']]
                
                status.update(label="Getting video details...")
                # Get video details
                videos_response = self.youtube.videos().list(
                    part='snippet,statistics,contentDetails',
                    id=','.join(video_ids)
                ).execute()

                status.update(label="Processing results...")
                analyzed_videos = []
                for video in videos_response['items']:
                    try:
                        # Convert duration to seconds
                        duration_str = video['contentDetails']['duration']
                        duration_sec = isodate.parse_duration(duration_str).total_seconds()
                        
                        # Process video data
                        view_count = int(video['statistics'].get('viewCount', 0))
                        like_count = int(video['statistics'].get('likeCount', 0))
                        
                        publish_date = datetime.strptime(
                            video['snippet']['publishedAt'], 
                            '%Y-%m-%dT%H:%M:%SZ'
                        ).replace(tzinfo=pytz.UTC)
                        
                        days_since_publish = (datetime.now(pytz.UTC) - publish_date).days
                        
                        # Enhanced video data
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
                            'description': video['snippet']['description'],
                            'channel_title': video['snippet']['channelTitle'],
                            'category_id': video['snippet'].get('categoryId', 'N/A'),
                            'publish_date': publish_date.strftime('%Y-%m-%d'),
                            'region': self.regions[region_code]
                        }
                        
                        # Find hooks
                        video_data['hooks'] = self._find_hooks(video_data)
                        analyzed_videos.append(video_data)
                        
                    except Exception as e:
                        st.warning(f"Error processing video {video.get('id', 'unknown')}: {str(e)}")
                        continue

                status.update(label="✅ Analysis complete!", state="complete")
                return analyzed_videos
            
        except Exception as e:
            st.error(f"Error in video analysis: {str(e)}")
            return []

    def _find_hooks(self, video_data: Dict) -> List[Dict]:
        """Find potential hook segments in video."""
        hooks = []
        
        # Always add opening hook
        hooks.append({
            'type': 'opening',
            'start_time': 0,
            'duration': 5,
            'url': f"{video_data['url']}&t=0s"
        })
        
        # Parse description for timestamps
        description_lines = video_data.get('description', '').split('\n')
        for line in description_lines:
            if ':' in line and any(char.isdigit() for char in line):
                try:
                    # Extract timestamp
                    time_part = line.split(' ')[0]
                    if ':' in time_part:
                        time_parts = time_part.split(':')
                        seconds = sum(x * int(t) for x, t in zip([3600, 60, 1], time_parts[-3:]))
                        
                        # Only add if it's not too close to start and within video duration
                        if seconds > 10 and seconds < video_data['duration']['seconds'] - 5:
                            hooks.append({
                                'type': 'chapter',
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
        
        # Main search interface
        st.header("🔍 Search Parameters")
        
        # Search query
        query = st.text_input("Enter search query (e.g., 'mobile game ads')")
        
        # Create three columns for filters
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Region selection
            region_code = st.selectbox(
                "Region",
                options=list(analyzer.regions.keys()),
                format_func=lambda x: analyzer.regions[x],
                help="Select the region to search videos from"
            )
            
            # Duration filter
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
            # Date range filter
            days_ago = st.slider(
                "Published within days",
                min_value=1,
                max_value=30,
                value=5,
                help="Filter videos published within the selected number of days"
            )
            
            # Sort order
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
            # Number of results
            max_results = st.slider(
                "Number of results",
                min_value=1,
                max_value=10,
                value=5,
                help="Maximum number of videos to analyze"
            )
            
            # Calculate and display quota usage
            quota_info = analyzer.calculate_quota_cost(max_results)
            st.info(f"""
            **📊 Quota Usage Estimate:**
            - Search: {quota_info['search_cost']} units
            - Video details: {quota_info['video_details_cost']} units
            - Total: {quota_info['total_cost']} units
            
            Daily limit: {quota_info['daily_limit']} units
            """)
        
        # Search button
        if st.button("🔎 Search Videos", type="primary"):
            if not query:
                st.error("❌ Please enter a search query")
                return
                
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
                
                # Add export button
                if st.download_button(
                    label="📥 Export Results",
                    data=str(videos),
                    file_name="youtube_analysis.json",
                    mime="application/json"
                ):
                    st.success("Results exported successfully!")
                
                # Display results
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
                            **Engagement Rate:** {video['engagement_rate']}%  
                            """)
                            
                            if video['tags']:
                                st.write("**Tags:**", ", ".join(video['tags'][:5]))
                        
                        with col2:
                            st.markdown(f"[🔗 Watch Video]({video['url']})")
                            
                            # Copy button
                            if st.button(f"📋 Copy URL", key=f"copy_{video['video_id']}"):
                                st.code(video['url'])
                        
                        st.write("**🎯 Potential Hooks:**")
                        for hook in video['hooks']:
                            st.markdown(
                                f"- **{hook['type'].title()}**\n"
                                f"  - Start Time: {hook['start_time']} seconds\n"
                                f"  - [Watch Segment]({hook['url']})"
                            )
                        
                        st.markdown("---")
            else:
                st.warning("No videos found matching your criteria")

    except Exception as e:
        st.error(f"Error: {str(e)}")
        st.error("Please check if your API key is valid and you have quota remaining")

if __name__ == "__main__":
    main()
