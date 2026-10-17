import os
from dotenv import load_dotenv

from googleapiclient.discovery import build

import csv
import logging
# added type hints for better code clarity and maintainability

from video import Video

# @TODO
# get channel -> get uploads playlist id -> get ~10 videos -> get max 100 comments using threads per video


# grabbing channels by their '@' handle may be the easiest if we have a predefined list of channels we want
def get_channel_uploads_id():
    uploads = {}
    with open('data/channels.txt', 'r') as channels:
        for channel in channels:
            handle = channel.strip()
            if not handle:
                continue
            try:
                request = youtube.channels().list(
                    part="snippet,contentDetails,statistics",
                    forHandle=handle
                )
                response = request.execute()
                if response['items']:
                    uploads[handle] = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
                else:
                    print(f"No channel found for handle: {handle}")
            except Exception as e:
                print(f"Error for {handle}: {e}")
                continue
    return uploads


def get_channel_data():
    channels_data = []
    with open('data/channels.txt', 'r') as channels:
        for channel in channels:
            handle = channel.strip()
            if not handle:
                continue
            try:
                request = youtube.channels().list(
                    part="snippet,contentDetails,statistics",
                    forHandle=handle
                )
                response = request.execute()
                if response['items']:
                    channel_info = {
                        'channel_id': response['items'][0]['id'],
                        'title': response['items'][0]['snippet']['title'],
                        'country': response['items'][0]['snippet'].get('country', 'N/A'),
                    }
                    channels_data.append(channel_info)
                else:
                    print(f"No channel found for handle: {handle}")
            except Exception as e:
                print(f"Error for {handle}: {e}")
                continue
    return channels_data


def create_video_obj(video_id) -> Video:

    try:
        request = youtube.videos.list(
            part="id, snippet, contentDetails, statistics, status, ",
            id=video_id
        )
        response = request.execute()

        if response['items']:
            item = response['items'][0]

            video_id = item['id']
            channel = item['snippet']['channelId']
            title = item['snippet']['title']
            desc = item['snippet']['description']
            published_date = item['snippet']['publishedAt']
            views = item['statistics'].get('viewCount', 0)
            likes = item['statistics'].get('likeCount', 0)
            tot_comments = item['statistics'].get('commentCount', 0)
            t3_comments = fetch_top3_comments(video_id)
            duration = item['contentDetails'].get('duration', 0)

            video = Video(video_id, channel, title, desc, published_date,
                          views, likes, tot_comments, t3_comments, duration)

        else:
            print(f"No video found for ID: {id}")
    except Exception as e:
        print(f"Error fetching data for video {id}: {e}")


def fetch_top3_comments(video_id) -> list:
    comments = []
    nextPageToken = None

    try:
        request = youtube.comments().list(
            part="id",
            id=video_id
        )

        response = request.execute()
        if response.get('items'):
            for item in response.get('items'):
                comment = item['textDisplay']
                comments.append(comment)

                nextPageToken = response.get('nextPageToken')
                if not nextPageToken:
                    break
    except Exception as e:
        print(f"Error fetching comments for video {video_id}: {e}")
    return comments


def testAPI():  # simple test function to ensure API is working
    global youtube
    request = youtube.channels().list(
        part="snippet,contentDetails,statistics",
        id="UC_x5XG1OV2P6uZZ5FSM9Ttw"
    )
    response = request.execute()

    print('\n\n\n' + 'REQUESTED' + '\n\n\n')

    try:
        print(response)
        print('\n\n\n' + 'REQUEST SUCCESS!' + '\n\n\n')
    except:
        print('\n\n\n' + 'REQUEST FAILED' + '\n\n\n')


def main():
    # setup logging for debugging reasons
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/collector.log'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)

    # making globals

    def create_youtube_client():
        try:
            load_dotenv()
            api_key = os.getenv('API_KEY')
            if not api_key:
                raise ValueError(
                    "API_KEY not found in environment variables. Please check your .env file.")

            client = build("youtube", "v3", developerKey=api_key)
            logger.info("YouTube API client created successfully")
            return client
        except Exception as e:
            logger.error(f"Failed to create YouTube client: {e}")
            raise

    youtube = create_youtube_client()

    link = ''

    # vid_id = process_link(link)   still need to make this

    new_vid = create_video_obj(vid_id)


if __name__ == "__main__":
    main()
