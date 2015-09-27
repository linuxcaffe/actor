import subprocess
import tempfile
import os
import dbus.mainloop.glib

from datetime import datetime
from test.base import ReporterTestCase
from util import run
from time import sleep
from tasklib import TaskWarrior, Task


class TimeReporterTest(ReporterTestCase):
    class_name = 'TimeReporter'
    module_name = 'time'

    def test_time_reporter(self):
        time = self.plugin.report()
        assert time == datetime.now().strftime("%H.%M")


class WeekdayReporterTest(ReporterTestCase):
    class_name = 'WeekdayReporter'
    module_name = 'time'

    def test_weekday_reporter(self):
        weekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        output, _, _ = run(['date', '+%w'])
        system_day = weekdays[int(output.strip())]

        day = self.plugin.report()
        assert day == system_day


class ActiveWindowReporterTest(ReporterTestCase):

    def setUp(self):
        super(ActiveWindowReporterTest, self).setUp()
        self.close('gedit')
        self.close('Calculator')
        sleep(0.5)
        subprocess.Popen(['gedit'])
        subprocess.Popen(['gnome-calculator'])
        sleep(0.5)

    def tearDown(self):
        self.close('gedit')
        self.close('Calculator')
        sleep(0.5)

    def activate(self, title_part):
        output = run(['xdotool', 'search', '--name', title_part])[0]
        window_ids = output.strip().splitlines()
        for window_id in window_ids:
            errors = run(['xdotool', 'windowactivate', window_id])[1]
        sleep(0.5)

    def close(self, title_part):
        output = run(['xdotool', 'search', '--name', title_part])[0]
        window_ids = output.strip().splitlines()
        for window_id in window_ids:
            errors = run(['xdotool', 'windowkill', window_id])[1]
        sleep(0.5)

class ActiveWindowNameReporterTest(ActiveWindowReporterTest):
    class_name = 'ActiveWindowNameReporter'
    module_name = 'active_window'

    def test_active_window_name_reporter(self):
        self.activate('gedit')
        window = self.plugin.report()
        assert type(window) == str
        assert 'gedit' in window

    def test_active_window_name_reporter_changing(self):
        self.activate('gedit')
        window = self.plugin.report()
        assert type(window) == str
        assert 'gedit' in window

        self.activate('Calculator')
        window = self.plugin.report()
        assert type(window) == str
        # The title depends on the package version
        assert 'Calculator' in window or 'gnome-calculator' in window

        self.activate('gedit')
        window = self.plugin.report()
        assert type(window) == str
        assert 'gedit' in window

class ActiveWindowPidReporterTest(ActiveWindowReporterTest):
    class_name = 'ActiveWindowPidReporter'
    module_name = 'active_window'

    def get_window_pid(self, title_part):
        self.activate(title_part)
        output = run(['xdotool', 'getwindowfocus', 'getwindowpid'])[0]
        xdopid = int(output.strip())
        return xdopid

    def setUp(self):
        super(ActiveWindowPidReporterTest, self).setUp()
        self.gedit_pid = self.get_window_pid('gedit')
        self.calc_pid = self.get_window_pid('Calculator')

    def test_active_window_pid_reporter(self):
        self.activate('gedit')
        pid = self.plugin.report()
        assert type(pid) == int
        assert pid == self.gedit_pid

    def test_active_window_pid_reporter_changing(self):
        self.activate('gedit')
        pid = self.plugin.report()
        assert type(pid) == int
        assert pid == self.gedit_pid

        self.activate('Calculator')
        pid = self.plugin.report()
        assert type(pid) == int
        assert pid == self.calc_pid

        self.activate('gedit')
        pid = self.plugin.report()
        assert type(pid) == int
        assert pid == self.gedit_pid


