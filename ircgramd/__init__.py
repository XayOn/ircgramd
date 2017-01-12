"""
Telegram to irc platform
------------------------

Usage:

    ircgramd --port <PORT_TO_LISTEN_ON> --ip <IP_TO_LISTEN_ON> \
             --control-channel <CONTROL_CHANNEL>

    irgramd --port <PORT_TO_LISTEN_ON>

    irgramd --ip <IP_TO_LISTEN_ON>

    irgramd --control-channel <CONTROL_CHANNEL>

Options:
    --port <PORT>    Port to listen on
    --ip   <IP>      Ip to listen on
    --control-channel control channel

"""
# pylint: disable=import-error

import socketserver
import asyncio
import functools
from contextlib import suppress
import logging
from concurrent.futures import ThreadPoolExecutor
from irc.events import codes
from pytg import Telegram, IllegalResponseException
from pytg.utils import coroutine
from irc.server import IRCClient
from docopt import docopt

logging.basicConfig(level=logging.ERROR)


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
        self.nick = get_user_name(self.tgm.sender.whoami())
        super().__init__(*args, **kwargs)
        self.tgm = self.server.tgm
        self.control_channel = self.server.control_channel

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

    @property
    @functools.lru_cache()
    def contacts(self):
        """ Return contact list """
        return self.tgm.sender.contacts_list()

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


class IRCServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """
    IRC server implementation

    """
    daemon_threads = True
    allow_reuse_address = True
    clients = {}

    @property
    @functools.lru_cache()
    def chats(self):
        """ Return chat list """
        dialogs = self.tgm.sender.dialog_list()
        return [c for c in dialogs if c['peer_type'] == "channel"]

    @property
    @functools.lru_cache()
    def chans(self):
        """ Return channel list """
        return self.tgm.sender.channel_list()

    @property
    def channels(self):
        chats = [get_user_name(chat) for chat in self.chats]
        chans = [get_user_name(chan) for chan in self.chans]
        return chats + chans

    def __init__(self, *args, **kwargs):
        self.servername = 'localhost'
        self.tgm = args.pop(2)
        self.clients = {}
        super().__init__(*args, **kwargs)


@coroutine
def message_loop(ircclient):
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
            for client in ircclient.clients.keys():
                if msg.get('event', False) != "message":
                    continue
                if not msg.own:
                    chan = get_chan(msg)
                    sender = get_user_name(msg['sender'])
                    msg = msg.get("text", msg.get("media"))
                    ircclient.clients[client].receive_message(
                        chan, sender, msg)
        except (KeyError, ValueError, IndexError) as exception:
            logging.error(exception)
        except Exception:
            logging.exception("Something strange happened")


def run_receiver(ircserver):
    """ Run receiver """
    ircserver.tgm.receiver.start()
    ircserver.tgm.receiver.message(message_loop(ircserver))


def main(**kwargs):
    """ Run irc server """
    tgopts = {"telegram": "/usr/bin/telegram-cli",
              "pubkey_file": "/etc/telegram/TG-server.pub"}
    ipport = (kwargs.get('ip', '127.0.0.1'), kwargs.get('port', 6667))
    control_channel = kwargs.get('control_channel', '#telegram')

    ircserver = IRCServer(ipport, TGIrcClient, telegram=Telegram(**tgopts),
                          control_channel=control_channel)

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
    main({k.replace('--', ''): v for k, v in docopt(__doc__).items()})
