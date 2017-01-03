TeleIRC - IRC<->telegram gateway
---------------------------------

Not my best proyect name, I know.

.. warning:: This is a 3h project. I actually invested
             3h in writting it all (except this readme,
             of course).
             It works, but it'll probably lack things
             you want


This project is a telegram to irc gateway (and vice-versa)
similar bitlbee + libpurple + telegram-purple setup.

After a few hours trying to make bitlbee + telegram-libpurple
to work on my rpi3, I decided that writing my own would probably
be easier (and it actually was).

Currently, you need to have telegram-cli installed, and
the user authenticated. Only one user per system user is allowed
at a time, and probably port collision will happen if you do it
on multiple users (irc port is hardcoded, as well as default
port for telegram-cli in pytg).

Usage
------

Usage is pretty simple:

- Install telegram_cli
- Run telegram_cli and authenticate your user
- Run ``teleirc``
- Connect your irc server to localhost:6666 and join #telegram
  channel

Now, you'll see some users have a # before their names on the
#telegram channel. That's so you can use autocomplete on
/join to not miss the channels name, but they're not actually
users and talking to them directly from the #telegram channel
will probably work not-so-fine.

Also, I'd recommend not using #telegram channel at all except
for the userlist, as user responses will always go on private
queries...

Apart from that, joining, querying and receiving messages work
as usual on IRC
