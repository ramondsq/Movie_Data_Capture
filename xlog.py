import os
import sys
import time
from datetime import datetime
import traceback
import threading
import json
import shutil

CRITICAL = 50
FATAL = CRITICAL
ERROR = 40
WARNING = 30
WARN = WARNING
INFO = 20
DEBUG = 10
NOTSET = 0


class Logger:
    def __init__(self, name, buffer_size=0, file_name=None, roll_num=1):
        self.err_color = '\033[0m'
        self.warn_color = '\033[0m'
        self.debug_color = '\033[0m'
        self.reset_color = '\033[0m'
        self.set_console_color = lambda color: sys.stderr.write(color)
        self.name = str(name)
        self.file_max_size = 1024 * 1024
        self.buffer_lock = threading.Lock()
        self.buffer = {}  # id => line
        self.buffer_size = buffer_size
        self.last_no = 0
        self.min_level = NOTSET
        self.log_fd = None
        self.roll_num = roll_num
        if file_name:
            self.set_file(file_name)

    def set_buffer(self, buffer_size):
        with self.buffer_lock:
            self.buffer_size = buffer_size
            buffer_len = len(self.buffer)
            if buffer_len > self.buffer_size:
                for i in range(self.last_no - buffer_len, self.last_no - self.buffer_size):
                    try:
                        del self.buffer[i]
                    except Exception:
                        pass

    def setLevel(self, level):
        if level == "DEBUG":
            self.min_level = DEBUG
        elif level == "INFO":
            self.min_level = INFO
        elif level == "WARN":
            self.min_level = WARN
        elif level == "ERROR":
            self.min_level = ERROR
        elif level == "FATAL":
            self.min_level = FATAL
        else:
            print(("log level not support:%s", level))

    def set_color(self):
        self.err_color = None
        self.warn_color = None
        self.debug_color = None
        self.reset_color = None
        self.set_console_color = lambda x: None
        if hasattr(sys.stderr, 'isatty') and sys.stderr.isatty():
            if os.name == 'nt':
                self.err_color = 0x04
                self.warn_color = 0x06
                self.debug_color = 0x002
                self.reset_color = 0x07

                import ctypes
                SetConsoleTextAttribute = ctypes.windll.kernel32.SetConsoleTextAttribute
                GetStdHandle = ctypes.windll.kernel32.GetStdHandle
                self.set_console_color = lambda color: SetConsoleTextAttribute(GetStdHandle(-11), color)

            elif os.name == 'posix':
                self.err_color = '\033[31m'
                self.warn_color = '\033[33m'
                self.debug_color = '\033[32m'
                self.reset_color = '\033[0m'

                self.set_console_color = lambda color: sys.stderr.write(color)

    def set_file(self, file_name):
        self.log_filename = file_name
        if os.path.isfile(file_name):
            self.file_size = os.path.getsize(file_name)
            if self.file_size > self.file_max_size:
                self.roll_log()
                self.file_size = 0
        else:
            self.file_size = 0

        self.log_fd = open(file_name, "a+")

    def roll_log(self):
        for i in range(self.roll_num, 1, -1):
            new_name = "%s.%d" % (self.log_filename, i)
            old_name = "%s.%d" % (self.log_filename, i - 1)
            if not os.path.isfile(old_name):
                continue

            # self.info("roll_log %s -> %s", old_name, new_name)
            shutil.move(old_name, new_name)

        shutil.move(self.log_filename, self.log_filename + ".1")

    def log_console(self, level, console_color, fmt, *args, **kwargs):
        try:
            console_string = '[%s] %s\n' % (level, fmt % args)
            self.set_console_color(console_color)
            sys.stderr.write(console_string)
            self.set_console_color(self.reset_color)
        except Exception:
            pass

    def log_to_file(self, level, console_color, fmt, *args, **kwargs):
        if self.log_fd:
            if level == 'e':
                string = '%s' % (fmt % args)
            else:
                time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:23]
                string = '%s [%s] [%s] %s\n' % (time_str, self.name, level, fmt % args)

            self.log_fd.write(string)
            try:
                self.log_fd.flush()
            except Exception:
                pass

            self.file_size += len(string)
            if self.file_size > self.file_max_size:
                self.log_fd.close()
                self.log_fd = None
                self.roll_log()
                self.log_fd = open(self.log_filename, "w")
                self.file_size = 0

    def log(self, level, console_color, html_color, fmt, *args, **kwargs):
        self.buffer_lock.acquire()
        try:
            self.log_console(level, console_color, fmt, *args, **kwargs)

            self.log_to_file(level, console_color, fmt, *args, **kwargs)

            if self.buffer_size:
                self.last_no += 1
                string = '%s [%s]LOG: %s' % (time.ctime()[4:-5], level, fmt % args)
                self.buffer[self.last_no] = string
                buffer_len = len(self.buffer)
                if buffer_len > self.buffer_size:
                    del self.buffer[self.last_no - self.buffer_size]
        except Exception as e:
            string = '%s - [%s]LOG_EXCEPT: %s, Except:%s<br> %s' % (
            time.ctime()[4:-5], level, fmt % args, e, traceback.format_exc())
            self.last_no += 1
            self.buffer[self.last_no] = string
            buffer_len = len(self.buffer)
            if buffer_len > self.buffer_size:
                del self.buffer[self.last_no - self.buffer_size]
        finally:
            self.buffer_lock.release()

    def debug(self, fmt, *args, **kwargs):
        if self.min_level > DEBUG:
            return
        self.log('-', self.debug_color, '21610b', fmt, *args, **kwargs)

    def info(self, fmt, *args, **kwargs):
        if self.min_level > INFO:
            return
        self.log('+', self.reset_color, '000000', fmt, *args)

    def warning(self, fmt, *args, **kwargs):
        if self.min_level > WARN:
            return
        self.log('#', self.warn_color, 'FF8000', fmt, *args, **kwargs)

    def warn(self, fmt, *args, **kwargs):
        self.warning(fmt, *args, **kwargs)

    def error(self, fmt, *args, **kwargs):
        if self.min_level > ERROR:
            return
        self.log('!', self.err_color, 'FE2E2E', fmt, *args, **kwargs)

    def exception(self, fmt, *args, **kwargs):
        self.error(fmt, *args, **kwargs)
        string = '%s' % (traceback.format_exc())
        self.log_to_file('e', self.err_color, string)

    def critical(self, fmt, *args, **kwargs):
        if self.min_level > CRITICAL:
            return
        self.log('!', self.err_color, 'D7DF01', fmt, *args, **kwargs)

    def tofile(self, fmt, *args, **kwargs):
        self.log_to_file('@', self.warn_color, fmt, *args, **kwargs)

    # =================================================================
    def set_buffer_size(self, set_size):
        self.buffer_lock.acquire()
        self.buffer_size = set_size
        buffer_len = len(self.buffer)
        if buffer_len > self.buffer_size:
            for i in range(self.last_no - buffer_len, self.last_no - self.buffer_size):
                try:
                    del self.buffer[i]
                except Exception:
                    pass
        self.buffer_lock.release()

    def get_last_lines(self, max_lines):
        self.buffer_lock.acquire()
        buffer_len = len(self.buffer)
        if buffer_len > max_lines:
            first_no = self.last_no - max_lines
        else:
            first_no = self.last_no - buffer_len + 1

        jd = {}
        if buffer_len > 0:
            for i in range(first_no, self.last_no + 1):
                jd[i] = self.unicode_line(self.buffer[i])
        self.buffer_lock.release()
        return json.dumps(jd)

    def get_new_lines(self, from_no):
        self.buffer_lock.acquire()
        jd = {}
        first_no = self.last_no - len(self.buffer) + 1
        if from_no < first_no:
            from_no = first_no

        if self.last_no >= from_no:
            for i in range(from_no, self.last_no + 1):
                jd[i] = self.unicode_line(self.buffer[i])
        self.buffer_lock.release()
        return json.dumps(jd)

    def unicode_line(self, line):
        try:
            if type(line) is str:
                return line
            else:
                return str(line, errors='ignore')
        except Exception as e:
            print(("unicode err:%r" % e))
            print(("line can't decode:%s" % line))
            print(("Except stack:%s" % traceback.format_exc()))
            return ""


