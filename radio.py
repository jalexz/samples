'********************************************************************************
'* The following is a python program that I wrote in order to listen to 		* 
'* internet radio stations on my old Acer Aspire One netbook running Arch		*
'* Linux. This program kicked in straight after boot, thus transforming my		*
'* otherwise useless netbook into a sort of web radio (with alarm clock too!).	*
'********************************************************************************/
 
import curses
import curses.ascii
import curses.panel
import datetime
import enum
import itertools
import json
import logging
import os
import subprocess
import time
import traceback
import urllib.parse

LOGGING_FILE = '.logfile'
LOGGING_FORMAT = '%(asctime)s %(levelname)s %(message)s'
LOGGING_LEVEL = logging.DEBUG

PREFERENCES_FILE = '.saved_prefs'

BATTERY_STATUS_FILE = '/sys/class/power_supply/BAT0/status'
BATTERY_CHARGE_FILE = '/sys/class/power_supply/BAT0/capacity'
BATTERY_UPDATE_TIME = 2
BATTERY_LOW_CHARGE = 10

START_VOLUME = 40
VOLUME_MAX = 100
VOLUME_MIN = 0
VOLUME_DELTA = 5
SOFTVOL_GAIN = 400

ALARM_TIME = (0, 0)
ALARM_ON = False
ALARM_RINGING_DURATION = 1800
MAX_SNOOZES = 3
SNOOZE_DURATION = 600

CHANNELS_FILE = 'radio_channels'
ALARM_CHANNEL = None

CURSES_UPDATE_TIME = 1/60

UP_ARROW_CH = u"\u25B2"
DOWN_ARROW_CH = u"\u25BC"
RIGHT_ARROW_CH = u"\u25B6"
LEFT_ARROW_CH = u"\u25C0"
LIGHT_SHADE_CH = u"\u2591"
MEDIUM_SHADE_CH = u"\u2592"
DARK_SHADE_CH = u"\u2593"
BLACK_DIAMOND_CH = u"\u25C6"

class System:

    """Utility for system operations"""
    
    class BatteryState(enum.Enum):
        unknown = 0
        charging = 1
        discharging = 2
        
    def read_sys_file(file_path):
        with open(file_path, 'r') as f:
            return f.readline().rstrip('\n')

    def get_battery_status():
        s = System.read_sys_file(BATTERY_STATUS_FILE)
        if s == 'Discharging':
            return System.BatteryState.discharging
        elif s == 'Charging':
            return System.BatteryState.charging
        else:
            return System.BatteryState.unknown

    def get_battery_charge():
        return round(float(System.read_sys_file(BATTERY_CHARGE_FILE)))
    
    def set_wake_time_after_seconds(seconds):
        if seconds > 0:
            args = ['sudo', '/usr/bin/rtcwake', '-m', 'no', '-s', '{0:d}'.format(seconds)]
        else:
            args = ['sudo', '/usr/bin/rtcwake', '-m', 'disable']
        subprocess.Popen(args, stdout=subprocess.DEVNULL)
    
    def poweroff():
        args = ['sudo', '/usr/bin/poweroff']
        subprocess.Popen(args, stdout=subprocess.DEVNULL)
        
class Preferences:

    """Application wide preferences with file load/save functionalities"""

    def __init__(self, default_values, preferences_file):
        self._prefs_dict = dict(default_values)
        self._preferences_file = preferences_file
        self._prefs_dict.update(Preferences.load_from_file(self._preferences_file))

    def __del__(self):
        pass

    def __getitem__(self, key):
        return self._prefs_dict[key]

    def __setitem__(self, key, val):
        self._prefs_dict[key] = val

    def save(self):
        Preferences.save_to_file(self._prefs_dict, self._preferences_file)
    
    def load_from_file(file_path):
        logging.info('loading preferences from file {0}'.format(file_path))
        result = dict()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                result.update((json.load(f)))
        except ValueError as err:
            logging.warning('could not parse preferences from file: {0}'.format(err))
        except OSError as err:
            logging.warning('could not load preferences from file: {0}'.format(err))
        return result

    def save_to_file(values, file_path):
        logging.info('saving preferences to file: {0}'.format(file_path))
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(values, f, indent=2, sort_keys=True)

class MPlayer:

    """Basic MPlayer wrapper"""

    def __init__(self, softvol_gain, initial_volume):
        args = ['/usr/bin/mplayer', '-nogui', '-quiet', '-idle', '-slave', '-input', 'nodefault-bindings', '-noconfig', 'all', '-softvol', '-softvol-max', '{0:d}'.format(softvol_gain), '-volume', '{0:d}'.format(initial_volume)]
        logging.info('starting mplayer process with line: "{0}"'.format(' '.join(args)))
        self._process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._stdin = self._process.stdin
        logging.info('mplayer process successfully started')
    
    def __del__(self):
        self.stop()

    def command(self, cmd):
        logging.debug('mplayer command: [{0}]'.format(cmd))
        cmd_line = '{0}\n'.format(cmd)
        cmd_bytes = bytes(cmd_line, 'ascii')
        self._stdin.write(cmd_bytes)
        self._stdin.flush()

    def loadlist(self, name, append):
        self.command('loadlist {0} {1:d}'.format(name, int(append)))

    def loadfile(self, name, append):
        self.command('loadfile {0} {1:d}'.format(name, int(append)))

    def pause(self):
        self.command('pause')
    
    def stop(self):
        self._process.terminate()
    
    def mute(self, value):
        self.command('mute {0:d}'.format(val))

    def volume(self, value, absolute):
        self.command('volume {0:d} {1:d}'.format(value, int(absolute)))
    
class RadioChannel:

    """Radio channel data"""

    def __init__(self, name, url, format=''):
        if RadioChannel.is_valid_name(name):
            self._name = name
        else:
            raise Exception('No name specified!')
        if RadioChannel.is_valid_url(url):
            self._url = url
        else:
            raise Exception('Invalid url "{0}"'.format(url))

    def is_valid_name(name):
        return name != None

    def is_valid_url(url):
        r = None
        try:
            r = urllib.parse.urlparse(url)
        except:
            pass
        return r != None and r.scheme != '' and r.netloc != '' and r.path != ''

