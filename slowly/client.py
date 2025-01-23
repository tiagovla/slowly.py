import asyncio
import logging
import signal
import sys
import traceback
from .models import User


from .http import HTTPClient
from .state import ConnectionState

log = logging.getLogger(__name__)


class _ClientEventTask(asyncio.Task):
    def __init__(self, original_coro, event_name, coro, *, loop):
        super().__init__(coro, loop=loop)
        self.__event_name = event_name
        self.__original_coro = original_coro

    def __repr__(self):
        info = [
            ("state", self._state.lower()),
            ("event", self.__event_name),
            ("coro", repr(self.__original_coro)),
        ]
        if self._exception is not None:
            info.append(("exception", repr(self._exception)))
        return "<ClientEventTask {}>".format(" ".join("%s=%s" % t for t in info))


class Client:
    def __init__(self, *, loop=None, **options):
        self.loop = loop or asyncio.get_event_loop()
        self.connector = options.pop("connector", None)
        self.proxy = options.pop("proxy", None)
        self.proxy_auth = options.pop("proxy_auth", None)
        self._listeners = {}
        self.http = HTTPClient(
            self.connector, proxy=self.proxy, proxy_auth=self.proxy_auth, loop=self.loop
        )
        self._ready = asyncio.Event()
        self._handlers = {"ready": self._handle_ready}
        self._connection = ConnectionState(
            dispatch=self.dispatch,
            handlers=self._handlers,
            http=self.http,
            loop=self.loop,
            **options,
        )

    def is_ready(self):
        return self._ready.is_set()

    async def _run_event(self, coro, event_name, *args, **kwargs):
        try:
            await coro(*args, **kwargs)
        except asyncio.CancelledError:
            pass
        except Exception:
            try:
                await self.on_error(event_name, *args, **kwargs)
            except asyncio.CancelledError:
                pass

    async def on_error(self, event_method, *args, **kwargs) -> None:
        print("Ignoring exception in {}".format(event_method), file=sys.stderr)
        traceback.print_exc()

    def _schedule_event(self, coro, event_name, *args, **kwargs):
        wrapped = self._run_event(coro, event_name, *args, **kwargs)
        return _ClientEventTask(
            original_coro=coro, event_name=event_name, coro=wrapped, loop=self.loop
        )

    async def wait_until_ready(self):
        await self._ready.wait()

    def wait_for(self, event, *, check=None, timeout=None):
        future = self.loop.create_future()
        check = check if check else lambda *args: True
        ev = event.lower()
        try:
            listeners = self._listeners[ev]
        except KeyError:
            listeners = []
            self._listeners[ev] = listeners

        listeners.append((future, check))
        return asyncio.wait_for(future, timeout)

    def dispatch(self, event, *args, **kwargs):
        log.debug("Dispatching %s", event)
        method = "on_" + event

        listeners = self._listeners.get(event)
        if listeners:
            removed = []
            for i, (future, condition) in enumerate(listeners):
                if future.cancelled():
                    removed.append(i)
                    continue

                try:
                    result = condition(*args)
                except Exception as exec:
                    future.set_exception(exec)
                    removed.append(i)
                else:
                    if result:
                        if len(args) == 0:
                            future.set_result(None)
                        elif len(args) == 1:
                            future.set_result(args[0])
                        else:
                            future.set_result(args)
                        removed.append(i)

                if len(removed) == len(listeners):
                    self._listeners.pop(event)
                else:
                    for idx in reversed(removed):
                        del listeners[idx]

        try:
            coro = getattr(self, method)
        except AttributeError:
            pass
        else:
            self._schedule_event(coro, method, *args, **kwargs)

    async def close(self) -> None:
        log.debug("Closing client")
        await self.http.close()

    async def login(self, token) -> None:
        log.debug("Logging in")
        await self.http.login(token.strip())

    async def start(self, *args, **kwargs) -> None:
        log.debug("Starting client")
        await self.login(*args)

    async def main(self) -> None:
        pass

    def _handle_ready(self) -> None:
        log.debug("Ready event!")
        self._ready.set()

    def run(self, *args, **kwargs):

        loop = self.loop
        try:
            loop.add_signal_handler(signal.SIGINT, lambda: loop.stop())
            loop.add_signal_handler(signal.SIGTERM, lambda: loop.stop())
        except NotImplementedError:
            pass

        async def runner():
            try:
                await self.start(*args, **kwargs)
                await self.main()
            finally:
                await self.close()

        def stop_loop_on_completion(f):
            loop.stop()

        future = asyncio.ensure_future(runner(), loop=loop)
        future.add_done_callback(stop_loop_on_completion)
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            print("Received terminate signal")
        finally:
            future.remove_done_callback(stop_loop_on_completion)

        if not future.cancelled():
            try:
                return future.result()
            except KeyboardInterrupt:
                return None

    def event(self, coro):
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError("event registered must be a coroutine function")

        setattr(self, coro.__name__, coro)
        log.debug("%s has successfully been registered as an event", coro.__name__)
        return coro

    async def fetch_client_profile(self):
        await self.http.get_client_profile()

    async def fetch_friends(self):
        data = await self.http.get_friends()
        log.debug("Fetched friends data.")
        return [User(self._connection, data=friend) for friend in data["friends"]]

    async def get_passcode(self, email):
        await self.http.auth_fetch_passcode(email)

    async def get_token(self, email, passcode) -> str:
        response = await self.http.auth_fetch_token(email, passcode)
        return response["token"]
