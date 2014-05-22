from active_window_pid import ActiveWindowPidReporter

class ActiveWindowProcessNameReporter(ActiveWindowPidReporter):

    export_as = 'active_window_process_name'

    def report(self):
        pid = super(ActiveWindowProcessNameReporter, self).report()
        try:
            with open('/proc/%d/cmdline' % pid, 'r') as f:
                name = f.read()
        except IOError:
            name = ''

        return name
