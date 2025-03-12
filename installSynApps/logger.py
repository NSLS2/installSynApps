"""Module containing logging classes and functions.

The logger is controlled via a set of global variables set by the installSynApps client.

The most important thing for the client to do is to run assign_write_function, and give the logger a 
function that takes a single string input parameter. This can be print or writing to a GUI display etc.
"""

import os
from datetime import datetime


# Global variable storing function for logging. Function must accept a single string parameter
_WRITE_FUNCTION = None

# Global variable representing the log file for the current run of installSynApps
_LOG_FILE = None
_LOG_FILE_PATH = f"installSynApps_{datetime.now().strftime('%m-%d-%Y_%H-%M-%S')}.log"

# Global variable representing whether or not to print commands being run by installSynApps
_PRINT_COMMANDS = False

# Global variable to determine whether or not to print debug messages
_DEBUG = False

# Global variable to determine whether or not 
_WITH_NEW_LINES = True


def initialize_logger():
    """Function for initializing log-file writing in addition to stdout output
    """

    global _LOG_FILE
    try:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        _LOG_FILE = open(os.path.join('logs', _LOG_FILE_PATH), 'w')
    except OSError:
        write('Failed to initialize log file...')


def close_logger():
    """Function that closes the opened logfile
    """

    global _LOG_FILE
    if _LOG_FILE is not None:
        _LOG_FILE.close()


def toggle_command_printing():
    """Function that toggles printing bash/batch commands
    """

    global _PRINT_COMMANDS
    _PRINT_COMMANDS = not _PRINT_COMMANDS


def toggle_debug_logging():
    """Function that toggles printing additional debug messages
    """

    global _DEBUG
    _DEBUG = not _DEBUG


def toggle_with_new_lines():
    """Function that toggles printing with/without newlines
    """

    global _WITH_NEW_LINES
    _WITH_NEW_LINES = not _WITH_NEW_LINES


def assign_write_function(write_function):
    """Function that assigns a default write function for the logger

    Parameters
    ----------
    write_function : function(str)
        A function that takes a single string parameter. Ex. print()
    """

    global _WRITE_FUNCTION
    _WRITE_FUNCTION = write_function


def debug(text, force_no_timestamp=False):
    """Function used for writing debug messages. 

    By default debug messages will have a timestamp, unless force_no_timestamp flag is set

    Parameters
    ----------
    text : str
        debug text to print
    force_no_timestamp=False : bool
        a flag to disable timestamp printing when required
    """

    global _DEBUG
    if _DEBUG:
        write(text, no_timestamp=force_no_timestamp)


def print_command(command: list[str]):
    """Function for printing bash/batch commands

    Parameters
    ----------
    command : list[str]
        command to print
    """

    global _PRINT_COMMANDS
    if _PRINT_COMMANDS:
        write(" ".join(command), no_timestamp=True)


def write(text, no_timestamp=True):
    """Main logging funcion. Called if write function was set
    
    Parameters
    ----------
    text : str
        debug text to print
    no_timestamp=False : bool
        a flag to disable timestamp printing when required
    """

    global _DEBUG
    global _WRITE_FUNCTION
    global _WITH_NEW_LINES

    # remove timestamp if not in use
    if not _DEBUG or no_timestamp:
        final_text = '{}\n'.format(text)
    else:
        # otherwise add timestamp
        final_text = '{} - {}\n'.format(datetime.now(), text)

    # If we are also writing to logfile do that here
    log_write(final_text)

    # Remove newlines (if requested)
    if not _WITH_NEW_LINES:
        final_text = final_text.strip()

    # Pass text to writefunction
    if _WRITE_FUNCTION is not None:
        _WRITE_FUNCTION(final_text)


def log_write(text):
    """Function that writes text to a file

    Parameters
    ----------
    text : str
        debug text to print
    """

    global _LOG_FILE
    if _LOG_FILE is not None:
        _LOG_FILE.write(text)
