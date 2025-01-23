from datetime import datetime
import logging

from . import abc
from ..state import ConnectionState

log = logging.getLogger(__name__)


class BaseLetter(abc.Letter):
    __slots__ = (
        "_state",
        "attachments",
        "avatar",
        "body",
        "created_at",
        "deliver_at",
        "fav",
        "gender",
        "id",
        "location_code",
        "name",
        "post",
        "read_at",
        "sent_from",
        "stamp",
        "status",
        "style",
        "type",
        "updated_at",
        "user",
        "user_fav",
        "user_to",
        "user_to_fav",
    )

    def __init__(self, state: ConnectionState, *, data):
        self._state: ConnectionState = state
        Letter._update(self, data)

    def __str__(self):
        return "<Letter from={0.name!r}>".format(self)

    def _update(self, data):
        for attr in BaseLetter.__slots__:
            if attr.startswith("_"):
                continue
            if attr in [
                "created_at",
                "updated_at",
                "delivered_at",
                "read_at",
            ] and data.get(attr):
                date_object = datetime.strptime(data[attr], "%Y-%m-%d %H:%M:%S")
                setattr(self, attr, date_object)
                continue
            setattr(self, attr, data.get(attr, None))

    def __repr__(self):
        return "<Letter id={0.id!r}>".format(self)


class Letter(BaseLetter):
    def __init__(self, state: ConnectionState, *, data):
        super().__init__(state, data=data)


class AsyncLetterIterator:
    def __init__(self, state, user_id):
        self.state = state
        self.user_id = user_id
        self.current_page = 1
        self.letter_batch = []
        self.next_page = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.letter_batch:
            return self.letter_batch.pop(0)

        if self.current_page == 1 or self.next_page:
            data = await self.state.http.fetch_user_letters(
                self.user_id, page=self.current_page
            )
            self.current_page += 1
            self.next_page = data["comments"]["next_page_url"]
            self.letter_batch = [
                Letter(self.state, data=letter) for letter in data["comments"]["data"]
            ]
        if self.letter_batch:
            return self.letter_batch.pop(0)
        else:
            raise StopAsyncIteration

    async def flatten(self) -> list[Letter]:
        all_letters = []
        async for letter in self:
            all_letters.append(letter)
        return all_letters
