import datetime
import dbus
import logging

class PluginMount(type):
    def __init__(cls, name, bases, attrs):
        if not hasattr(cls, 'plugins'):
            cls.plugins = []
        else:
            cls.plugins.append(cls)

class Plugin(object):

    def __init__(self, context):
        self.context = context

    # Logging-related helpers
    def log(self, log_func, message):
        log_func("%s: %s" % (self.__class__.__name__, message))

    def debug(self, message):
        self.log(logging.debug, message)

    def info(self, message):
        self.log(logging.info, message)

    def warning(self, message):
        self.log(logging.warning, message)

    def error(self, message):
        self.log(logging.error, message)

    def critical(self, message):
        self.log(logging.critical, message)

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
        raise NotImplementedError("The run method needs to be"
            "implemented by the plugin itself")


class Worker(Plugin):
    """
    A base class for Reporter, Checker and Fixer.
    """

    stateless = True
    side_effects = False

    def evaluate(self, *args, **kwargs):
        # TODO: Wrap in exception handling
        return self.run(*args, **kwargs)


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

class PythonRule(ContextProxyMixin, Plugin):
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

    def __init__(self, *args, **kwargs):
        super(DBusMixin, self).__init__(*args, **kwargs)

        try:
            self.bus = dbus.SessionBus()
            dbus_object = self.bus.get_object(self.bus_name, self.object_path)
            self.interface = dbus.Interface(dbus_object,
                                            self.interface_name or self.bus_name)
        except dbus.exceptions.DBusException:
            self.interface = None


class Activity(ContextProxyMixin, Plugin):

    __metaclass__ = PluginMount

    whitelist_commands = tuple()
    whitelist_titles = tuple()

    def run(self):
        """
        Enforces the allowed applications.
        """

        current_title = self.report('active_window_name')
        current_command = self.report('active_window_process_name')

        if not any([title in current_title for title in self.whitelist_titles] +
                   [command in current_command for command in self.whitelist_commands]):
            self.fix('notify', message="Application not allowed")
            self.fix('kill_process', pid=self.report('active_window_pid'))


class Flow(Plugin):
    """
    Defines a list of activities with their duration.
    """

    __metaclass__ = PluginMount

    activities = tuple()

    def __init__(self, context, actor):
        self.actor = actor
        self.current_activity_index = None
        self.current_activity_start = None

    @property
    def next_activity(self):
        try:
            return self.activities[(self.current_activity_index or 0) + 1]
        except IndexError:
            return None

    @property
    def current_activity(self):
        return self.activities[self.current_activity_index]

    @property
    def current_activity_expired(self):
        duration = datetime.timedelta(minutes=self.current_activity[1])
        end_time = self.current_activity_start + duration

        return datetime.datetime.now() > end_time

    def start(self, activity):
        self.current_activity_start = datetime.datetime.now()
        self.actor.set_activity(activity[0])

    def end(self):
        self.actor.unset_activity()
        self.current_activity_start = None

    def run(self):
        if self.current_activity_index is None:
            self.current_activity_index = 0
            self.start(self.current_activity)
        elif self.current_activity_expired and self.next_activity is not None:
            self.end()
            self.current_activity_index =+ 1
            self.start(self.current_activity)
        elif self.current_activity_expired and self.next_activity is None:
            self.end()
            self.actor.unset_flow()