class CoreRadio:
    
    """Implements core radio functions"""
    
    def __init__(self, prefs):
        self._prefs = prefs
        self._channels_dict = dict()
        self._playing_channel = None
        self._is_paused = False
        self._volume = self._prefs['CoreRadio.StartVolume']
        logging.info('initial volume set to {0:d}'.format(self._volume))    
        self._mplayer = None

    def load_radio_list(self, list_file_path):
        logging.info('loading channels from file "{0}"'.format(list_file_path))
        self._channels_dict.clear()
        channel_list = list() # preserves channel's order of appearance in the file
        with open(list_file_path, 'r') as f:
            line_counter = 0
            for line in f:
                line = line.strip()
                line_counter += 1
                if not (len(line) == 0 or line[0] == '#'):
                    tokens = line.rstrip().split('|')
                    if len(tokens) > 1:
                        try:
                            channel = RadioChannel(tokens[0], tokens[1])
                            if channel._name in self._channels_dict:
                                logging.warning('overwriting channel "{0}"!', channel._name)
                            self._channels_dict[channel._name] = channel
                            channel_list.append(channel._name)
                        except Exception as e:
                            logging.warning('skipping invalid line: {0:d}.\n{1}'.format(line_counter, e.args))
                    else:
                        logging.warning('skipping invalid line: {0:d}.\nNot enough arguments.'.format(line_counter))
        logging.info('found {0:d} channel(s):'.format(len(channel_list)))
        for channel_name in channel_list:
            logging.info('  {0}'.format(channel_name))
        return channel_list

    def play(self, channel_name, volume=None):
        self.stop()
        if channel_name in self._channels_dict:
            logging.info('start playing channel {0}'.format(channel_name))
            if volume != None:
                self._volume = volume
                logging.debug('changed volume to {0:d}'.format(self._volume))
            self._mplayer = MPlayer(self._prefs['CoreRadio.SoftvolGain'], self._volume)
            self._playing_channel = self._channels_dict[channel_name]
            self._mplayer.loadlist(self._playing_channel._url, True)
        else:
            logging.error('can\'t play unknown channel "{0}"!'.format(channel_name)) 
        return

    def stop(self):
        self._playing_channel = None
        if self._mplayer:
            self._mplayer.stop()
        self._mplayer = None
        return
    
    def pause(self):
        if self._mplayer:
            self._is_paused = not self._is_paused
            self._mplayer.pause()
        else:
            logging.info('won\'t pause, player is already stopped')

    def get_volume(self):
        return self._volume
        
    def get_max_volume(self):
        return self._prefs['CoreRadio.VolumeMax']
        
    def increase_volume(self):
        self._volume = min(self._volume + self._prefs['CoreRadio.VolumeDelta'], self._prefs['CoreRadio.VolumeMax'])
        logging.info('changed volume to {0:d}'.format(self._volume))
        if self._mplayer:
            self._mplayer.volume(self._volume, True)

    def decrease_volume(self):
        self._volume = max(self._volume - self._prefs['CoreRadio.VolumeDelta'], self._prefs['CoreRadio.VolumeMin'])
        logging.info('changed volume to {0:d}'.format(self._volume))
        if self._mplayer:
            self._mplayer.volume(self._volume, True)

    def get_playing_channel(self):
        if self.is_playing():
            return self._playing_channel._name
        else:
            return 0
    
    def is_playing(self):
        return self._playing_channel and self._mplayer

    def sync_preferences(self):
        self._prefs['CoreRadio.StartVolume'] = self._volume

    def get_default_preferences():
        result = dict()
        result['CoreRadio.StartVolume'] = START_VOLUME
        result['CoreRadio.VolumeMax'] = VOLUME_MAX
        result['CoreRadio.VolumeMin'] = VOLUME_MIN
        result['CoreRadio.VolumeDelta'] = VOLUME_DELTA
        result['CoreRadio.SoftvolGain'] = SOFTVOL_GAIN
        return result

