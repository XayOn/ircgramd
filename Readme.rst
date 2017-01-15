IRCGramD
--------

Local IRC Server implementing a telegram-cli gateway.

This project is a telegram to irc gateway (and vice-versa)
similar bitlbee + libpurple + telegram-purple setup.


Why did I do this
-----------------

After a few hours trying to make bitlbee + telegram-libpurple
to work on my rpi3, I decided that writing my own would probably
be easier (and it actually was).

How to make it work
-------------------

Currently, you need to have telegram-cli installed
and the phones you're going to use authenticated (see telegram-cli --user)
The nick you send to the irc server will be used as your telegram user,
wich must be YOUR PHONE.
**This is important, your nick on the telegram server must be your phone
including contry code (without the initial 00 or the +).
For example, 34671666617 NOT +34671666617 or 0034...**

Security
--------
**Warning: this project has no security features whatsoever**
This means that you are responsible for isolating this server
in a secure network, allowing access only from your client.

Also, this server's traffic goes unencrypted. OpenVPN will
probably be cool enough.


Usage
------

::

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


Usage is pretty simple:

- Install telegram_cli
- Run telegram_cli and authenticate your user
- Run ``ircgramd``
- Connect your irc client and join your specified control channel

TODO
----

- SSL
- Some kind of assistant / documentation for creating new users.
- Make channels work again
