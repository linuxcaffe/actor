import dbus

from plugins import IChecker

class NotificationAskChecker(IChecker):
    """
    Simple checker, that sends a D-Bus notification to ask user yes/no question.

    Accepted options:
      - message : Text of the message sent
      - question : Text of the question sent (Sample question?)
      - app_name: Application name (AcTor)
      - timeout : Timeout of the notification (0)
      - app_icon: Icon of the notification ('')
    """

    export_as = "ask"

    def __init__(self):
        super(NotificationAskChecker, self).__init__()
        self.last_notification = 0
        self.answer = ''
        self.bus = None

    def setup(self, **options):
        super(NotificationAskChecker, self).setup(**options)
        self.bus = dbus.SessionBus()
        self.bus.add_signal_receiver(self.set_answer, path='/org/freedesktop/Notifications', signal_name='ActionInvoked')
        self.question = self.options.get('question', '')

    def ask(self):

        if not self.answer:
            headline = self.options.get('headline', 'AcTor Alert!')
            app_name = self.options.get('app_name', 'AcTor')
            app_icon = self.options.get('app_icon', '')
            timeout = self.options.get('timeout', 0)
            message = self.options.get('question', 'Sample question this is?')

            choice_list = ["yes", "Yes", "no", "No"]

            replaces_id = self.last_notification

            bus_name = 'org.freedesktop.Notifications'
            object_path = '/org/freedesktop/Notifications'
            interface_name = bus_name

            dbus_object = self.bus.get_object(bus_name, object_path)
            interface = dbus.Interface(dbus_object, interface_name)

            self.last_notification = interface.Notify(app_name, replaces_id, app_icon,
                                                  headline, message, choice_list, {},
                                                  timeout)

        return self.answer == "yes"

    def set_answer(self, notification_id, answer_id):
        if notification_id == self.last_notification:
            self.answer = answer_id

    def check(self, **data):
        return self.ask()