class ClockRadio:

    """Implements standard clock radio functions"""

    class AlarmState(enum.Enum):
        waiting = 0
        ready_to_ring = 1
        ringing = 2
        snooze = 3
        
    def __init__(self, prefs):
        self._alarm_state = ClockRadio.AlarmState.waiting
        self._prefs = prefs
        self._alarm_on = self._prefs['ClockRadio.AlarmOn']
        self._alarm_time = self._prefs['ClockRadio.AlarmTime']
        self._alarm_channel = self._prefs['ClockRadio.AlarmChannel']
        self._alarm_volume = self._prefs['ClockRadio.AlarmVolume']
        self._alarm_date = datetime.datetime.now()
        self._alarm_date = self.get_next_alarm_date()
        self._core_radio = CoreRadio(self._prefs)
        self._channel_names = self._core_radio.load_radio_list(self._prefs['ClockRadio.ChannelsFile'])
        if not (self._alarm_channel in self._channel_names):
            if len(self._channel_names) > 0:
                self._alarm_channel = self._channel_names[0]
            else:
                self._alarm_channel = None
        self._fire_event_listener = None
        self._ringing_timeout_event_listener = None
        self._snooze_timeout_event_listener = None
        self._ringing_start_time = -1
        self._snooze_start_time = -1
        self._snooze_counter = 0
        self.update_wake_up_time()

    def __del__(self):
        pass
     
    def is_alarm_on(self):
        return self._alarm_on

    def set_alarm_on(self, flag):
        self._alarm_on = flag
        self.update_wake_up_time()
        
    def get_alarm_time(self):
        return self._alarm_time
    
    def get_alarm_volume(self):
        return self._alarm_volume
    
    def get_alarm_max_volume(self):
        return self._prefs['ClockRadio.VolumeMax']
        
    def get_alarm_channel(self):
        return self._alarm_channel
    
    def set_alarm_time(self, time):
        self._alarm_time = time
        logging.info('alarm time is {0:d}:{1:02d}'.format(self._alarm_time[0], self._alarm_time[1]))
        self._alarm_date = self.get_next_alarm_date()
        self._alarm_time_changed = True
        self.update_wake_up_time()
    
    def increase_alarm_volume(self):
        self._alarm_volume = min(self._alarm_volume + self._prefs['ClockRadio.VolumeDelta'], self._prefs['ClockRadio.VolumeMax'])
        logging.info('changed alarm volume to {0:d}'.format(self._alarm_volume))

    def decrease_alarm_volume(self):
        self._alarm_volume = max(self._alarm_volume - self._prefs['ClockRadio.VolumeDelta'], self._prefs['ClockRadio.VolumeMin'])
        logging.info('changed alarm volume to {0:d}'.format(self._alarm_volume))
        
    def set_alarm_channel(self, channel):
        self._alarm_channel = channel

    def get_alarm_date(self):
        return self._alarm_date
        
    def get_alarm_datetime(self):
        return datetime.datetime.combine(self._alarm_date, datetime.time(hour=self._alarm_time[0], minute=self._alarm_time[1]))
    
    def toggle_alarm(self):
        if self._alarm_channel:
            self.set_alarm_on(not self._alarm_on)
        else:
            self.set_alarm_on(False)
    
    def get_next_alarm_date(self):
        now = datetime.datetime.now()
        alarm_end = datetime.datetime.combine(now.date(), datetime.time(hour=self._alarm_time[0], minute=self._alarm_time[1])) + datetime.timedelta(minutes=1)
        if now < alarm_end:
            return now.date()
        else:
            return now.date() + datetime.timedelta(days=1)
            
    def is_ready_to_ring(self):
        now = datetime.datetime.now()
        now_date = now.date()
        now_time = now.time()
        return now_date == self._alarm_date and [now_time.hour, now_time.minute] == self._alarm_time
        
    def get_available_channels(self):
        return self._channel_names
    
    def is_radio_playing(self):
        return self._core_radio.is_playing()

    def get_playing_channel(self):
        return self._core_radio.get_playing_channel()
    
    def stop_radio(self):
        if self.is_radio_playing():
            self._core_radio.stop()
    
    def play_radio(self, channel_name):
        self._core_radio.play(channel_name)
        
    def get_radio_volume(self):
        return self._core_radio.get_volume()
        
    def get_radio_max_volume(self):
        return self._core_radio.get_max_volume()
        
    def increase_radio_volume(self):
        self._core_radio.increase_volume()
    
    def decrease_radio_volume(self):
        self._core_radio.decrease_volume()
    
    def set_fire_event_listener(self, listener):
        self._fire_event_listener = listener

    def set_ringing_timeout_event_listener(self, listener):
        self._ringing_timeout_event_listener = listener
    
    def set_snooze_timeout_event_listener(self, listener):
        self._snooze_timeout_event_listener = listener
        
    def get_ringing_countdown(self):
        if self._alarm_state == ClockRadio.AlarmState.ringing:
            ringing_time = time.clock() - self._ringing_start_time
            return self._prefs['ClockRadio.RingingDuration'] - ringing_time
        else:
            return 0
    
    def get_snooze_countdown(self):
        if self._alarm_state == ClockRadio.AlarmState.snooze:
            snooze_time = time.clock() - self._snooze_start_time
            return self._prefs['ClockRadio.SnoozeDuration'] - snooze_time
        else:
            return 0
            
    def next_snooze_quits(self):
        return self._snooze_counter == self._prefs['ClockRadio.MaxSnoozes']
        
    def snooze(self):
        if self._alarm_state == ClockRadio.AlarmState.ringing:
            self._core_radio.stop()
            self._snooze_counter += 1
            if self._snooze_counter <= self._prefs['ClockRadio.MaxSnoozes']:
                self.do_transition(ClockRadio.AlarmState.snooze)
                return True
            else:
                self._snooze_counter = 0
                self.exit_alarm()
                return False
        else:
            raise Exception('Cannot snooze while in state {0}'.format(self._alarm_state))
    
    def exit_alarm(self):
        if self._alarm_state == ClockRadio.AlarmState.ringing:
            self.do_transition(ClockRadio.AlarmState.waiting)
        elif self._alarm_state == ClockRadio.AlarmState.snooze:
            self.do_transition(ClockRadio.AlarmState.waiting)
        else:
            raise Exception('Cannot exit alarm while in state {0}'.format(self._alarm_state))
            
    def update_wake_up_time(self):
        if self._alarm_on:
            alarm_datetime = datetime.datetime.combine(self._alarm_date, datetime.time(hour=self._alarm_time[0], minute=self._alarm_time[1], second=0))
            logging.info('wake up time set to: {0}'.format(alarm_datetime))
            # Must provide a value greater than 0, otherwise the wake up time will be disabled
            alarm_after_seconds = max(1, round((alarm_datetime - datetime.datetime.now()).total_seconds()))
            logging.debug('wake up in {0:d} seconds'.format(alarm_after_seconds))
            System.set_wake_time_after_seconds(alarm_after_seconds)
        else:
            logging.info('wake up time disabled')
            System.set_wake_time_after_seconds(0)
        
    def set_alarm_tomorrow(self):
        self._alarm_date = datetime.datetime.now().date() + datetime.timedelta(days=1)
        
    # To be used in any wrapper main loop
    def update(self, dont_fire_alarm=False):
        if self._alarm_state == ClockRadio.AlarmState.waiting:
            if self.is_ready_to_ring():
                self.do_transition(ClockRadio.AlarmState.ready_to_ring)
        elif self._alarm_state == ClockRadio.AlarmState.ready_to_ring:
            if not self.is_ready_to_ring():
                self.do_transition(ClockRadio.AlarmState.waiting)
            elif self._alarm_on and not (self._core_radio.is_playing() or dont_fire_alarm):
                logging.debug('firing alarm!')
                self._core_radio.play(self._alarm_channel, self._alarm_volume)
                if self._fire_event_listener:
                    self._fire_event_listener()
                self.do_transition(ClockRadio.AlarmState.ringing)
        elif self._alarm_state == ClockRadio.AlarmState.ringing:
            if self.get_ringing_countdown() <= 0:
                self._core_radio.stop()
                if self._ringing_timeout_event_listener:
                    self._ringing_timeout_event_listener()
                self.do_transition(ClockRadio.AlarmState.waiting)
        elif self._alarm_state == ClockRadio.AlarmState.snooze:
            if self.get_snooze_countdown() <= 0:
                self._core_radio.play(self._alarm_channel, self._alarm_volume)
                if self._snooze_timeout_event_listener:
                    self._snooze_timeout_event_listener()
                self.do_transition(ClockRadio.AlarmState.ringing)
        self._alarm_time_changed = False
        
    def do_transition(self, next_state):
        if self._alarm_state == ClockRadio.AlarmState.waiting and next_state == ClockRadio.AlarmState.ready_to_ring:
            pass
        elif self._alarm_state == ClockRadio.AlarmState.ready_to_ring and next_state == ClockRadio.AlarmState.waiting:
            if not self._alarm_time_changed:
                self.set_alarm_tomorrow()
            self.update_wake_up_time()
        elif self._alarm_state == ClockRadio.AlarmState.ready_to_ring and next_state == ClockRadio.AlarmState.ringing:
           if not self._alarm_time_changed:
                self.set_alarm_tomorrow()
           self.update_wake_up_time()
           self._ringing_start_time = time.clock()
           self._snooze_start_time = -1
        elif self._alarm_state == ClockRadio.AlarmState.ringing and next_state == ClockRadio.AlarmState.waiting:
            self._ringing_start_time = -1
            self._snooze_start_time = -1
        elif self._alarm_state == ClockRadio.AlarmState.ringing and next_state == ClockRadio.AlarmState.snooze:
            self._snooze_start_time = time.clock()
            self._ringing_start_time = -1
        elif self._alarm_state == ClockRadio.AlarmState.snooze and next_state == ClockRadio.AlarmState.waiting:
            self._ringing_start_time = -1
            self._snooze_start_time = -1
        elif self._alarm_state == ClockRadio.AlarmState.snooze and next_state == ClockRadio.AlarmState.ringing:
           self._ringing_start_time = time.clock()
           self._snooze_start_time = -1
        else:
            raise Exception('Unknown transition: {0} -> {1}'.format(self._alarm_state, next_state))
        self._alarm_state = next_state
        
    def sync_preferences(self):
        self._prefs['ClockRadio.AlarmOn'] = self._alarm_on
        self._prefs['ClockRadio.AlarmTime'] = self._alarm_time
        self._prefs['ClockRadio.AlarmChannel'] = self._alarm_channel
        self._prefs['ClockRadio.AlarmVolume'] = self._alarm_volume
        self._core_radio.sync_preferences()
        
    def get_default_preferences():
        result = dict()
        result['ClockRadio.AlarmOn'] = ALARM_ON
        result['ClockRadio.AlarmTime'] = ALARM_TIME
        result['ClockRadio.ChannelsFile'] = CHANNELS_FILE
        result['ClockRadio.AlarmChannel'] = ALARM_CHANNEL
        result['ClockRadio.AlarmVolume'] = START_VOLUME
        result['ClockRadio.VolumeMax'] = VOLUME_MAX
        result['ClockRadio.VolumeMin'] = VOLUME_MIN
        result['ClockRadio.VolumeDelta'] = VOLUME_DELTA
        result['ClockRadio.RingingDuration'] = ALARM_RINGING_DURATION
        result['ClockRadio.MaxSnoozes'] = MAX_SNOOZES
        result['ClockRadio.SnoozeDuration'] = SNOOZE_DURATION
        result.update(CoreRadio.get_default_preferences())
        return result

