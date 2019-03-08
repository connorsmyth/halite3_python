# Placed here to avoid circular imports
import debug_common

def read_input():
    """
    Reads input from stdin, shutting down logging and exiting if an EOFError occurs
    :return: input read
    """
    if debug_common.debug_mode == True:
        return __get_line()
    else:
        try:
            return input()
        except EOFError as eof:
            logging.shutdown()
            raise SystemExit(eof)

def __get_line():
    next_line = debug_common.input_arr[0]
    debug_common.input_arr = debug_common.input_arr[1:]
    return next_line