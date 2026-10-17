"""
video class object
store video attributes and class methods
"""


class Video:

    def __init__(self, video_id, channel_id, title, description, publish_date, likes, t3_comments, views, total_comments, duration):
        self.__video_id = video_id
        self.__channel_id = channel_id
        self.__title = title
        self.__description = description
        self.__publish_date = publish_date
        self.__likes = likes
        self.__t3_comments = t3_comments
        self.__views = views
        self.__total_comments = total_comments
        self.__duration = duration

    @property
    def video_id(self):
        return self.__video_id

    @property
    def channel_id(self):
        return self.__channel_id

    @property
    def title(self):
        return self.__title

    @property
    def description(self):
        return self.__description

    @property
    def publish_date(self):
        return self.__publish_date

    @property
    def likes(self):
        return self.__likes

    @property
    def t3_comments(self):
        return self.__t3_comments

    @property
    def views(self):
        return self.__views

    @property
    def total_comments(self):
        return self.__total_comments

    @property
    def duration(self):
        return self.__duration
