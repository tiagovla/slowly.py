import asyncio
import logging
import signal
from typing import Any, Callable, Dict, List, Optional, Tuple
from .models import User
from .http import HTTPClient
from .state import ConnectionState

log = logging.getLogger(__name__)


class _ClientEventTask(asyncio.Task):
    def __init__(
        self,
        original_coro: Callable,
        event_name: str,
        coro: Callable,
        *,
        loop: asyncio.AbstractEventLoop
    ) -> None:
        super().__init__(coro, loop=loop)
        self.__event_name = event_name
        self.__original_coro = original_coro

    def __repr__(self) -> str:
        info = [
            ("state", self._state.lower()),
            ("event", self.__event_name),
            ("coro", repr(self.__original_coro)),
        ]
        if self._exception is not None:
            info.append(("exception", repr(self._exception)))
        return "<ClientEventTask {}>".format(" ".join("%s=%s" % t for t in info))


class Client:
    def __init__(
        self, *, loop: Optional[asyncio.AbstractEventLoop] = None, **options: Any
    ) -> None:
        self.loop = loop or asyncio.get_event_loop()
        self.connector = options.pop("connector", None)
        self.proxy = options.pop("proxy", None)
        self.proxy_auth = options.pop("proxy_auth", None)
        self._listeners: Dict[str, List[Tuple[asyncio.Future, Callable]]] = {}
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

    def is_ready(self) -> bool:
        """Check if the client is ready."""
        return self._ready.is_set()

    async def _run_event(
        self, coro: Callable, event_name: str, *args: Any, **kwargs: Any
    ) -> None:
        try:
            await coro(*args, **kwargs)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("Exception in event '%s': %s", event_name, e)
            try:
                await self.on_error(event_name, *args, **kwargs)
            except asyncio.CancelledError:
                pass

    async def on_error(self, event_method: str, *args: Any, **kwargs: Any) -> None:
        """Handle errors during event execution."""
        log.error("Ignoring exception in %s", event_method, exc_info=True)

    def _schedule_event(
        self, coro: Callable, event_name: str, *args: Any, **kwargs: Any
    ) -> _ClientEventTask:
        wrapped = self._run_event(coro, event_name, *args, **kwargs)
        return _ClientEventTask(
            original_coro=coro, event_name=event_name, coro=wrapped, loop=self.loop
        )

    async def wait_until_ready(self) -> None:
        """Wait until the client is ready."""
        await self._ready.wait()

    def wait_for(
        self,
        event: str,
        *,
        check: Optional[Callable] = None,
        timeout: Optional[float] = None
    ) -> asyncio.Future:
        """Wait for a specific event to occur."""
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

    def dispatch(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Dispatch an event to the appropriate handlers."""
        log.debug(
            "Dispatching event: %s with args: %s and kwargs: %s", event, args, kwargs
        )
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
                    log.error(
                        "Error in event listener condition for event '%s': %s",
                        event,
                        exec,
                    )
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
            log.warning("No handler found for event: %s", event)
        else:
            self._schedule_event(coro, method, *args, **kwargs)

    async def close(self) -> None:
        """Close the client."""
        log.debug("Closing client")
        await self.http.close()

    async def login(self, token: str) -> None:
        """Login to the client using a token."""
        log.debug("Logging in with token: %s", token)
        await self.http.login(token.strip())

    async def start(self, *args: Any, **kwargs: Any) -> None:
        """Start the client."""
        log.debug("Starting client with args: %s and kwargs: %s", args, kwargs)
        await self.login(*args)

    async def main(self) -> None:
        """Main function to be overridden by subclasses."""
        pass

    def _handle_ready(self) -> None:
        """Handle the ready event."""
        log.debug("Ready event triggered")
        self._ready.set()

    def run(self, *args: Any, **kwargs: Any) -> Optional[Any]:
        """Run the client."""
        loop = self.loop
        try:
            loop.add_signal_handler(signal.SIGINT, lambda: loop.stop())
            loop.add_signal_handler(signal.SIGTERM, lambda: loop.stop())
        except NotImplementedError:
            pass

        async def runner() -> None:
            try:
                await self.start(*args, **kwargs)
                await self.main()
            finally:
                await self.close()

        def stop_loop_on_completion(f: asyncio.Future) -> None:
            loop.stop()

        future = asyncio.ensure_future(runner(), loop=loop)
        future.add_done_callback(stop_loop_on_completion)
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            log.info("Received terminate signal")
        finally:
            future.remove_done_callback(stop_loop_on_completion)

        if not future.cancelled():
            try:
                return future.result()
            except KeyboardInterrupt:
                return None

    def event(self, coro: Callable) -> Callable:
        """Register an event coroutine."""
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError("event registered must be a coroutine function")

        setattr(self, coro.__name__, coro)
        log.debug("Event %s has been successfully registered", coro.__name__)
        return coro

    async def fetch_client_profile(self) -> None:
        """Fetch the client profile."""
        log.debug("Fetching client profile")
        await self.http.fetch_client_profile()

    async def fetch_friends(self) -> List[User]:
        """Fetch the list of friends."""
        data = await self.http.fetch_friends()
        log.debug("Fetched friends data: %s", data)
        return [User(self._connection, data=friend) for friend in data["friends"]]

    async def fetch_passcode(self, email: str) -> None:
        """Fetch the passcode for the given email."""
        log.debug("Fetching passcode for email: %s", email)
        await self.http.fetch_auth_passcode(email)

    async def fetch_token(self, email: str, passcode: str) -> str:
        """Fetch the token for the given email and passcode."""
        log.debug("Fetching token for email: %s with passcode: %s", email, passcode)
        response = await self.http.fetch_auth_token(email, passcode)
        log.debug("Fetched token: %s", response["token"])
        return response["token"]
