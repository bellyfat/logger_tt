import sys
import logging
import json
from pathlib import Path
from logging.config import dictConfig
from dataclasses import dataclass
from functools import partial
from .capture import PrintCapture
from .inspector import analyze_frame


__author__ = "Duc Tin"
__all__ = ['setup_logging']


"""Config log from file and make it also logs uncaught exception"""


@dataclass()
class LogConfig:
    full_context:bool = False


internal_config = LogConfig()


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    full_context = internal_config.full_context

    # Root logger with log all other uncaught exceptions
    txt = analyze_frame(exc_traceback, full_context)
    logging.error(f"Uncaught exception:\n"
                  f"Traceback (most recent call last):\n"
                  f"{txt}",
                  exc_info=(exc_type, exc_value, None))

    # As interpreter is going to shutdown after this function,
    # objects are getting deleted.
    # Disable further logging to prevent NameError exception
    logging.disable(logging.CRITICAL)


def ensure_path(config: dict, override_log_path: str = ""):
    """ensure log path exists"""
    for handler in config['handlers'].values():
        filename = handler.get('filename')
        if not filename:
            continue
        filename = override_log_path or filename
        handler['filename'] = filename
        log_path = Path(filename).parent
        log_path.mkdir(parents=True, exist_ok=True)


def load_from_file(f: Path) -> dict:
    if f.suffix == '.yaml':
        import yaml     # will raise error if pyyaml is not installed
        return yaml.safe_load(f.read_text())
    else:
        with f.open() as fp:
            return json.load(fp)


def suppress_logger(loggers, suppress_level_below):
    if not loggers:
        return

    for name in loggers:
        logger = logging.getLogger(name)
        logger.level = suppress_level_below


def setup_logging(config_path="", log_path="",
                  capture_print=False, strict=False, guess_level=False,
                  full_context=False,
                  suppress_level_below=logging.WARNING):
    """Setup logging configuration
        :param config_path: Path to log config file. Use default config if this is not provided
        :param log_path: Path to store log file. Override 'filename' field of 'handlers' in
            default config.
        :param capture_print: Log message that is printed out with print() function
        :param strict: only used when capture_print is True. If strict is True, then log
            everything that use sys.stdout.write().
        :param guess_level: auto guess logging level of captured message
        :param full_context: whether to log full local scope on exception or not
        :param suppress_level_below: For logger in the suppress list, any message below this level
            is not processed, not printed out nor logged to file
    """
    if config_path:
        path = Path(config_path)
        assert path.is_file(), 'Input config path is not a file!'
        assert path.suffix in ['.yaml', '.json'], 'Config file type must be either yaml or json!'
        assert path.exists(), f'Config file path not exists! {path.absolute()}'
    else:
        path = Path(__file__).parent / 'log_config.json'

    # load config from file
    config = load_from_file(path)
    ensure_path(config, log_path)
    suppress_logger(config.pop('suppress', None), suppress_level_below)
    logging.config.dictConfig(config)

    # set internal config
    internal_config.full_context = full_context

    # capture other messages
    sys.excepthook = partial(handle_exception)
    if capture_print:
        sys.stdout = PrintCapture(sys.stdout, strict=strict, guess_level=guess_level)
    logging.debug('New log started'.center(50, '_'))


class ExceptionLogger(logging.Logger):
    """Modify the `exception` func so that it print out context too
        This allow user do a try-except in outer code but still has the full log
        of nested code's error
        Example:
            try:
                a, b = 1, 0
            except Exception as e:
                logger.exception(e)
            # then move on
    """
    def exception(self, msg, *args, exc_info=True, **kwargs):
        if exc_info:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            full_context = internal_config.full_context
            txt = analyze_frame(exc_traceback, full_context)
            logging.error(f'{msg}\n'
                          f"Traceback (most recent call last):\n"
                          f"{txt}",
                          exc_info=(exc_type, exc_value, None))
        else:
            logging.error(msg, *args, exc_info=exc_info, **kwargs)


logging.setLoggerClass(ExceptionLogger)
