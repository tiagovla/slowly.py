from datetime import datetime
import logging

from . import abc
from ..state import ConnectionState
from .letter import AsyncLetterIterator

log = logging.getLogger(__name__)


class BaseUser(abc.User):
    __slots__ = (
        "_state",
        "dob",
        "age",
        "allowaudio",
        "allowphotos",
        "audiorequest",
        "avatar",
        "by_id",
        "created_at",
        "customdesc",
        "deactivated",
        "dob_privacy",
        "emoji_status",
        "fav",
        "gender",
        "id",
        "identity",
        "joined",
        "joined_at",
        "joined_audio",
        "joined_photos",
        "latest_comment",
        "latest_sent_by",
        "location_code",
        "name",
        "openletter",
        "photorequest",
        "plus",
        "show_last_login",
        "status",
        "total",
        "unread",
        "updated_at",
        "user_audio",
        "user_id",
        "user_photos",
        "user_status",
    )

    def __init__(self, state: ConnectionState, *, data):
        self._state: ConnectionState = state
        BaseUser._update(self, data)

    def __str__(self):
        return self.name

    def _update(self, data):
        for attr in BaseUser.__slots__:
            if attr.startswith("_"):
                continue
            if attr in [
                "created_at",
                "latest_comment",
                "updated_at",
                "joined_at",
            ] and data.get(attr):
                date_object = datetime.strptime(data["created_at"], "%Y-%m-%d %H:%M:%S")
                setattr(self, attr, date_object)
                continue
            elif attr == "dob" and data.get("dob"):
                date_object = datetime.strptime(data["dob"], "%Y-%m-%d")
                setattr(self, attr, date_object)
                continue
            setattr(self, attr, data.get(attr, None))

    def __repr__(self):
        return "<User name={0.name!r} id={0.id!r}>".format(self)


class User(BaseUser):
    def __init__(self, state: ConnectionState, *, data):
        super().__init__(state, data=data)

    def letters(self) -> AsyncLetterIterator:
        return AsyncLetterIterator(self._state, self.id)
