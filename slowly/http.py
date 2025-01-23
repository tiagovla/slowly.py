import asyncio
import uuid
import logging
from typing import Optional, Any, Dict, Coroutine
from urllib.parse import quote as _uriquote

import aiohttp
from .errors import Forbidden, HTTPException, NotFound

log: logging.Logger = logging.getLogger(__name__)


async def json_or_text(response: aiohttp.ClientResponse) -> Dict[str, Any] | str:
    """
    Parse the response as JSON if possible, otherwise return as text.

    :param response: The response object to parse.
    :type response: aiohttp.ClientResponse
    :return: The parsed JSON data or text.
    :rtype: dict[str, Any] or str
    """
    try:
        if "application/json" in response.headers["content-type"]:
            return await response.json()
    except KeyError:
        pass
    return await response.text(encoding="utf-8")


class Route:
    BASE = "https://api.getslowly.com/"

    def __init__(self, method: str, path: str, **params: Any) -> None:
        """
        Initialize a Route instance.

        :param method: The HTTP method (e.g., 'GET', 'POST').
        :type method: str
        :param path: The API endpoint path.
        :type path: str
        :param params: Additional parameters for the URL.
        :type params: Any
        """
        self.path = path
        self.method = method
        url: str = self.BASE + self.path
        if params:
            self.url = url.format(
                **{
                    k: _uriquote(v) if isinstance(v, str) else v
                    for k, v in params.items()
                }
            )
        else:
            self.url = url


