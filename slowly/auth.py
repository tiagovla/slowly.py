class Auth:
    def __init__(
        self,
        token=None,
    ):
        self.token = token

    async def check_token(self):
        raise NotImplementedError

    async def login(self, email: str):
        raise NotImplementedError
