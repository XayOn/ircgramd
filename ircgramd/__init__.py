"""
Telegram to irc platform

"""
# pylint: disable=import-error

import socketserver
import asyncio
import functools
import logging
from concurrent.futures import ThreadPoolExecutor

from pytg import Telegram, IllegalResponseException
from pytg.utils import coroutine
from irc.server import IRCClient

logging.basicConfig(level=logging.ERROR)

CONTROL_CHANNELS = ["#telegram"]

TGM = Telegram(telegram="/usr/bin/telegram-cli",
               pubkey_file="/etc/telegram/TG-server.pub")


class IRCChannel(object):
    """
    IRC Channel handler.

    """
    # pylint: disable=too-few-public-methods
    def __init__(self, name, topic='Telegram channel'):
        self.name = name
        self.topic_by = 'Telegram'
        self.topic = topic
        self.clients = set()


def get_user_name(client):
    """
    If not name is present, return username,
    if not present, return phone

    """
    def get_name(client):
        """ return username """
        name = client.get('print_name', "_".join(
            a for a in [client.get('name', False),
                        client.get('last_name', False)] if a))
        if not name:
            return client.get("username", client.id)
        return name.replace(' ', '_')

    if client.get('peer_type', '') in ("channel", "chat"):
        return "#{}".format(get_name(client))
    else:
        return "{}".format(get_name(client))


class TGIrcClient(IRCClient):
    """
    Telegram to irc base client class

    """

    def __init__(self, *args, **kwargs):
        self.tgm = TGM
        self.nick = get_user_name(self.tgm.sender.whoami())
        self.control_channels = CONTROL_CHANNELS
        super().__init__(*args, **kwargs)

    @staticmethod
    def send_privmsg(from_, to_, msg):
        """ craft a private message """
        return ':%s PRIVMSG %s %s' % (from_, to_, msg)

    def receive_message(self, channel, sender, msg):
        """
        Send a fake message from anybody

        """
        for line in msg.split('\n'):
            self.send_queue.append(TGIrcClient.send_privmsg(
                from_=sender, to_=channel, msg=line))

    def is_probably_me(self, nick):
        """ probably me """
        nicks = [self.nick.lower(), "{}_".format(self.nick.lower())]
        return nick.lower() in nicks

    def handle_privmsg(self, params):
        """
        Handle all private messages (that is, messages received
        by a user or to a channel, we don't really care)

        """

        try:
            target, _, msg = params.partition(' ')
            if target.startswith('#'):
                if target in CONTROL_CHANNELS:
                    target, msg = msg[1:].split(':')
                    self.tgm.sender.send_msg(target, msg[1:].strip())
                else:
                    self.tgm.sender.send_msg(target[1:], msg[1:].strip())
            else:
                self.tgm.sender.send_msg(target, msg[1:].strip())
        except Exception as err:
            print(err)

    @property
    @functools.lru_cache(20)
    def nicklist(self):
        """
        Return nicklist with groups, channels and users

        """

        return (self.tgm.sender.contacts_list(),
                self.tgm.sender.channel_list(),
                self.tgm.sender.dialog_list())

    def get_type_by_name(self, name):
        """ Not quite efficient ... """
        _, channels, _ = self.nicklist

        for channel_name in channels:
            if name in channel_name.values():
                return "channel"
        return "chat"

    @property
    def nick_names(self):
        """ Return nick names """
        for method in self.nicklist:
            for nick in method:
                yield get_user_name(nick)

    def handle_names(self, channel):
        """
        handle names command

        """
        for channel in channel.split(','):
            if channel in CONTROL_CHANNELS:
                # We are in a control channel, return contact list
                nicks = list(self.nick_names)
            else:
                try:
                    # We are in a group chat. Return nicklist
                    # for that groupchat
                    if self.get_type_by_name(channel[1:]) == "channel":
                        nicks = self.tgm.sender.channel_get_members(channel)
                    else:
                        nicks = self.tgm.sender.chat_info(
                            channel[1:])['members']
                    nicks = [get_user_name(nick) for nick in nicks]
                except (KeyError, IllegalResponseException):
                    nicks = []

            self.send_queue.append(':{} 353 {} = {} :{}'.format(
                self.server.servername, self.nick, channel, ' '.join(nicks)))
            self.send_queue.append(
                ':{} 366 {} {} :End of /NAMES list'.format(
                    self.server.servername, channel, self.nick))

    def handle_join(self, channel):
        """
        Overwrite join to send fake names

        """
        for channel in channel.split(','):
            super().handle_join(channel)
            self.channels[channel].topic = channel
            self.handle_names(channel)


class IRCServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """
    IRC server implementation

    """
    daemon_threads = True
    allow_reuse_address = True
    channels = {}
    clients = {}

    def __init__(self, *args, **kwargs):
        self.servername = 'localhost'
        self.channels = {}
        self.clients = {}
        super().__init__(*args, **kwargs)


@coroutine
def message_loop(ircclient):
    """
    foo

    """
    while True:
        # pylint: disable=broad-except
        try:
            msg = (yield)
            client = list(ircclient.clients.keys())[0]

            if msg.get('event', False) != "message":
                continue
            if msg.receiver.type == "user":
                # We, or somebody else in a chan are getting
                # a message
                if msg.sender.type == "user":
                    # We are getting a message
                    chan = get_user_name(msg.sender)
                else:
                    # Somebody is getting a message in a chan
                    chan = "#{}".format(msg.receiver.title.replace(' ', '_'))
            else:
                # A message has been sent to a chan or group
                chan = "#{}".format(msg.receiver.title.replace(' ', '_'))

            sender = get_user_name(msg['sender'])
            if not msg.own:
                msg = msg.get("text", msg.get("media"))
                ircclient.clients[client].receive_message(chan, sender, msg)
        except (KeyError, ValueError, IndexError) as exception:
            logging.error(exception)
        except Exception:
            logging.exception("Something failed")


def run_receiver(ircserver):
    """ Run receiver """
    TGM.receiver.start()
    TGM.receiver.message(message_loop(ircserver))


def main():
    """ Run irc server on port 6667 """

    ircserver = IRCServer(("127.0.0.1", 6667), TGIrcClient)
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(2)
    # pylint: disable=no-member
    asyncio.ensure_future(loop.run_in_executor(
        executor, functools.partial(run_receiver, ircserver)))
    asyncio.ensure_future(loop.run_in_executor(
        executor, ircserver.serve_forever))
    loop.run_forever()
    loop.close()


if __name__ == "__main__":
    main()