class HTTPClient:
    def __init__(
        self,
        connector: Optional[aiohttp.BaseConnector] = None,
        *,
        proxy: Optional[str] = None,
        proxy_auth: Optional[aiohttp.BasicAuth] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """
        Initialize an HTTPClient instance.

        :param connector: The aiohttp connector to use, by default None.
        :type connector: Optional[aiohttp.BaseConnector], optional
        :param proxy: The proxy URL, by default None.
        :type proxy: Optional[str], optional
        :param proxy_auth: The proxy authentication, by default None.
        :type proxy_auth: Optional[aiohttp.BasicAuth], optional
        :param loop: The event loop to use, by default None.
        :type loop: Optional[asyncio.AbstractEventLoop], optional
        """
        self.loop: asyncio.AbstractEventLoop = loop or asyncio.get_event_loop()
        self.connector: Optional[aiohttp.BaseConnector] = connector
        self.__session: aiohttp.ClientSession
        self.token: Optional[str] = None
        self.proxy: Optional[str] = proxy
        self.proxy_auth: Optional[aiohttp.BasicAuth] = proxy_auth
        self.__global_over: asyncio.Event = asyncio.Event()
        self.__global_over.set()
        self.user_agent: str = " ".join(
            [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "AppleWebKit/537.36 (KHTML, like Gecko)",
                "Chrome/132.0.0.0 Safari/537.36",
            ]
        )
        self.device = {
            "uuid": str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.getnode()))),
            "os": "Linux x86_64",
            "browser": "Chrome 132",
            "locale": "en",
            "trusted": "true",
            "version": "4.0.x",
        }

    async def request(self, route: Route, **kwargs: Any) -> dict[str, Any] | str:
        """
        Make an HTTP request.

        :param route: The route object containing method and URL.
        :type route: Route
        :param kwargs: Additional arguments for the request.
        :type kwargs: Any
        :return: The response data.
        :rtype: dict[str, Any] or str
        :raises Forbidden: If the response status is 403.
        :raises NotFound: If the response status is 404.
        :raises HTTPException: For other HTTP errors.
        :raises RuntimeError: If the code is unreachable.
        """
        method = route.method
        url = route.url
        headers: Optional[dict[str, str]] = kwargs.get("headers")
        if headers is None:
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "origin": "https://web.slowly.app",
                "user-agent": self.user_agent,
            }
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"
        kwargs["headers"] = headers
        if self.proxy:
            kwargs["proxy"] = self.proxy
        elif self.proxy_auth:
            kwargs["proxy_auth"] = self.proxy_auth
        if not self.__global_over.is_set():
            await self.__global_over.wait()
        for tries in range(3):
            async with self.__session.request(method, url, **kwargs) as r:
                data: dict[str, Any] | str = await json_or_text(r)
                if 300 > r.status >= 200:
                    return data
                elif r.status in {500, 502}:
                    await asyncio.sleep(1 + tries * 2)
                    continue
                elif r.status == 403:
                    raise Forbidden(r, data)
                elif r.status == 404:
                    raise NotFound(r, data)
                else:
                    raise HTTPException(r, data)
        raise RuntimeError("Unreachable code in HTTP handling")

    async def login(self, token: str) -> None:
        """
        Login with the provided token.

        :param token: The authentication token.
        :type token: str
        """
        log.debug("Logging in with token: %s", token)
        self.__session = aiohttp.ClientSession(connector=self.connector)
        self.token = token

    async def close(self) -> None:
        """
        Close the HTTP session.
        """
        log.debug("Closing the HTTP session")
        if self.__session:
            await self.__session.close()

    async def recreate(self) -> None:
        """
        Recreate the HTTP session if it is closed.
        """
        log.debug("Recreating the HTTP session")
        if self.__session and self.__session.closed:
            self.__session = aiohttp.ClientSession(connector=self.connector)

    def get_client_profile(self) -> Coroutine[Any, Any, dict[str, Any] | str]:
        """
        Get the client's profile.

        :return: The coroutine for the request.
        :rtype: Coroutine
        """
        log.debug("Getting client profile")
        device = str(self.device)
        data = {
            "device": device,
            "trusted": True,
            "ver": 90000,
            "includes": "add_by_id,weather,paragraph",
        }
        return self.request(Route("POST", "web/me"), data=data)

    def get_friends(
        self, requests: int = 1, dob: bool = True
    ) -> Coroutine[Any, Any, dict[str, Any] | str]:
        """
        Get the list of friends.

        :param requests: The number of friend requests, by default 1.
        :type requests: int, optional
        :param dob: Whether to include date of birth, by default True.
        :type dob: bool, optional
        :return: The coroutine for the request.
        :rtype: Coroutine
        """
        log.debug("Getting friends with requests: %d, dob: %s", requests, dob)
        dob = "true" if dob else "false"
        params = {"requests": requests, "dob": dob, "token": self.token}
        return self.request(Route("GET", "users/me/friends/v2"), params=params)

    def fetch_user_letters(
        self, friend_id: int, page: int = 1
    ) -> Coroutine[Any, Any, dict[str, Any] | str]:
        """
        Fetch letters from a specific friend.

        :param friend_id: The friend's ID.
        :type friend_id: int
        :param page: The page number, by default 1.
        :type page: int, optional
        :return: The coroutine for the request.
        :rtype: Coroutine
        """
        log.debug("Fetching letters for friend_id: %d, page: %d", friend_id, page)
        params = {"token": self.token, "page": page}
        return self.request(Route("GET", f"friend/{friend_id}/all"), params=params)

    async def auth_fetch_passcode(
        self, email: str
    ) -> Coroutine[Any, Any, dict[str, Any] | str]:
        """
        Fetch the authentication passcode.

        :param email: The email address.
        :type email: str
        :return: The coroutine for the request.
        :rtype: Coroutine
        """
        log.debug("Fetching passcode for email: %s", email)
        data = {"email": email, "device": self.device, "checkpass": False}
        return self.request(Route("POST", "auth/email/passcode"), data=data)

    async def auth_fetch_token(
        self, email: str, passcode: str
    ) -> Coroutine[Any, Any, dict[str, Any] | str]:
        """
        Fetch the authentication token.

        :param email: The email address.
        :type email: str
        :param passcode: The passcode.
        :type passcode: str
        :return: The coroutine for the request.
        :rtype: Coroutine
        """
        log.debug("Fetching token for email: %s with passcode: %s", email, passcode)
        data = {"email": email, "passcode": passcode, "device": self.device}
        return self.request(Route("POST", "auth/email"), data=data)
