import json
import argparse
import os
import sys
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Instructions:
# 1. Obtain a YouTube Data API v3 key from the Google Cloud Console:
#    - Go to https://console.cloud.google.com/
#    - Create a project, enable the YouTube Data API v3, and generate an API key.
# 2. Set the GOOGLE_CLOUD_PROJECT_KEY environment variable with your API key.
# 3. Run the script with the channel handle as a command-line argument, e.g.:
#    python yt-channel.py --channel_handle PepperGeek

# Get API key from environment variable
api_key = os.getenv('GOOGLE_CLOUD_PROJECT_KEY')
if not api_key:
    print("Error: GOOGLE_CLOUD_PROJECT_KEY environment variable is not set.")
    print("Please set it to your YouTube Data API v3 key.")
    sys.exit(1)

def get_channel_id(youtube, handle):
    request = youtube.channels().list(
        part='id,contentDetails',
        forHandle=handle
    )
    response = request.execute()
    if 'items' in response and response['items']:
        channel = response['items'][0]
        return channel['id'], channel['contentDetails']['relatedPlaylists']['uploads']
    else:
        raise ValueError(f"Channel with handle '{handle}' not found.")

def get_all_videos(youtube, playlist_id):
    videos = []
    next_page_token = None
    while True:
        try:
            request = youtube.playlistItems().list(
                part='snippet',
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            for item in response['items']:
                snippet = item['snippet']
                video_id = snippet['resourceId']['videoId']
                url = f'https://youtu.be/{video_id}'
                metadata = {
                    'url': url,
                    'title': snippet['title'],
                    'published_at': snippet['publishedAt'],
                    'description': snippet['description'],
                    # You can add more metadata here if needed, e.g., thumbnails: snippet['thumbnails']
                }
                videos.append(metadata)
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
        except HttpError as e:
            print(f"An error occurred: {e}")
            break
    return videos

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a JSON file with videos from a YouTube channel.")
    parser.add_argument('--channel_handle', type=str, required=True, help="The YouTube channel handle (without the '@')")
    args = parser.parse_args()

    youtube = build('youtube', 'v3', developerKey=api_key)

    try:
        channel_id, uploads_playlist_id = get_channel_id(youtube, args.channel_handle)
        videos = get_all_videos(youtube, uploads_playlist_id)
        with open(f'{args.channel_handle}_videos.json', 'w', encoding='utf-8') as f:
            json.dump(videos, f, ensure_ascii=False, indent=4)
        print(f"Successfully saved {len(videos)} videos to '{args.channel_handle}_videos.json'")
    except ValueError as ve:
        print(ve)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
