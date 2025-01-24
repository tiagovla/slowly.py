import os
import slowly

import logging

log = logging.getLogger("slowly")

log.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
log.addHandler(handler)


class Client(slowly.Client):
    async def main(self):
        friends = await self.fetch_friends()
        for friend in await self.fetch_friends():
            async for letter in friend.letters():
                print(letter)


if __name__ == "__main__":
    client = Client()
    token = os.getenv("SLOWLY_TOKEN")
    client.run(token)
