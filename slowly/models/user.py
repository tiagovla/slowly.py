from datetime import datetime
import logging
from typing import Any, Dict

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

    def __init__(self, state: ConnectionState, *, data: Dict[str, Any]) -> None:
        """
        Initialize a BaseUser instance.

        :param state: The connection state.
        :param data: The data to initialize the user with.
        """
        self._state: ConnectionState = state
        self._update(data)

    def __str__(self) -> str:
        """
        Return the string representation of the user.

        :return: The name of the user.
        """
        return self.name

    def _update(self, data: Dict[str, Any]) -> None:
        """
        Update the user attributes with the provided data.

        :param data: The data to update the user with.
        """
        for attr in BaseUser.__slots__:
            if attr.startswith("_"):
                continue
            if attr in [
                "created_at",
                "latest_comment",
                "updated_at",
                "joined_at",
            ] and data.get(attr):
                date_object = datetime.strptime(data[attr], "%Y-%m-%d %H:%M:%S")
                setattr(self, attr, date_object)
                continue
            elif attr == "dob" and data.get("dob"):
                date_object = datetime.strptime(data["dob"], "%Y-%m-%d")
                setattr(self, attr, date_object)
                continue
            setattr(self, attr, data.get(attr, None))

    def __repr__(self) -> str:
        """
        Return the official string representation of the user.

        :return: The official string representation of the user.
        """
        return "<User name={0.name!r} id={0.id!r}>".format(self)


class User(BaseUser):
    def __init__(self, state: ConnectionState, *, data: Dict[str, Any]) -> None:
        """
        Initialize a User instance.

        :param state: The connection state.
        :param data: The data to initialize the user with.
        """
        super().__init__(state, data=data)

    def letters(self) -> AsyncLetterIterator:
        """
        Return an iterator for the user's letters.

        :return: An AsyncLetterIterator instance.
        """
        return AsyncLetterIterator(self._state, self.id)
