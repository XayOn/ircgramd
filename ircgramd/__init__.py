"""
Telegram to irc gateway

Usage:
    ircgramd --port=<listen_port> --ip=<listen_addr> --channel <control_chan>
    ircgramd --port=<listen_port>
    ircgramd --ip <listen_ip>
    ircgramd --channel <control_channel>

Options:
    --port=<listen_port>        Port to listen on
    --ip=<listen_ip>            Ip to listen on
    --channel=<control channel> Control channel

Examples:
    ircgramd --port=8080 --ip 127.0.0.1
    ircgramd --channel=#telegram
    ircgramd --port=8080 --ip=127.0.0.1 --channel=#telegram

"""
# pylint: disable=import-error

import socketserver
import asyncio
import functools
import json
import hashlib
from contextlib import suppress
import logging
from concurrent.futures import ThreadPoolExecutor
from irc.events import codes
from pytg import Telegram, IllegalResponseException
from pytg.utils import coroutine
from irc.server import IRCClient, IRCError
from docopt import docopt

logging.basicConfig(level=logging.ERROR)
EXECUTOR = ThreadPoolExecutor(200)


class IRCChannel(object):
    """
    IRC Channel, overwriting topic.

    """
    # pylint: disable=too-few-public-methods
    def __init__(self, name, topic='Telegram channel'):
        self.name = name
        self.topic_by = 'Telegram'
        self.topic = topic
        self.clients = set()


def get_user_name(client):
    """
    Try to get a username from any telegram user-like object

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

    This implements:
    - Chat handling *
    - Channel handling *
    - Private message handling
    - Channel lists
    - User lists in chats

    * Both represented as channels in IRC.
      TODO: Make channels +v and user without voice =)

    """

    def __init__(self, *args, **kwargs):
        self.nick = get_user_name(self.tgm.sender.whoami())
        super().__init__(*args, **kwargs)
        self.tgm = Telegram(**self.server.tgopts, user="+{}".format(self.nick))
        self.control_channel = self.server.control_channel

    @property
    @functools.lru_cache()
    def chats(self):
        """
        Extract the list of chats from current open dialogs

        """
        dialogs = self.tgm.sender.dialog_list()
        return [c for c in dialogs if c['peer_type'] == "chat"]

    @property
    @functools.lru_cache()
    def chans(self):
        """ Retur telegram channel list """
        return self.tgm.sender.channel_list()

    @property
    def channels(self):
        """
        Return the list of channels available in the server.
        That being the chats + the channels the user has
        joined in telegram

        """
        chats = [get_user_name(chat) for chat in self.chats]
        chans = [get_user_name(chan) for chan in self.chans]
        return chats + chans

    @property
    @functools.lru_cache()
    def contacts(self):
        """
        Return contact list

        .. TODO:: After implementing modes, we should probably make
                  open dialogs +v

        """
        return self.tgm.sender.contacts_list()

    @staticmethod
    def send_privmsg(from_, to_, msg):
        """ Craft a IRC private message """
        return ':%s PRIVMSG %s %s' % (from_, to_, msg)

    def receive_message(self, channel, sender, msg):
        """
        Send a fake message from anybody to the user,
        this enables us to send messages from telegram buddies

        """
        for line in msg.split('\n'):
            self.send_queue.append(TGIrcClient.send_privmsg(
                from_=sender, to_=channel, msg=line))

    def handle_list(self, params):
        """
        Handles list command. Does not yet support parameters

        """
        self.send_queue.append(':' + ' '.join([
            self.client_ident(), codes['liststart'], self.nick,
            'Channel', ':Users Name']))

        for chan in self.server.channels:
            self.send_queue.append(':' + ' '.join(
                [self.server.servername, codes['list'], self.nick, chan]))

        self.send_queue.append(":" + " ".join(
            [self.server.servername, codes["listend"], self.nick,
             ':End of /LIST']))

    def handle_privmsg(self, params):
        """
        Handle all private messages (that is, messages received
        by a user or to a channel, we don't really care)

        """

        with suppress(Exception):
            target, _, msg = params.partition(' ')
            if target.startswith('#'):
                if target == self.control_channel:
                    target, msg = msg[1:].split(':')
                    self.tgm.sender.send_msg(target, msg[1:].strip())
                else:
                    self.tgm.sender.send_msg(target[1:], msg[1:].strip())
            else:
                self.tgm.sender.send_msg(target, msg[1:].strip())

    def handle_names(self, channel):
        """
        handle names command

        """
        for channel in channel.split(','):
            if channel == self.control_channel:
                nicks = [get_user_name(contact) for contact in self.contacts]
            else:
                channel_ = channel[1:]
                nicks = []
                with suppress(IllegalResponseException):
                    if channel_ in [get_user_name(a) for a in self.chans]:
                        nicks = self.tgm.sender.channel_get_members(channel_)
                    # elif channel in [get_user_name(a) for a in self.chats]:
                    else:
                        nicks = self.tgm.sender.chat_info(channel_)['members']
                    nicks = [get_user_name(nick) for nick in nicks]

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
            self.handle_names(channel)

    def handle_nick(self, params):
        nick, password = params
        if not self.auth(nick, password):
            raise IRCError.from_name('nosuchnick', 'Wrong password')
        super().handle_nick(nick)

    def auth(self, nick, password):
        """ Check user auth """
        pass_ = json.load(open('~/.ircgramd_passwords', 'r')).get(nick)
        return hashlib.sha256(password.encode('utf-8')).hexdigest == pass_


class IRCServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """
    IRC server implementation

    """
    daemon_threads = True
    allow_reuse_address = True
    clients = {}

    def __init__(self, *args, **kwargs):
        self.servername = 'localhost'
        self.tgopts = kwargs.pop('tgopts')
        self.control_channel = kwargs.pop('control_channel')
        self.clients = {}
        super().__init__(*args, **kwargs)


def run_receiver(client):
    """
    Run receiver threat

    """

    @coroutine
    def message_loop(client):
        """
        Fake message sender

        """
        def get_chan(msg):
            if msg.receiver.type == "user":
                if msg.sender.type == "user":
                    return get_user_name(msg.sender)
            return "#{}".format(msg.receiver.title.replace(' ', '_'))

        while True:
            try:
                msg = (yield)
                if msg.get('event', False) != "message":
                    continue
                if not msg.own:
                    chan = get_chan(msg)
                    sender = get_user_name(msg['sender'])
                    msg = msg.get("text", msg.get("media"))
                    client.receive_message(chan, sender, msg)
            except (KeyError, ValueError, IndexError) as exception:
                logging.error(exception)
            except Exception:
                logging.exception("Something strange happened")

    client.tgm.receiver.start()
    client.tgm.receiver.message(message_loop(client))


def client_monitor(ircserver):
    """
    Monitor for new clients and add a future receiver for each
    with their phone number.

    """
    loop = asyncio.get_event_loop()
    for client in ircserver.clients:
        if client not in ircserver.watched_clients:
            ircserver.watched_clients.append(client)
            asyncio.ensure_future(
                loop.run_in_executor(
                    EXECUTOR, functools.partial(run_receiver, client)))


def main():
    """ Run irc server """
    kwargs = {k.replace('--', ''): v for k, v in docopt(__doc__).items()}
    tgopts = {"telegram": kwargs.get("bin", "/usr/bin/telegram-cli"),
              "pubkey_file": kwargs.get("key", "/etc/telegram/TG-server.pub")}
    ipport = (kwargs.get('ip', '127.0.0.1'), int(kwargs.get('port', 6667)))
    control_channel = kwargs.get('control_channel', '#telegram')

    ircserver = IRCServer(ipport, TGIrcClient, tgopts=tgopts,
                          control_channel=control_channel)

    loop = asyncio.get_event_loop()
    # pylint: disable=no-member
    asyncio.ensure_future(loop.run_in_executor(
        EXECUTOR, functools.partial(client_monitor, ircserver)))
    asyncio.ensure_future(loop.run_in_executor(
        EXECUTOR, ircserver.serve_forever))
    loop.run_forever()
    loop.close()
