import dbus
import time
import threading

import logger

# This file contains definitions of plugin classes, most of
# which intentionally do not implement their abstract method
# contracts.
# pylint: disable=abstract-method


class NoSuchPlugin(Exception):
    """
    Raised when a plugin could not be found.
    """
    pass


class PluginMount(type):

    def __init__(cls, name, bases, attrs):
        if not hasattr(cls, 'plugins'):
            cls.plugins = []
        else:
            # System generic plugin classes are marked with 'noplugin'
            # attribute. We do not want to mix those with user plugin
            # instances, so let's skip them
            if not 'noplugin' in cls.__dict__:
                cls.plugins.append(cls)


class Plugin(logger.LoggerMixin):

    def __init__(self, context):
        self.context = context

    # Convenience function for accessing worker modules
    def report(self, identifier, *args, **kwargs):
        return self.context.reporters.get(identifier, args, kwargs)

    def check(self, identifier, *args, **kwargs):
        return self.context.checkers.get(identifier, args, kwargs)

    def fix(self, identifier, *args, **kwargs):
        return self.context.fixers.get(identifier, args, kwargs)

    def factory_report(self, identifier, *args, **kwargs):
        return self.context.reporter_factory.make(identifier, args, kwargs)

    def factory_check(self, identifier, *args, **kwargs):
        return self.context.checker_factory.make(identifier, args, kwargs)

    def factory_fix(self, identifier, *args, **kwargs):
        return self.context.fixer_factory.make(identifier, args, kwargs)

    # Make sure every plugin implements the run method
    def run(self):
        """
        Method that actually provides the custom runtime logic shipped
        with the plugin.

        Plugins are expected to override this methods to perform their
        actions.
        """

        raise NotImplementedError("The run method needs to be"
                                  "implemented by the plugin itself")


class Worker(Plugin):
    """
    A base class for Reporter, Checker and Fixer.
    """

    stateless = True
    side_effects = False

    def evaluate(self, *args, **kwargs):
        """
        Wraps the run method. Currently only adds the debug logging.
        """

        self.debug('Running with args={0}, kwargs={1}'.format(args, kwargs))

        result = self.run(*args, **kwargs)
        self.debug('Result: {0}'.format(result))

        return result


class Reporter(Worker):
    """
    Reports user activity to the AcTor.
    """

    __metaclass__ = PluginMount


class Checker(Worker):
    """
    Evaluates user activity depending on the input from the responders.
    """

    __metaclass__ = PluginMount

    def __bool__(self):
        return self.run()


class Fixer(Worker):
    """
    Performs a custom action on the machine.
    """

    side_effects = True

    __metaclass__ = PluginMount


class ContextProxyMixin(object):
    """
    Provides a simplified interface to the workers exposed by the context.
    """

    @property
    def identifier(self):
        return self.__class__.__name__

    def report(self, identifier, *args, **kwargs):
        return self.context.reporters.get(identifier, args, kwargs,
                                          rule_name=self.identifier)

    def check(self, identifier, *args, **kwargs):
        return self.context.checkers.get(identifier, args, kwargs,
                                         rule_name=self.identifier)

    def fix(self, identifier, *args, **kwargs):
        return self.context.fixers.get(identifier, args, kwargs,
                                       rule_name=self.identifier)


class Rule(ContextProxyMixin, Plugin):
    """
    Performs custom rule.
    """

    __metaclass__ = PluginMount


class DBusMixin(object):
    """
    Sets the interface of the specified DBus object as self.interface. In case
    DBusException occurs during setup, self.interface is set to None.
    """

    bus_name = None        # i.e. 'org.freedesktop.PowerManagement'
    object_path = None     # i.e.'/org/freedesktop/PowerManagement'
    interface_name = None  # can be omitted, and bus_name will be used instead

    # This is the maximum timeout possible, see
    # http://dbus.freedesktop.org/doc/api/html/group__DBusPendingCall.html
    INFINITE_TIMEOUT = 0x7FFFFFFF / 1000.0

    def __init__(self, *args, **kwargs):
        super(DBusMixin, self).__init__(*args, **kwargs)

        try:
            self.bus = dbus.SessionBus()
            dbus_object = self.bus.get_object(self.bus_name, self.object_path)
            self.interface = dbus.Interface(dbus_object,
                                            self.interface_name or self.bus_name)
        except dbus.exceptions.DBusException:
            self.interface = None


class AsyncEvalMixinBase(object):

    """
    Base class for the asynchronous evaluation of the plugins. It makes
    sure that the plugin is evaluated in a separate thread, and hence
    it does not block the main execution loop of the program.

    This class is not to be used directly, instead one of the two child
    classes is supposed to be used:
        AsyncEvalNonBlockingMixin - does not block the thread, useful for
                                    plugins that leverage polling to obtain
                                    the data
        AsyncEvalBlockingMixin - blocks the thread, useful for the plugins
                                 that have data pushed using callbacks
    """

    stateless = False

    def __init__(self, *args, **kwargs):
        super(AsyncEvalMixinBase, self).__init__(*args, **kwargs)
        self.reset()

    def thread_handler(self, *args, **kwargs):
        raise NotImplementedError("This class is not meant to be run directly")

    def evaluate(self, *args, **kwargs):
        if not self.running and not self.completed:
            thread = threading.Thread(
                target=self.thread_handler,
                args=args,
                kwargs=kwargs
            )
            thread.start()
        elif self.completed:
            return self.result

    def reset(self):
        """
        Resets the cached result and state of the plugin.

        This method should be explicitly called after the value
        from the plugin has been pulled and processed, to allow the
        further re-use of this plugin instance.
        """

        self.running = False
        self.completed = False
        self.result = None


class AsyncEvalNonBlockingMixin(AsyncEvalMixinBase):
    """
    Async mixin for polling-based plugins. Does not block the thread.
    """

    def thread_handler(self, *args, **kwargs):
        self.running = True

        # Here we intentionally call the evaluate on the grandparent to avoid
        # getting into a deadlock
        # pylint: disable=bad-super-call
        self.result = super(AsyncEvalMixinBase, self).evaluate(*args, **kwargs)
        self.completed = True
        self.running = False


class AsyncEvalBlockingMixin(AsyncEvalMixinBase):
    """
    Async mixin for pushing-based plugins. Does block the thread, waiting
    for the result to be updated.
    """

    def thread_handler(self, *args, **kwargs):
        self.running = True
        super(AsyncEvalBlockingMixin, self).evaluate(*args, **kwargs)

        # Block until result is available
        while getattr(self, 'result', None) is None:
            time.sleep(1)

        self.completed = True
        self.running = False


class AsyncDBusEvalMixin(AsyncEvalNonBlockingMixin, DBusMixin):
    """
    Async mixin for pushing-based plugins leveraging async dbus
    calls.
    """

    def reply_handler(self, reply):
        self.result = reply

    def error_handler(self, error):
        # Raise the returned DBusException
        raise error
