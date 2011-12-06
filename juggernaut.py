# -*- coding: utf-8 -*-
"""
    juggernaut
    ~~~~~~~~~~

    Dead simple Python library that connects to a juggernaut via
    redis.  It also provides a very basic roster implementation that
    can be used as a daemon process to manage online users.

    Basic usage
    -----------

    How to send a message to all subscribers of a channel::

        from juggernaut import Juggernaut
        jug = Juggernaut()
        jug.publish('channel', {'message': 'Hello World!'})

    Connection Events
    -----------------

    Juggernaut also allows you to subscribe to events (new subscription,
    unsubscribe event) so that you can respond to users going online
    and offline::

        from juggernaut import Juggernaut
        jug = Juggernaut()
        for event, data in jug.subscribe_listen():
            if event == 'subscribe':
                ...
            elif event == 'unsubscribe':
                ...

    Since this is quite common this library also implements a Roster
    that can group multiple connections to the same user.  For grouping
    this it uses a key in the meta part of the message.  The default
    is ``user_id`` in the meta object.

    Example usage::

        from juggernaut import Juggernaut, RedisRoster
        jug = Juggernaut()
        roster = RedisRoster(jug)
        roster.run()

    By default it keeps the number of online users in redis so that you
    can use the roster class to see if users are online::

        >>> roster.get_online_users()
        [42, 23]
        >>> roster.is_user_online(42)
        True
        >>> roster.is_user_online(99)
        False

    If you want to respond to users signing in and out you need to
    override the `on_signed_in` and `on_signed_out` methods::

        class MyRoster(RedisRoster):
            def on_signed_in(self, user_id):
                print 'User signed in', user_id
            def on_signed_out(self, user_id):
                print 'User signed out', user_id

    You can for instance use juggernaut to broadcast that to other
    users that signed in.


    :copyright: (c) 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import redis
try:
    import simplejson as json
except ImportError:
    import json


class Juggernaut(object):
    """Connects to a Juggernaut.  By default it creates a new redis
    connection with default settings (localhost) but a different
    connection can be explicitly provided.
    """
    events = [
        'juggernaut:subscribe',
        'juggernaut:unsubscribe',
        'juggernaut:custom'
    ]

    def __init__(self, redis_connection=None, key='juggernaut'):
        if redis_connection is None:
            redis_connection = redis.Redis()
        self.redis = redis_connection
        self.key = key

    def publish(self, channels, data, except_=None, **options):
        """Publishes some data to one channel or a list of channels."""
        if isinstance(channels, basestring):
            channels = [channels]
        d = {'channels': list(set(channels)), 'data': data}
        if except_:
            d['except'] = except_
        d.update(options)
        data = json.dumps(d)
        self.redis.publish(self.key, data)

    def subscribe_listen(self):
        """Iterates over incoming events in a blocking way and yields
        ``(event, data)`` tuples.
        """
        pubsub = self.redis.pubsub()
        for event in self.events:
            pubsub.subscribe(event)
        for message in pubsub.listen():
            event = message['channel'].split(':', 1)[1]
            data = json.loads(message['data'])
            yield event, data

    def subscribe(self, handler):
        """"Like :meth:`subscribe_listen` but calls a function instead."""
        for args in self.subscribe_listen():
            handler(*args)


class Roster(object):
    """Implements the basic functionality to provide a roster.  Use the
    subclasses that actually implement the storage.

    For this to work the user id has to be specified in the meta when
    creating the connection::

        var jug = new Juggernaut();
        jug.meta = {'user_id': the_users_id};
        jug.subscribe(...);

    The roster can be used as a daemon::

        from juggernaut import RedisRoster
        RedisRoster().run()

    Or as a client to see the current contents::

        from juggernaut import RedisRoster
        roster = RedisRoster()
        print roster.get_online_users()
    """

    def __init__(self, jug=None):
        if jug is None:
            jug = Juggernaut()
        self.jug = jug

    def get_user_id(self, data):
        """Returns the user id from the data.  The default implementation
        returns the :attr:`user_meta_key` from the meta dictionary if
        available.  If no user is associated with the connection `None`
        is returned.
        """
        meta = data.get('meta')
        if meta:
            return unicode(meta.get(self.user_meta_key))

    def on_signed_in(self, user_id):
        """Called if a user is signed in."""

    def on_signed_out(self, user_id):
        """Called if a user signs out."""

    def get_online_users(self):
        """Returns a list of all users currently online."""
        raise NotImplementedError()

    def is_user_online(self, user_id):
        """Checks if a user is online."""
        raise NotImplementedError()

    def on_subscribe(self, user_id, data):
        """Called if a user subscribes.  This might be called multiple
        times for a user since a user could have multiple tabs open.

        Has to call :meth:`on_signed_in`.
        """
        raise NotImplementedError()

    def on_unsubscribe(self, user_id, data):
        """Called if a user unsubscribes.  This might be called multiple
        times for a user since a user could have multiple tabs open.

        Has to call :meth:`on_signed_out`.
        """
        raise NotImplementedError()

    def handle_event(self, event, data):
        """Handles a single event and data."""
        user_id = self.get_user_id(data)
        if user_id is not None:
            if event == 'subscribe':
                self.on_subscribe(user_id, data)
            elif event == 'unsubscribe':
                self.on_unsubscribe(user_id, data)

    def run(self):
        """Runs the daemon."""
        for event, data in self.jug.subscribe_listen():
            self.handle_event(event, data)


class RedisRoster(Roster):
    """A roster implementation that stores the data in redis."""

    def __init__(self, jug=None, key_prefix='juggernaut-roster:',
                 user_meta_key='user_id'):
        Roster.__init__(self, jug)
        self.key_prefix = key_prefix
        self.user_meta_key = user_meta_key

    def get_online_users(self):
        return self.jug.redis.smembers(self.key_prefix + 'online-users')

    def is_user_online(self, user_id):
        key = '%sconnections:%s' % (self.key_prefix, user_id)
        return self.jug.redis.scard(key) > 0

    def on_subscribe(self, user_id, data):
        r = self.jug.redis
        key = '%sconnections:%s' % (self.key_prefix, user_id)
        r.sadd(key, data['session_id'])
        if r.scard(key) == 0:
            self.on_signed_in(user_id)
        r.sadd(self.key_prefix + 'online-users', user_id)

    def on_unsubscribe(self, user_id, data):
        r = self.jug.redis
        key = '%sconnections:%s' % (self.key_prefix, user_id)
        r.srem(key, data['session_id'])
        if r.scard(key) == 0:
            self.on_signed_out(user_id)
            r.sadd(self.key_prefix + 'online-users', user_id)
