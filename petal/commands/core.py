import asyncio
from urllib.parse import urlencode, quote_plus

import discord

from petal.dbhandler import m2id


class Commands:
    auth_fail = "This command is implemented incorrectly."
    op = -1  # Used for Minecraft commands
    role = ""  # Name of the config field dictating the name of the needed role
    whitelist = ""  # Name of the list of permitted IDs in the config file

    def __init__(self, client, router, *a, **kw):
        self.client = client
        self.config = client.config
        self.db = client.db

        self.router = router
        self.log = self.router.log

        self.args = a  # Save for later
        self.kwargs = kw  # Just in case

    def get_command(self, kword: str):
        if "__" not in kword:
            # Refuse to fetch anything with a dunder
            return getattr(self, "cmd_" + kword, None), None

    def get_all(self) -> list:
        full = [
            getattr(self, attr)
            for attr in dir(self)
            if "__" not in attr and attr.startswith("cmd_")
        ]
        return full

    def authenticate(self, src):
        """
        Take a Discord message and return True if:
          1. The author of the message is allowed to access this package.
          2. This command can be run in this channel.
        """
        try:
            if self.whitelist and src.author.id not in self.config.get(
                self.whitelist, []
            ):
                return False, "denied"
            if self.role:
                allow, denied = self.check_user_has_role(
                    src.author, self.config.get(self.role)
                )
                if not allow:
                    return allow, denied
            if 0 <= self.op <= 4:
                if hasattr(self, "minecraft"):
                    return self.minecraft.WLAuthenticate(src, self.op)
                else:
                    return False, "bad op"
        except Exception as e:
            # For security, "fail closed".
            return False, "Error: `{}`".format(e)
        else:
            return True, None

    def any(self, sample: dict, *allowed: str):
        """Try to find any specifically non-None (rather than simple logically
            True) value in a dict.
        """
        if not allowed:
            # If no values are supplied, search all.
            allowed = list(sample)

        for key in allowed:
            if sample.get(key, None) is not None:
                return sample[key]

        return None

    # # # UTILS IMPORTED FROM LEGACY COMMANDS # # #

    def check_user_has_role(self, user, role):
        if not role:
            return "bad role"
        if type(user) != discord.Member:
            user = self.member_on_main(user.id)
        if user:
            server = self.client.get_server(self.config.get("mainServer"))
            target = discord.utils.get(server.roles, name=role)
            # TODO: Make this block a bit more...compact.
            if target is None:
                # Role is not found on Main Server? Check this one.
                target = discord.utils.get(user.server.roles, name=role)
                if target is None:
                    # Role is not found on this server? Fail.
                    self.log.err("Role '" + role + "' does not exist.")
                    return False, "bad role"
                elif target in user.roles:
                    # Role is found, and includes member? Pass.
                    return True, None
                else:
                    # Role is found, but does not include member? Fail.
                    return False, "denied"
            else:
                # Role is found on Main Server. Find the member there and check.
                user_there = server.get_member(user.id)
                if user_there:
                    # User is there? Check roles.
                    if target in user_there.roles:
                        return True, None
                    else:
                        return False, "denied"
                else:
                    # User is NOT there? Fail.
                    return False, "bad user"
        else:
            return False, "private"

    def get_member(self, src, uuid):
        """
        Get a Discord Member object from an ID.
        """
        if isinstance(src, discord.Server):
            return src.get_member(m2id(uuid))
        else:
            return discord.utils.get(
                src.server.members, id=uuid.lstrip("<@!").rstrip(">")
            )

    def member_on_main(self, uuid):
        return self.get_member(
            self.client.get_server(self.client.get_main_server()), uuid
        )

    @staticmethod
    def validate_channel(chanlist: list, msg: str) -> bool:
        for i in range(len(msg)):
            try:
                chanlist[int(msg[int(i)])]
            except AttributeError:
                return False
        return True

    async def notify_subscribers(self, source_channel, target_message, key):
        await self.client.send_message(None, source_channel, "Notifying subscribers...")
        sub = self.db.subs.find_one({"code": key})
        if sub is None:
            return "Error, could not find that subscription anymore. Which shouldn't ever happen. Ask isometricramen about it."
        status = "```\n"
        total = len(sub["members"])
        if len(sub["members"]) == 0:
            return "Nobody is subscribed to this game. "
        count = 0
        for member in sub["members"]:
            mem = self.get_member(target_message, member)
            if mem is None:
                status += member + " is missing\n"
            else:
                try:
                    await self.client.send_message(
                        None,
                        mem,
                        "Hello! Hope your day/evening/night/morning is going well\n\nI was just popping in here to let you know that an event for `{}` has been announced.".format(
                            sub["name"]
                        )
                        + "\n\nIf you wish to stop receiving these messages, just do `{}unsubscribe {}` in the same server in which you subscribed originally.".format(
                            self.config.prefix, sub["code"]
                        ),
                    )
                except discord.errors.ClientException:
                    status += member + " blocked PMs\n"
                else:
                    status += mem.name + " PMed\n"
                    count += 1
            if len(status) > 1900:
                await self.client.send_message(None, source_channel, status + "```")
                await asyncio.sleep(0.5)
                status = "```\n"
        if len(status) > 0:
            await self.client.send_message(None, source_channel, status + "```")
        return (
            str(count) + " out of " + str(total) + " subscribed members were notified. "
        )

    # TODO: Convert to Mongo
    def get_event_subscription(self, post):

        print(post)
        postdata = post.lower().split(" ")

        subs = list(self.db.subs.find({}))
        if len(subs) == 0:
            self.log.f("event", "Subscription list empty. Ignoring...")
            return None, None
        # print(str(postdata))
        self.log.f("subs", "Searching for explicit tags")
        for item in subs:
            if "[{}]".format(item["code"]) in post:
                return item["code"], item["name"]
        for item in subs:
            # print(item["name"] + item["code"])

            if item["code"].lower() in postdata:
                return item["code"], item["name"]
            for word in item["name"].split(" "):
                # print(word)

                if word.lower() in [
                    "and",
                    "of",
                    "the",
                    "or",
                    "with",
                    "to",
                    "from",
                    "by",
                    "on",
                    "or",
                ]:
                    continue

                if word.lower() in postdata:
                    return item["code"], item["name"]

        self.log.f("event", "could not find subscription key in your announcement")
        return None, None

    def generate_post_process_URI(self, mod, reason, message, target):
        if self.config.get("modURI") is None:
            return "*no modURI in config, so post processing will be skipped*"
        req = {"mod": mod, "off": reason, "msg": message, "uid": target}
        return self.config.get("modURI") + "?" + urlencode(req, quote_via=quote_plus)
