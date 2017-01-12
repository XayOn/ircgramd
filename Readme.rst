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

Currently, you need to have telegram-cli installed, and
the user running the IRCGramD process authenticated.
Only one user per system user is allowed at a time,
and probably port collision will happen if you do it
on multiple users (irc port is hardcoded, as well as default
port for telegram-cli in pytg).

Security
--------
**Warning: this project has no security features whatsoever**
This means that you are responsible for isolating this server
in a secure network, allowing access only from your client.

Also, this server's traffic goes unencrypted. OpenVPN will
probably be cool enough.


Usage
------

Usage is pretty simple:

- Install telegram_cli
- Run telegram_cli and authenticate your user
- Run ``ircgramd``
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


TODO
----

- SSL
- User auth