class CursesWrapper:

    """Implements the ncurses frontend for ClockRadio"""

    class Action(enum.Enum):
        no_op = -1
        push_top = 0
        switch_top = 1
        pop_self = 2
        switch_self = 3
        pop = 4
    
    class KeyMappings:
        quit_app = [curses.ascii.ESC]
        alarm_tab = [ord('A'), ord('a')]
        radio_tab = [ord('R'), ord('r')]
        change_channel_up = [curses.KEY_UP]
        change_channel_down = [curses.KEY_DOWN]
        increase_volume = [curses.KEY_RIGHT]
        decrease_volume = [curses.KEY_LEFT]
        play_radio = [ord('P'), ord('p')]
        stop_radio = [ord('S'), ord('s')]
        enable_alarm = [ord('E'), ord('e')]
        disable_alarm = [ord('D'), ord('d')]
        set_alarm_time = [ord('T'), ord('t')]
        cancel_dialog = [curses.ascii.ESC]
        poweroff = [ord('P'), ord('p')]
        quit_to_terminal = [ord('Q'), ord('q')]
        enter_input = [curses.ascii.NL]
        cancel_input = [curses.ascii.ESC]
        increase_time = [curses.KEY_UP]
        decrease_time = [curses.KEY_DOWN]
        next_digit = [curses.KEY_RIGHT]
        previous_digit = [curses.KEY_LEFT]
        exit_alarm = [curses.ascii.ESC]
        
    main_frame = None
    radio_frame = None
    alarm_frame = None
    exit_dialog = None
    alarm_dialog = None

    def __init__(self, prefs):
        self._prefs = prefs
        self._current_channel = self._prefs['CursesWrapper.CurrentChannel']
        self._current_window = None
        self._current_panel = None
        self._screen_size = (0, 0)
        CursesWrapper.main_frame = CursesWrapper.MainFrameState(self)
        CursesWrapper.radio_frame = CursesWrapper.RadioFrameState(self)
        CursesWrapper.alarm_frame = CursesWrapper.AlarmFrameState(self)
        CursesWrapper.exit_dialog = CursesWrapper.ExitDialogState(self)
        CursesWrapper.alarm_dialog = CursesWrapper.AlarmDialogState(self)
        CursesWrapper.snooze_dialog = CursesWrapper.SnoozeDialogState(self)
        CursesWrapper.insert_alarm_time_dialog = CursesWrapper.InsertAlarmTimeDialogState(self)
        
        self._clock_radio = ClockRadio(self._prefs)
        self._states_stack = list()
        os.environ['ESCDELAY'] = '25' # Reduces the delay after pressing ESC in curses
        curses.wrapper(CursesWrapper.main_loop, self)
    
    def __del__(self):
        pass
    
    def main_loop(window, self):
        self._current_window = window
        self._screen_size = self._current_window.getmaxyx()
        self._current_panel = curses.panel.new_panel(window)
        curses.panel.update_panels()
        curses.curs_set(0)
        window.nodelay(1)
        self.push_state(CursesWrapper.main_frame)
        self.push_state(CursesWrapper.radio_frame)
        last_draw_time = -CURSES_UPDATE_TIME
        while len(self._states_stack) > 0:
            self.clear_input()
            self.consume_input(window)
            self.update()
            if time.clock() - last_draw_time > CURSES_UPDATE_TIME:
                self.draw()
                last_draw_time = time.clock()
        window.clear()
        window.noutrefresh()
        curses.doupdate()

    def get_screen_size(self):
        return self._screen_size
        
    def get_current_window(self):
        return self._current_window
    
    def set_current_window(self, window):
        self._current_window = window
        
    def top_state(self):
        return self._states_stack[-1]

    def bottom_state(self):
        return self._states_stack[0]

    def push_state(self, state):
        logging.debug('push_state({0})'.format(type(state).__name__))
        self._states_stack.append(state)
        logging.debug('{0}.on_enter()'.format(type(state).__name__))
        self.top_state().on_enter()

    def pop_state(self, state):
       logging.debug('pop_state({0})'.format(type(state).__name__))
       while True:
        s = self._states_stack.pop()
        logging.debug('{0}.on_exit()'.format(type(s).__name__))
        s.on_exit()
        if s == state:
            break

    def draw(self):
        for s in self._states_stack:
            s.draw()
        curses.doupdate()

    def clear_input(self):
        for s in reversed(self._states_stack):
            s.clear_input()

    def consume_input(self, window):
        ch = window.getch()
        if ch != -1:
            logging.debug('typed character {0:d}'.format(ch))
            for s in reversed(self._states_stack):
                if s.consume_input(ch):
                    logging.debug('{0}.consume_input({1:d})'.format(type(s).__name__, ch))
                    return
            curses.beep()

    def update_clock_radio_state(self):
        dont_fire_alarm = self.top_state() != CursesWrapper.radio_frame
        self._clock_radio.update(dont_fire_alarm=dont_fire_alarm)
        
    def update(self):
        self.update_clock_radio_state()
        actions_stack = list()
        for s in reversed(self._states_stack):
            actions_stack.insert(0, (s.update()))
        for i in reversed(range(len(actions_stack))):
            (action, args) = actions_stack[i]
            if action == CursesWrapper.Action.pop_self:
                self.pop_state(self._states_stack[i])
            elif action == CursesWrapper.Action.switch_top:
                self.pop_state(self._states_stack[-1])
                self.push_state(args)
            elif action == CursesWrapper.Action.push_top:
                self.push_state(args)
            elif action == CursesWrapper.Action.pop:
                self.pop_state(args)
            elif action == CursesWrapper.Action.switch_self:
                self.pop_state(self._states_stack[i])
                self.push_state(args)
            elif action == CursesWrapper.Action.no_op:
                pass # Do nothing
            else:
                raise Exception('Not implemented: {0}'.format(action))

    def sync_preferences(self):
        self._prefs['CursesWrapper.CurrentChannel'] = self._current_channel
        self._clock_radio.sync_preferences()

    def get_default_preferences():
        result = dict()
        result['CursesWrapper.CurrentChannel'] = None
        result.update(ClockRadio.get_default_preferences())
        return result

    class BaseState:

        """Default implementation for all GUI states"""

        def __init__(self, fsm):
            self._fsm = fsm
            self._ch = -1

        def __del__(self):
            pass

        def on_enter(self):
            pass

        def on_exit(self):
            pass

        def draw(self):
            pass

        def clear_input(self):
            self._ch = -1
            
        def consume_input(self, ch):
            self._ch = -1
            return False

        def update(self):
            return (CursesWrapper.Action.no_op, None)

        def get_screen_size(self):
            return self._fsm.get_screen_size()
            
        def get_current_window(self):
            return self._fsm.get_current_window()
        
        def set_current_window(self, window):
            self._fsm.set_current_window(window)
        
        def top_state(self):
            return self._fsm.top_state()

        def bottom_state(self):
            return self._fsm.bottom_state()
        
        def is_alarm_on(self):
            return self._fsm._clock_radio.is_alarm_on()

        def toggle_alarm(self):
            return self._fsm._clock_radio.toggle_alarm()
            
        def get_alarm_time(self):
            return self._fsm._clock_radio.get_alarm_time()

        def get_alarm_volume(self):
            return self._fsm._clock_radio.get_alarm_volume()

        def get_alarm_max_volume(self):
            return self._fsm._clock_radio.get_alarm_max_volume()
            
        def get_alarm_channel(self):
            return self._fsm._clock_radio.get_alarm_channel()

        def set_alarm_time(self, time):
            self._fsm._clock_radio.set_alarm_time(time)

        def increase_alarm_volume(self):
            self._fsm._clock_radio.increase_alarm_volume()
        
        def decrease_alarm_volume(self):
            self._fsm._clock_radio.decrease_alarm_volume()
            
        def set_alarm_channel(self, channel):
            self._fsm._clock_radio.set_alarm_channel(channel)
            
        def get_radio_channels(self):
            return self._fsm._clock_radio.get_available_channels()
        
        def get_playing_channel(self):
            return self._fsm._clock_radio.get_playing_channel()

        def is_radio_playing(self):
            return self._fsm._clock_radio.is_radio_playing()
        
        def stop_radio(self):
            self._fsm._clock_radio.stop_radio()
        
        def play_radio(self):
            self._fsm._clock_radio.play_radio(self.get_current_channel())
            
        def get_radio_volume(self):
            return self._fsm._clock_radio.get_radio_volume()
        
        def get_radio_max_volume(self):
            return self._fsm._clock_radio.get_radio_max_volume()
           
        def increase_radio_volume(self):
            self._fsm._clock_radio.increase_radio_volume()
        
        def decrease_radio_volume(self):
            self._fsm._clock_radio.decrease_radio_volume()
            
        def set_current_channel(self, channel):
            self._fsm._current_channel = channel
        
        def get_current_channel(self):
            return self._fsm._current_channel
            
        def next_snooze_quits(self):
            return self._fsm._clock_radio.next_snooze_quits()
            
        def snooze(self):
            return self._fsm._clock_radio.snooze()
        
        def exit_alarm(self):
            self._fsm._clock_radio.exit_alarm()
            
        def get_ringing_countdown(self):
            return self._fsm._clock_radio.get_ringing_countdown()
            
        def get_snooze_countdown(self):
            return self._fsm._clock_radio.get_snooze_countdown()

        def set_fire_event_listener(self, listener):
            self._fsm._clock_radio.set_fire_event_listener(listener)

        def set_ringing_timeout_event_listener(self, listener):
            self._fsm._clock_radio.set_ringing_timeout_event_listener(listener)

        def set_snooze_timeout_event_listener(self, listener):
            self._fsm._clock_radio.set_snooze_timeout_event_listener(listener)
               
        def save_preferences(self):
            self._fsm.sync_preferences()
            self._fsm._prefs.save()
        
    class SubWinState(BaseState):
    
        """ Common behaviour for sub windows"""
        
        def __init__(self, fsm):
            super().__init__(fsm)
            
        def __del__(self):
            super().__del__()

        def on_enter(self):
            super().on_enter()
            self._parent_window = self.get_current_window()
            (prows, pcols) = self._parent_window.getmaxyx()
            self._sub_windows = list()
            self._child_window = self.create_sub_windows(prows, pcols)
            self.set_current_window(self._child_window)

        def on_exit(self):
            for w in self._sub_windows:
                w.clear()
                w.noutrefresh()
                del w
            self._sub_windows.clear()
            del self._child_window
            self.set_current_window(self._parent_window)
            super().on_exit()
        
        def add_sub_window(self, window):
            self._sub_windows.append(window)
            
        def get_center_padded_string(width, string):
            center_padding_format = '{{0:{0}}}'.format('^{0:d}'.format(width))
            return center_padding_format.format(string)
            
        def get_left_padded_string(width, string):
            center_padding_format = '{{0:{0}}}'.format('<{0:d}'.format(width))
            return center_padding_format.format(string)
            
        def get_right_padded_string(width, string):
            center_padding_format = '{{0:{0}}}'.format('>{0:d}'.format(width))
            return center_padding_format.format(string)
            
        def draw_list_scroll(window, lst, selected_index, marked_element, height, width, highlight_attr, marker):
            (start_y, start_x) = window.getyx()
            central_row = int(height*0.5)
            for row in range(0, height):
                window.move(start_y+row, start_x)
                index = selected_index + row - central_row
                if index < 0 or index >= len(lst):
                    window.addstr(CursesWrapper.SubWinState.get_center_padded_string(width, '...'))
                else:
                    attr = curses.A_REVERSE if row == central_row else 0
                    string = lst[index]
                    if marked_element == lst[index]:
                        string = '{0} {1}'.format(marker, string)
                    window.addstr(CursesWrapper.SubWinState.get_center_padded_string(width, string), attr)
            window.move(start_y, start_x+width-1)
            CursesWrapper.SubWinState.draw_vertical_bar(window, height, float(selected_index)/len(lst), highlight_attr)
            
        def draw_horizontal_bar(window, length, percent, arrow_attr):
            window.addstr(LEFT_ARROW_CH, arrow_attr)
            slider_length = length - 3
            thumb_pos = round(slider_length*percent)
            if thumb_pos > 0: window.addstr(MEDIUM_SHADE_CH * thumb_pos)
            window.addstr(BLACK_DIAMOND_CH)
            if slider_length - thumb_pos > 0: window.addstr(MEDIUM_SHADE_CH * (slider_length-thumb_pos))
            window.addstr(RIGHT_ARROW_CH, arrow_attr)
        
        def draw_vertical_bar(window, length, percent, arrow_attr):
            (start_y, start_x) = window.getyx()
            window.addstr(UP_ARROW_CH, arrow_attr)
            slider_length = length - 2
            thumb_pos = round(slider_length*percent)
            for i in range(1, thumb_pos+1):
                window.move(start_y+i, start_x)
                window.addstr(MEDIUM_SHADE_CH)
            window.move(start_y+thumb_pos+1, start_x)
            window.addstr(BLACK_DIAMOND_CH)
            for i in range(thumb_pos+2, length-1):
                window.move(start_y+i, start_x)
                window.addstr(MEDIUM_SHADE_CH)
            window.move(start_y+length-1, start_x)
            window.addstr(DOWN_ARROW_CH, arrow_attr)
            
    class MainFrameState(SubWinState):

        """Common GUI elements and logic"""

        def __init__(self, fsm):
            super().__init__(fsm)
            
        def __del__(self):
            super().__del__()

        def on_enter(self):
            super().on_enter()
            self._alarm_fired = False
            self.set_fire_event_listener(self.on_alarm_fired)
            self._battery_update_timer = -BATTERY_UPDATE_TIME
            self.current_battery_charge = -1
            self.current_battery_status = System.BatteryState.unknown

        def on_exit(self):
            self.set_fire_event_listener(None)
            super().on_exit()

        def create_sub_windows(self, parent_rows, parent_cols):
            self._top_win = self._parent_window.derwin(3, parent_cols, 0, 0)
            self.add_sub_window(self._top_win)
            self._top_win.border()
            self._top_win.noutrefresh()
            self._bottom_win = self._parent_window.derwin(3, parent_cols, parent_rows-3, 0)
            self.add_sub_window(self._bottom_win)
            self._bottom_win.border()
            self._bottom_win.noutrefresh()
            return self._parent_window.derwin(parent_rows-6, parent_cols, 3, 0)
        
        def consume_input(self, ch):
            if ch in itertools.chain(CursesWrapper.KeyMappings.quit_app, CursesWrapper.KeyMappings.radio_tab, CursesWrapper.KeyMappings.alarm_tab):
                self._ch = ch
                return True
            return super().consume_input(ch)

        def draw(self):
            self._top_win.move(1,2)
            attr = curses.A_BOLD if self.top_state() == CursesWrapper.alarm_frame else curses.A_REVERSE if self.top_state() == CursesWrapper.radio_frame else 0
            self._top_win.addstr('R', attr)
            attr = curses.A_REVERSE if self.top_state() == CursesWrapper.radio_frame else 0
            self._top_win.addstr('adio', attr)
            self._top_win.addstr(' | ')
            #attr = curses.A_BOLD if self.top_state() == CursesWrapper.radio_frame else curses.A_REVERSE if self.top_state() == CursesWrapper.alarm_frame else 0
            #self._top_win.addstr('A', attr)
            #attr = curses.A_REVERSE if self.top_state() == CursesWrapper.alarm_frame else 0
            #self._top_win.addstr('larm', attr)
            #self._top_win.addstr(' | ')
            width = self._top_win.getmaxyx()[1]-20
            playing_string = ''
            if (self.is_radio_playing()):
                playing_string = 'Playing channel: {0}'.format(self.get_playing_channel())
            self._top_win.addstr(CursesWrapper.SubWinState.get_left_padded_string(width, playing_string))
            self._top_win.noutrefresh()
            
            self._bottom_win.move(1,1)
            self._bottom_win.addstr('{0:%H:%M:%S - %d %b %Y} | Alarm is {1}'.format(datetime.datetime.now(), 'On ' if self.is_alarm_on() else 'Off'))
            self._bottom_win.move(1, self._bottom_win.getmaxyx()[1]-18)
            self._bottom_win.addstr('| Battery ')
            attr = curses.A_REVERSE if self._current_battery_charge <= BATTERY_LOW_CHARGE else 0
            self._bottom_win.addstr('{0: 3d}%'.format(self._current_battery_charge), attr)
            self._bottom_win.addstr(' {0}'.format(UP_ARROW_CH if self._current_battery_status == System.BatteryState.charging else DOWN_ARROW_CH if self._current_battery_status == System.BatteryState.discharging else ' '))
            self._bottom_win.noutrefresh()
            
        def update(self):
            if time.clock() - self._battery_update_timer >= BATTERY_UPDATE_TIME:
                self._current_battery_charge = System.get_battery_charge()
                self._current_battery_status = System.get_battery_status()
                self._battery_update_timer = time.clock()
            if self._alarm_fired:
                self._alarm_fired = False
                self.save_preferences()
                return (CursesWrapper.Action.push_top, CursesWrapper.alarm_dialog)
            elif self._ch in CursesWrapper.KeyMappings.quit_app:
                return (CursesWrapper.Action.push_top, CursesWrapper.exit_dialog)
            elif self._ch in CursesWrapper.KeyMappings.radio_tab:
                if self.top_state() == CursesWrapper.alarm_frame:
                    return (CursesWrapper.Action.switch_top, CursesWrapper.radio_frame)
            elif self._ch in CursesWrapper.KeyMappings.alarm_tab:
                pass
                #if self.top_state() == CursesWrapper.radio_frame:
                    #return (CursesWrapper.Action.switch_top, CursesWrapper.alarm_frame)
            return super().update()
        
        def on_alarm_fired(self):
            self._alarm_fired = True
            
    class RadioFrameState(SubWinState):

        """GUI elements and logic for the radio"""

        def __init__(self, fsm):
            super().__init__(fsm)

        def __del__(self):
            super().__del__()

        def on_enter(self):
            super().on_enter()
            self._radio_channels = self.get_radio_channels()
            try:
                self._current_channel_index = self._radio_channels.index(self.get_current_channel())
            except ValueError:
                self._current_channel_index = 0
            
        def consume_input(self, ch):
            if ch in itertools.chain(CursesWrapper.KeyMappings.change_channel_up, CursesWrapper.KeyMappings.change_channel_down, CursesWrapper.KeyMappings.play_radio, CursesWrapper.KeyMappings.stop_radio , CursesWrapper.KeyMappings.increase_volume, CursesWrapper.KeyMappings.decrease_volume):
                self._ch = ch
                return True
            return super().consume_input(ch)
            
        def create_sub_windows(self, parent_rows, parent_cols):
            self._center_win = self._parent_window.derwin(parent_rows-3, parent_cols, 0, 0)
            self.add_sub_window(self._center_win)
            self._center_win.border()
            self._center_win.noutrefresh()
            self._bottom_win = self._parent_window.derwin(3, parent_cols, parent_rows-3, 0)
            self.add_sub_window(self._bottom_win)
            self._bottom_win.border()
            self._bottom_win.noutrefresh()
            return None
        
        def draw(self):
            bold_attr = curses.A_BOLD if self.top_state() == CursesWrapper.radio_frame else 0
            self._center_win.move(1, 1)
            CursesWrapper.SubWinState.draw_list_scroll(self._center_win, self._radio_channels, self._current_channel_index, self.get_playing_channel(), self._center_win.getmaxyx()[0]-2, self._center_win.getmaxyx()[1]-2, bold_attr, RIGHT_ARROW_CH)
            self._center_win.noutrefresh()
            
            if self.is_radio_playing():
                self._bottom_win.move(1, 2)
                self._bottom_win.addstr('S', bold_attr)
                self._bottom_win.addstr('top | ')
            else:
                self._bottom_win.move(1, 2)
                self._bottom_win.addstr('P', bold_attr)
                self._bottom_win.addstr('lay | ')
            self._bottom_win.addstr('Volume ')
            CursesWrapper.SubWinState.draw_horizontal_bar(self._bottom_win, self._bottom_win.getmaxyx()[1]-self._bottom_win.getyx()[1]-1, float(self.get_radio_volume())/self.get_radio_max_volume(), bold_attr)
            self._bottom_win.noutrefresh()
            
        def update(self):
            if self._ch in CursesWrapper.KeyMappings.change_channel_down:
                self._current_channel_index = min(self._current_channel_index+1, len(self._radio_channels)-1)
                self.set_current_channel(self._radio_channels[self._current_channel_index])
                self.save_preferences()
            elif self._ch in CursesWrapper.KeyMappings.change_channel_up:
                self._current_channel_index = max(self._current_channel_index-1, 0)
                self.set_current_channel(self._radio_channels[self._current_channel_index])
                self.save_preferences()
            elif self._ch in CursesWrapper.KeyMappings.stop_radio and self.is_radio_playing():
                self.stop_radio()
            elif self._ch in CursesWrapper.KeyMappings.play_radio and not self.is_radio_playing():
                self.play_radio()
            elif self._ch in CursesWrapper.KeyMappings.increase_volume:
                self.increase_radio_volume()
                self.save_preferences()
            elif self._ch in CursesWrapper.KeyMappings.decrease_volume:
                self.decrease_radio_volume()
                self.save_preferences()
            return super().update()

    class AlarmFrameState(SubWinState):

        """GUI elements and logic for the alarm"""

        def __init__(self, fsm):
            super().__init__(fsm)

        def __del__(self):
            super().__del__()

        def on_enter(self):
            super().on_enter()
            self._radio_channels = self.get_radio_channels()
            try:
                self._alarm_channel_index = self._radio_channels.index(self.get_alarm_channel())
            except ValueError:
                self._alarm_channel_index = 0
        
        def create_sub_windows(self, parent_rows, parent_cols):
            self._top_win = self._parent_window.derwin(3, parent_cols, 0, 0)
            self.add_sub_window(self._top_win)
            self._top_win.border()
            self._top_win.noutrefresh()
            self._center_win = self._parent_window.derwin(3, 0)
            self.add_sub_window(self._center_win)
            self._center_win.border()
            self._center_win.noutrefresh()
            return None
        
        def consume_input(self, ch):
            if ch in itertools.chain(CursesWrapper.KeyMappings.change_channel_up, CursesWrapper.KeyMappings.change_channel_down, CursesWrapper.KeyMappings.increase_volume, CursesWrapper.KeyMappings.decrease_volume, CursesWrapper.KeyMappings.enable_alarm, CursesWrapper.KeyMappings.disable_alarm, CursesWrapper.KeyMappings.set_alarm_time):
                self._ch = ch
                return True
            return super().consume_input(ch)

        def draw(self):
            alarm_time = self.get_alarm_time()
            bold_attr = curses.A_BOLD if self.top_state() == CursesWrapper.alarm_frame else 0
            self._top_win.move(1, 2)
            self._top_win.addstr('T', bold_attr)
            self._top_win.addstr('ime: {0:02d}:{1:02d} | '.format(alarm_time[0], alarm_time[1]))
            if self.is_alarm_on():
                self._top_win.addstr('D', bold_attr)
                self._top_win.addstr('isable | Volume ')
            else:
                self._top_win.addstr('E', bold_attr)
                self._top_win.addstr('nable  | Volume ')
            CursesWrapper.SubWinState.draw_horizontal_bar(self._top_win, self._top_win.getmaxyx()[1]-self._top_win.getyx()[1]-1, float(self.get_alarm_volume())/self.get_alarm_max_volume(), bold_attr)    
            self._top_win.noutrefresh()
            self._center_win.move(1, 1)
            CursesWrapper.SubWinState.draw_list_scroll(self._center_win, self._radio_channels, self._alarm_channel_index, self.get_alarm_channel(), self._center_win.getmaxyx()[0]-2, self._center_win.getmaxyx()[1]-2, bold_attr, BLACK_DIAMOND_CH if self.is_alarm_on() else "")
            self._center_win.noutrefresh()
            
        def update(self):
            if (self._ch in CursesWrapper.KeyMappings.enable_alarm and not self.is_alarm_on()) or (self._ch in CursesWrapper.KeyMappings.disable_alarm and self.is_alarm_on()):
                self.toggle_alarm()
                logging.debug('set alarm: {0}'.format('on' if self.is_alarm_on() else 'off'))
                self.save_preferences()
            elif self._ch in CursesWrapper.KeyMappings.change_channel_down:
                self._alarm_channel_index += 1
                if self._alarm_channel_index >= len(self._radio_channels):
                    self._alarm_channel_index = 0
                self.set_alarm_channel(self._radio_channels[self._alarm_channel_index])
                self.save_preferences()
            elif self._ch in CursesWrapper.KeyMappings.change_channel_up:
                self._alarm_channel_index -= 1
                if self._alarm_channel_index <= -1:
                    self._alarm_channel_index = len(self._radio_channels)-1
                self.set_alarm_channel(self._radio_channels[self._alarm_channel_index])
                self.save_preferences()
            elif self._ch in CursesWrapper.KeyMappings.increase_volume:
                self.increase_alarm_volume()
                self.save_preferences()
            elif self._ch in CursesWrapper.KeyMappings.decrease_volume:
                self.decrease_alarm_volume()
                self.save_preferences()
            elif self._ch in CursesWrapper.KeyMappings.set_alarm_time:
               return (CursesWrapper.Action.push_top, CursesWrapper.insert_alarm_time_dialog)
            return super().update()
    
    class DialogFrameState(BaseState):

        """ GUI elements and logic for an overlapping dialog"""

        def __init__(self, fsm):
            super().__init__(fsm)

        def on_enter(self):
            super().on_enter()
            self._background_window = self.get_current_window()
            self.set_current_window(None)
            self._dialog_window = self.create_dialog_window(self.get_screen_size())
            self._dialog_panel = curses.panel.new_panel(self._dialog_window)
            self._dialog_panel.top()
            curses.panel.update_panels()

        def on_exit(self):
            del self._dialog_panel
            curses.panel.update_panels()
            self._dialog_window.clear()
            self._dialog_window.noutrefresh()
            del self._dialog_window
            self.set_current_window(self._background_window)
            self._background_window = None
            super().on_exit()
            
        def consume_input(self, ch):
            self._ch = ch
            return True  # Dialogs always consume all input
        
        def get_dialog_window(self):
            return self._dialog_window

    class ExitDialogState(DialogFrameState):

        """ Confirm application exit """

        def __init__(self, fsm):
            super().__init__(fsm)
            
        def create_dialog_window(self, window_size):
            dialog_win = curses.newwin(5, 52, int((window_size[0]-4)/2), int((window_size[1]-51)/2))
            return dialog_win
            
        def draw(self):
            self.get_dialog_window().border()  # Need to redraw everything
            self.get_dialog_window().move(2, 2)
            self.get_dialog_window().addstr('Do you want to ')
            self.get_dialog_window().addstr('P', curses.A_BOLD)
            self.get_dialog_window().addstr('oweroff or ')
            self.get_dialog_window().addstr('Q', curses.A_BOLD)
            self.get_dialog_window().addstr('uit to the terminal?')
            self.get_dialog_window().noutrefresh()
            
        def update(self):
            if self._ch in CursesWrapper.KeyMappings.cancel_dialog:
                return (CursesWrapper.Action.pop_self, None)
            elif self._ch in CursesWrapper.KeyMappings.quit_to_terminal:
                return (CursesWrapper.Action.pop, self.bottom_state())
            elif self._ch in CursesWrapper.KeyMappings.poweroff:
                # TODO implement save restart!
                System.poweroff()
                #return (CursesWrapper.Action.pop, self.bottom_state())
            return super().update()

    class AlarmDialogState(DialogFrameState):

        """ Alarm triggered dialog """

        def __init__(self, fsm):
            super().__init__(fsm)
            
        def on_enter(self):
            super().on_enter()
            self._ringing_timeout = False
            self.set_ringing_timeout_event_listener(self.on_ringing_timeout)

        def on_exit(self):
            self.set_ringing_timeout_event_listener(None)
        
        def create_dialog_window(self, window_size):
            dialog_win = curses.newwin(7, 52, int((window_size[0]-6)/2), int((window_size[1]-51)/2))
            return dialog_win
        
        def draw(self):
            self.get_dialog_window().border()  # Need to redraw everything
            self.get_dialog_window().move(2, 2)
            self.get_dialog_window().addstr('Alarm will exit automatically in {0:^4d} seconds...'.format(round(self.get_ringing_countdown())))
            self.get_dialog_window().move(3, 2)
            self.get_dialog_window().addstr('Press ')
            if not self.next_snooze_quits():
                self.get_dialog_window().addstr('ESC', curses.A_BOLD)
                self.get_dialog_window().addstr(' to continue listening to the radio,')
                self.get_dialog_window().move(4, 2)
                self.get_dialog_window().addstr('any other key', curses.A_BOLD)
                self.get_dialog_window().addstr(' to snooze.')
            else:
                 self.get_dialog_window().addstr('any key to quit the alarm.')
            self.get_dialog_window().noutrefresh()
        
        def update(self):
            if self._ringing_timeout:
                self._ringing_timeout = False
                return (CursesWrapper.Action.pop_self, None)
            elif self._ch in CursesWrapper.KeyMappings.exit_alarm:
                self.exit_alarm()
                return (CursesWrapper.Action.pop_self, None)
            elif self._ch != -1:
                if self.snooze():
                    return (CursesWrapper.Action.switch_self, CursesWrapper.snooze_dialog)
                else:
                    return (CursesWrapper.Action.pop_self, None)
            return super().update()

        def on_ringing_timeout(self):
            self._ringing_timeout = True
    
    class SnoozeDialogState(DialogFrameState):
    
        """ Snooze dialog """
        
        def __init__(self, fsm):
            super().__init__(fsm)
            
        def on_enter(self):
            super().on_enter()
            self._snooze_timeout = False
            self.set_snooze_timeout_event_listener(self.on_snooze_timeout)

        def on_exit(self):
            self.set_snooze_timeout_event_listener(None)
        
        def create_dialog_window(self, window_size):
            dialog_win = curses.newwin(6, 53, int((window_size[0]-6)/2), int((window_size[1]-52)/2))
            return dialog_win
            
        def draw(self):
            self.get_dialog_window().border()  # Need to redraw everything
            self.get_dialog_window().move(2, 2)
            self.get_dialog_window().addstr('Snooze will exit automatically in {0:^4d} seconds...'.format(round(self.get_snooze_countdown())))
            self.get_dialog_window().move(3, 2)
            self.get_dialog_window().addstr('Press ')
            self.get_dialog_window().addstr('ESC', curses.A_BOLD)
            self.get_dialog_window().addstr(' to quit the alarm.')
            self.get_dialog_window().noutrefresh()
            
        def update(self):
            if self._snooze_timeout:
                self._snooze_timeout = False
                return (CursesWrapper.Action.switch_self, CursesWrapper.alarm_dialog)
            elif self._ch in CursesWrapper.KeyMappings.exit_alarm:
                self.exit_alarm()
                return (CursesWrapper.Action.pop_self, None)
            return super().update()

        def on_snooze_timeout(self):
            self._snooze_timeout = True
     
    class InsertAlarmTimeDialogState(DialogFrameState):

        """ Insert alarm time """

        def __init__(self, fsm):
            super().__init__(fsm)
            
        def on_enter(self):
            super().on_enter()
            self._user_input = CursesWrapper.InsertAlarmTimeDialogState.to_input_sequence(self.get_alarm_time())
            self._user_input_index = 0
            
        def create_dialog_window(self, window_size):
            dialog_win = curses.newwin(7, 34, int((window_size[0]-6)/2), int((window_size[1]-33)/2))
            return dialog_win
           
        def draw(self):
            self.get_dialog_window().border()  # Need to redraw everything
            self.get_dialog_window().move(3, 2)
            self.get_dialog_window().addstr('Insert new alarm time: ')
            self.get_dialog_window().addstr(LEFT_ARROW_CH, curses.A_BOLD)
            time_str = '{0}'.format(CursesWrapper.InsertAlarmTimeDialogState.to_string(self._user_input))
            dx = self._user_input_index if self._user_input_index < 2 else self._user_input_index+1
            cy, cx = self.get_dialog_window().getyx()
            for i in range(len(time_str)):
                if i == dx:
                    self.get_dialog_window().move(cy-1, cx+i)
                    self.get_dialog_window().addstr(UP_ARROW_CH, curses.A_BOLD)
                    self.get_dialog_window().move(cy, cx+i)
                    self.get_dialog_window().addstr(time_str[i], curses.A_REVERSE)
                    self.get_dialog_window().move(cy+1, cx+i)
                    self.get_dialog_window().addstr(DOWN_ARROW_CH, curses.A_BOLD)
                else:
                    self.get_dialog_window().move(cy-1, cx+i)
                    self.get_dialog_window().addstr(' ')
                    self.get_dialog_window().move(cy, cx+i)
                    self.get_dialog_window().addstr(time_str[i])
                    self.get_dialog_window().move(cy+1, cx+i)
                    self.get_dialog_window().addstr(' ')
            self.get_dialog_window().move(cy, cx+len(time_str))
            self.get_dialog_window().addstr(RIGHT_ARROW_CH, curses.A_BOLD)
            self.get_dialog_window().noutrefresh()
            
        def update(self):
            if self._ch in CursesWrapper.KeyMappings.enter_input:
                self.set_alarm_time(CursesWrapper.InsertAlarmTimeDialogState.to_time(self._user_input))
                self.save_preferences()
                return (CursesWrapper.Action.pop_self, None)
            elif self._ch in CursesWrapper.KeyMappings.cancel_input:
                return (CursesWrapper.Action.pop_self, None)
            elif self._ch in CursesWrapper.KeyMappings.increase_time:
                self.adjust_alarm(1)
            elif self._ch in CursesWrapper.KeyMappings.decrease_time:
                self.adjust_alarm(-1)
            elif self._ch in CursesWrapper.KeyMappings.next_digit:
                self.move_focus(1)
            elif self._ch in CursesWrapper.KeyMappings.previous_digit:
                self.move_focus(-1)
            return super().update()
        
        def adjust_alarm(self, incr):
            if self._user_input_index == 0:
                if self.get_digit(1) <= 3:
                    max_val = 2
                else:
                    max_val = 1
            elif self._user_input_index == 1:
                if self.get_digit(-1) <= 1:
                    max_val = 9
                else:
                    max_val = 3
            elif self._user_input_index == 2:
                max_val = 5
            else:
                max_val = 9
            d = self.get_digit(0)+incr
            if d < 0:
               d = max_val
            elif d > max_val:
               d = 0
            self.set_digit(0, d)
        
        def move_focus(self, delta):
            self._user_input_index = self._user_input_index+delta
            if self._user_input_index > 3:
                self._user_input_index = 0
            elif self._user_input_index < 0:
                self._user_input_index = 3
            
        def get_digit(self, delta):
            return int(self._user_input[self._user_input_index+delta])
        
        def set_digit(self, delta, val):
            self._user_input[self._user_input_index+delta] = '{0}'.format(val)[0]
            
        def to_input_sequence(time):
            h = '{0:02d}'.format(time[0])
            m = '{0:02d}'.format(time[1])
            return [h[0], h[1], m[0], m[1]]
            
        def to_string(user_input):
            return '{0}:{1}'.format(''.join(user_input[0:2]), ''.join(user_input[2:4]))
        
        def to_time(user_input):
            return [int(''.join(user_input[0:2])), int(''.join(user_input[2:4]))]
        
if __name__ == '__main__':
    try:
        logging.basicConfig(filename=LOGGING_FILE, filemode='w', format=LOGGING_FORMAT, level=LOGGING_LEVEL)
        curses_wrapper = CursesWrapper(Preferences(CursesWrapper.get_default_preferences(), PREFERENCES_FILE))
    except:
        traceback.print_exc()
    finally:
        logging.shutdown()
