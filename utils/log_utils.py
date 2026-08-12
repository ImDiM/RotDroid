import logging


def config_log(
        log_file: str,
        level: str = 'info',
        with_prefix: bool = True,
        clear: bool = True,
        encoding: str = 'utf-8'
    ):
    level = logging.DEBUG if level.lower() == 'debug' else logging.INFO

    if clear:
        with open(log_file, 'w', encoding=encoding):
            pass

    logger = logging.getLogger()

    while len(logger.handlers) > 0:
        logger.removeHandler(logger.handlers[0])

    logger.setLevel(level)
    file_handler = logging.FileHandler(log_file,encoding=encoding)

    console_handler = logging.StreamHandler()


    if with_prefix:
        formatter = logging.Formatter(
            fmt='''[%(asctime)s - %(levelname)s]: %(message)s''',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)    
    logger.addHandler(console_handler)
