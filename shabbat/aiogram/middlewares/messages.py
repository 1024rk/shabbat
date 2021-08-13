import json

import psycopg2
import aiopg
from aiogram.dispatcher.middlewares import BaseMiddleware


class MessagesSet:
    def __init__(self):
        super(MessagesSet, self).__setattr__("_messages", {})

    def __setattr__(self, attr, value):
        self._messages[attr] = value

    def __getattr__(self, attr):
        try:
            return self._messages[attr]
        except KeyError:
            raise AttributeError


class MessagesProxy:
    def __init__(self):
        self.project_id = None
        self.configured = False

    async def configure(
        self, bot, config, messages_file="messages.json", hard=False, hard_list=[]
    ):
        self.messages = MessagesSet()
        self.fallback_messages = MessagesSet()
        if config.debug:
            messages = json.load(open(messages_file, encoding="utf-8"))
            for message_name, message_text in messages.items():
                if isinstance(message_text, dict):
                    message_text = message_text["text"]
                setattr(self.messages, message_name, message_text)
                setattr(self.fallback_messages, message_name, message_text)
            return
        self.dsn = (
            "dbname={database} user={user} password={password} host={host}".format(
                database=config.database,
                user=config.user,
                password=config.password,
                host=config.host,
            )
        )
        bot_obj = await bot.get_me()
        self.bot_name = bot_obj.username
        async with aiopg.create_pool(self.dsn) as pool:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select id from project where name = %s", (self.bot_name,)
                    )
                    async for row in cur:
                        self.project_id = row[0]
                    if self.project_id is None:
                        await cur.execute(
                            "insert into project (name) values (%s) returning id",
                            (self.bot_name,),
                        )
                        async for row in cur:
                            self.project_id = row[0]
                    await cur.execute(
                        "select name, text from message where project_id = %s",
                        (self.project_id,),
                    )
                    async for row in cur:
                        setattr(self.fallback_messages, row[0], row[1])
                    messages = json.load(open(messages_file, encoding="utf-8"))
                    for message_name in hard_list:
                        if message_name not in messages.keys():
                            await cur.execute(
                                "select id from message where name = %s and project_id = %s",
                                (message_name, self.project_id),
                            )
                            message_id = None
                            async for row in cur:
                                message_id = row[0]
                            if message_id is not None:
                                await cur.execute(
                                    "delete from variable where message_id = %s",
                                    (message_id,),
                                )
                                await cur.execute(
                                    "delete from message where id = %s", (message_id,)
                                )
                    for message_name, message_text in messages.items():
                        variables = []
                        if hard or not hasattr(self.fallback_messages, message_name):
                            if (
                                hard
                                and message_name not in hard_list
                                and hasattr(self.fallback_messages, message_name)
                            ):
                                continue
                            if hard:
                                await cur.execute(
                                    "select id from message where name = %s and project_id = %s",
                                    (message_name, self.project_id),
                                )
                                async for row in cur:
                                    message_id = row[0]
                                variables_in_db = {}
                                await cur.execute(
                                    "select id, name from variable where message_id = %s",
                                    (message_id,),
                                )
                                async for row in cur:
                                    variables_in_db[row[1]] = row[0]
                                for var_name, var_id in variables_in_db.items():
                                    await cur.execute(
                                        "delete from variable where id = %s", (var_id,)
                                    )
                                await cur.execute(
                                    "delete from message where id = %s", (message_id,)
                                )
                            if isinstance(message_text, dict):
                                variables = message_text["variables"]
                                message_text = message_text["text"]
                            await cur.execute(
                                "insert into message (name, text, project_id) values (%s, %s, %s) returning id",
                                (message_name, message_text, self.project_id),
                            )
                            async for row in cur:
                                message_id = row[0]
                            for variable in variables:
                                await cur.execute(
                                    "insert into variable (name, description, message_id) values (%s, %s, %s)",
                                    (
                                        variable["name"],
                                        variable["description"],
                                        message_id,
                                    ),
                                )
                            setattr(self.messages, message_name, message_text)
                            setattr(self.fallback_messages, message_name, message_text)
        self.configured = True

    async def actualize_messages(self):
        if not self.configured:
            return self.fallback_messages
        try:
            async with aiopg.create_pool(self.dsn) as pool:
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "select name, text from message where project_id = %s",
                            (self.project_id,),
                        )
                        async for row in cur:
                            setattr(self.messages, row[0], row[1])
            return self.messages
        except psycopg2.Error:
            return self.fallback_messages


class MessagesMiddleware(BaseMiddleware):
    """
    Proxies a set of bot messages to context, taking it from database
    """

    def __init__(self):
        super().__init__()
        self.messages_proxy = MessagesProxy()

    async def configure_db(
        self, bot, config, messages_file="messages.json", hard=False, hard_list=[]
    ):
        await self.messages_proxy.configure(
            bot, config, messages_file, hard=hard, hard_list=hard_list
        )

    async def on_pre_process_message(self, message, data):
        data["messages"] = await self.messages_proxy.actualize_messages()

    async def on_pre_process_edited_message(self, edited_message, data):
        data["messages"] = await self.messages_proxy.actualize_messages()

    async def on_pre_process_channel_post(self, channel_post, data):
        data["messages"] = await self.messages_proxy.actualize_messages()

    async def on_pre_process_edited_channel_post(self, edited_channel_post, data):
        data["messages"] = await self.messages_proxy.actualize_messages()

    async def on_pre_process_inline_query(self, inline_query, data):
        data["messages"] = await self.messages_proxy.actualize_messages()

    async def on_pre_process_chosen_inline_result(self, chosen_inline_result, data):
        data["messages"] = await self.messages_proxy.actualize_messages()

    async def on_pre_process_callback_query(self, callback_query, data):
        data["messages"] = await self.messages_proxy.actualize_messages()

    async def on_pre_process_shipping_query(self, shipping_query, data):
        data["messages"] = await self.messages_proxy.actualize_messages()

    async def on_pre_process_pre_checkout_query(self, pre_checkout_query, data):
        data["messages"] = await self.messages_proxy.actualize_messages()

    async def on_pre_process_poll(self, poll, data):
        data["messages"] = await self.messages_proxy.actualize_messages()

    async def on_pre_process_poll_answer(self, poll_answer, data):
        data["messages"] = await self.messages_proxy.actualize_messages()
