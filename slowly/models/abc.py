import abc


class Snowflake(metaclass=abc.ABCMeta):

    __slots__ = ()

    @property
    @abc.abstractmethod
    def created_at(self):
        """:class:`datetime.datetime`: Returns the model's creation time as a naive datetime in UTC."""
        raise NotImplementedError

    @classmethod
    def __subclasshook__(cls, C):
        if cls is Snowflake:
            mro = C.__mro__
            for attr in ("created_at", "id"):
                for base in mro:
                    if attr in base.__dict__:
                        break
                else:
                    return NotImplemented
            return True
        return NotImplemented


class User(metaclass=abc.ABCMeta):
    ...


class Letter(metaclass=abc.ABCMeta):
    ...