loggerDict = {}


def getLogger(name=None, buffer_size=0, file_name=None, roll_num=1):
    global loggerDict, default_log
    if name is None:
        for n in loggerDict:
            name = n
            break
    if name is None:
        name = u"default"

    if not isinstance(name, str):
        raise TypeError('A logger name must be string or Unicode')
    if isinstance(name, bytes):
        name = name.encode('utf-8')

    if name in loggerDict:
        return loggerDict[name]
    else:
        logger_instance = Logger(name, buffer_size, file_name, roll_num)
        loggerDict[name] = logger_instance
        default_log = logger_instance
        return logger_instance


default_log = getLogger()


def debg(fmt, *args, **kwargs):
    default_log.debug(fmt, *args, **kwargs)


def info(fmt, *args, **kwargs):
    default_log.info(fmt, *args, **kwargs)


def warn(fmt, *args, **kwargs):
    default_log.warning(fmt, *args, **kwargs)


def erro(fmt, *args, **kwargs):
    default_log.error(fmt, *args, **kwargs)


def excp(fmt, *args, **kwargs):
    default_log.exception(fmt, *args, **kwargs)


def crit(fmt, *args, **kwargs):
    default_log.critical(fmt, *args, **kwargs)


def tofile(fmt, *args, **kwargs):
    default_log.tofile(fmt, *args, **kwargs)


if __name__ == '__main__':
    log_file = os.path.join(os.path.dirname(sys.argv[0]), "test.log")
    getLogger().set_file(log_file)
    debg("debug")
    info("info")
    warn("warning")
    erro("error")
    crit("critical")
    tofile("write to file only")

    try:
        1 / 0
    except Exception:
        excp("An error has occurred")
