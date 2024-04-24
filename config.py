import logging
import coloredlogs
import yaml
import os
import argparse
from types import SimpleNamespace
import sys

# Temporary logging configuration
coloredlogs.install(level="WARN")

def dict_to_simplenamespace(dict_obj):
    """
    Recursively converts a nested dictionary into a SimpleNamespace object.

    Args:
        dict_obj (dict): The input dictionary to be converted.

    Returns:
        SimpleNamespace: The resulting SimpleNamespace object.
    """
    logging.info("Converting dictionary to SimpleNamespace")
    logging.debug(f"Input dictionary: {dict_obj}")
    if isinstance(dict_obj, dict):
        for key, value in dict_obj.items():
            logging.debug(f"Processing key: {key}")
            dict_obj[key] = dict_to_simplenamespace(value)
    elif isinstance(dict_obj, list):
        logging.debug(f"Processing list with {len(dict_obj)} items")
        return [dict_to_simplenamespace(item) for item in dict_obj]
    result = SimpleNamespace(**dict_obj) if isinstance(dict_obj, dict) else dict_obj
    logging.debug(f"Resulting SimpleNamespace or value: {result}")
    return result


def flatten_keys(d, parent_key='', sep='.'):
    """
    Flattens a nested dictionary into a flat dictionary with concatenated keys.

    Args:
        d (dict): The input nested dictionary to be flattened.
        parent_key (str): The parent key for the current level of recursion.
        sep (str): The separator used for concatenating keys.

    Returns:
        dict: The flattened dictionary.
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_keys(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def parse_args(config):
    """
    Parses command line arguments based on the configuration.

    Args:
        config (dict): The configuration dictionary.

    Returns:
        argparse.Namespace: The parsed command line arguments.
    """
    parser = argparse.ArgumentParser(
        description='Command Line Interface for the Application')
    parser.add_argument('-c', '--config', default=os.path.join(os.path.dirname(__file__), 'config.yaml'), type=str, help='Path to the config.yaml file')
    config_flat = flatten_keys(config)
    # Dynamically add arguments based on the config.yaml structure
    for key, value in config_flat.items():
        cli_key = key.replace('..', '.').lower()  # Ensure CLI arguments are lowercase
        parser.add_argument(f'--{cli_key}',
                            type=type(value),
                            default=value,
                            help=f'Specify the {cli_key} value')
    args, unknown = parser.parse_known_args()

    if unknown:
        logging.critical(f"Unknown arguments provided: {unknown}. Exiting program.")
        sys.exit(1)
    return args

def load_config():
    """
    Loads configuration settings from a YAML file and applies overrides.

    Returns:
        SimpleNamespace: The final configuration as a SimpleNamespace object.
    """
    logging.info("Loading configuration from file")
    with open('config.yaml', "r") as file:
        config = yaml.safe_load(file)
        logging.debug("Loaded initial configuration: %s", config)

    args = parse_args(config)

    if args.config:
        with open(args.config, "r") as file:
            config = yaml.safe_load(file)
            logging.info("Loaded configuration from file: %s", config)

    apply_overrides_from_env_and_cli(config, args)

    result = dict_to_simplenamespace(config)
    logging.debug("Final configuration as SimpleNamespace: %s", result)
    return result

def apply_overrides_from_env_and_cli(config, args):
    """
    Applies environment variables and command line arguments as overrides to the configuration.

    Args:
        config (dict): The configuration dictionary to be modified.
        args (argparse.Namespace): The parsed command line arguments.
    """
    env_vars = {k.upper(): v for k, v in os.environ.items()}
    for key, value in config.items():
        env_key = key.upper()
        if env_key in env_vars:
            config[key] = env_vars[env_key]
        arg_key = key.lower().replace('.', '__')  # Adapt for CLI argument format
        if hasattr(args, arg_key) and getattr(args, arg_key) is not None:
            config[key] = getattr(args, arg_key)

def init_loggers(config):
    """
    Initializes logging based on the configuration.

    Args:
        config (dict): The configuration dictionary.

    Returns:
        logging.Logger: The application logger instance.

    This function configures logging based on the provided configuration and returns the application logger instance.
    """
    # Configure logging based on configuration
    coloredlogs.install(level=config.logLevel.general)

    app_logger = logging.getLogger("application")
    app_logger.setLevel(config.logLevel.application)  # Application level specifically
    # Disable propagation of logging to other loggers
    app_logger.propagate = False

    # Handler for the application logger (if you want to also log to file or elsewhere)
    stream_handler = logging.StreamHandler()
    formatter = coloredlogs.ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler.setFormatter(formatter)

    app_logger.addHandler(stream_handler)

    return app_logger


config = load_config()
app_logger = init_loggers(config)