class ActiveWindowProcessNameReporterTest(ActiveWindowReporterTest):
    class_name = 'ActiveWindowProcessNameReporter'
    module_name = 'active_window'

    def test_active_process_name_reporter(self):
        self.activate('gedit')
        process = self.plugin.report()
        assert type(process) == str
        assert 'gedit' in process

    def test_active_process_name_reporter_changing(self):
        self.activate('gedit')
        process = self.plugin.report()
        assert type(process) == str
        assert 'gedit' in process

        self.activate('Calculator')
        process = self.plugin.report()
        assert type(process) == str
        assert 'gnome-calculator' in process

        self.activate('gedit')
        process = self.plugin.report()
        assert type(process) == str
        assert 'gedit' in process

class FileContentReporterTest(ReporterTestCase):
    class_name = 'FileContentReporter'
    module_name = 'file_content'

    def setUp(self):
        self.tempfile = tempfile.NamedTemporaryFile()
        self.options.update({'path': self.tempfile.name})

        self.tempfile.write("aaa\n")
        self.tempfile.write("bbb\n")
        self.tempfile.write("ccc\n")
        self.tempfile.flush()

        super(FileContentReporterTest, self).setUp()

    def test_file_content_reporter(self):
        file_content = self.plugin.report()
        assert type(file_content) == str
        assert len(file_content) > 0
        assert "aaa" in file_content
        assert "bbb" in file_content
        assert "ccc" in file_content


class HamsterActivityReporterTest(ReporterTestCase):
    class_name = 'HamsterActivityReporter'
    module_name = 'hamster'

    def setUp(self):
        run(['killall', 'hamster-service'])
        self.hamster_db_file = os.path.expanduser("~/.local/share/hamster-applet/hamster.db")

        if os.path.isfile(self.hamster_db_file):
            os.rename(self.hamster_db_file, self.hamster_db_file + "-backup-actor-tests")

        run(['hamster', 'start', "something@Home"])
        sleep(1)
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        super(HamsterActivityReporterTest, self).setUp()

    def tearDown(self):
        run(['killall', 'hamster-service'])

        if os.path.isfile(self.hamster_db_file + "-backup-actor-tests"):
            os.rename(self.hamster_db_file + "-backup-actor-tests", self.hamster_db_file)

        run(['hamster', 'current'])

    def test_correct_activity(self):
        assert self.plugin.report() == "something@Home"

        run(['hamster', 'start', 'other@Home'])

        # We need to update the activity manually, since tests
        # do not listen to the DBUS signals
        self.plugin.get_current_activity()
        assert self.plugin.report() == "other@Home"


class TaskTestBase(object):
    module_name = 'taskwarrior'

    def setUp(self):
        self.data = tempfile.mkdtemp()
        self.warrior = TaskWarrior(data_location=self.data)
        super(TaskTestBase, self).setUp()

    def initialize(self, **options):
        warrior_options = {'data_location': self.data}

        if not 'warrior_options' in options:
            options['warrior_options'] = warrior_options
        else:
            options['warrior_options'].update(warrior_options)

        self.plugin = self.plugin_class(
                rule_name="test",
                **options
            )


class TaskWarriorReporterTest(TaskTestBase, ReporterTestCase):
    class_name = 'TaskWarriorReporter'

    def test_empty_tasklist(self):
        assert self.plugin.report() == ''

    def test_correct_description(self):
        Task(self.warrior, description="test").save()
        assert self.plugin.report() == "test"

    def test_filtered_description(self):
        self.initialize(filter=dict(project="work"))
        Task(self.warrior, project="work", description="work task1").save()
        Task(self.warrior, project="home", description="home task1").save()

        assert self.plugin.report() == "work task1"


class TaskCountReporterTest(TaskTestBase, ReporterTestCase):
    class_name = 'TaskCountReporter'

    def test_empty_tasklist(self):
        assert self.plugin.report() == 0

    def test_correct_description(self):
        Task(self.warrior, description="test").save()
        assert self.plugin.report() == 1

    def test_filtered_description(self):
        self.initialize(filter=dict(project="work"))
        Task(self.warrior, project="work", description="work task1").save()
        Task(self.warrior, project="home", description="home task1").save()

        assert self.plugin.report() == 1
