import logging
import coloredlogs
import yaml
import os
import argparse
import sys
from typing import NamedTuple, Dict, Any
from types import SimpleNamespace

# Temporary logging configuration
coloredlogs.install(level="WARN")

class TLSCertificateConfig(NamedTuple):
    """A path to a certificate required by TLS."""
    file: str

class DockerTLSConfig(NamedTuple):
    """The container representing the TLS config information needed by Docker"""
    verify: TLSCertificateConfig
    cert: TLSCertificateConfig
    key: TLSCertificateConfig
    enabled: bool

class DockerConfig(NamedTuple):
    """
    Configuration for Docker.

    Attributes:
        host (str): The Docker host URL.
        tls (DockerTLSConfig): The container that holds the Docker host URL and TLS configurations that go with it
    """
    host: str
    tls: DockerTLSConfig

class LogLevelConfig(NamedTuple):
    """
    Configuration for logging levels.

    Attributes:
        general (str): The general logging level.
        application (str): The application-specific logging level.
    """
    general: str
    application: str

class TraefikConfig(NamedTuple):
    """
    Configuration for Traefik.

    Attributes:
        containerName (str): The name of the Traefik container.
        monitoredLabel (str): The label used to identify monitored services.
        networkLabel (str): The label used to identify the network.
    """
    containerName: str
    monitoredLabel: str
    networkLabel: str

class Config(NamedTuple):
    """
    The main configuration class.

    Attributes:
        docker (DockerConfig): The Docker configuration.
        logLevel (LogLevelConfig): The logging level configuration.
        traefik (TraefikConfig): The Traefik configuration.
    """
    docker: DockerConfig
    logLevel: LogLevelConfig
    traefik: TraefikConfig

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
                            help=f'Specify the {cli_key} value')
    args, unknown = parser.parse_known_args()

    if unknown:
        logging.critical(f"Unknown arguments provided: {unknown}. Exiting program.")
        sys.exit(1)
    return args

def load_config() -> Config:
    """
    Loads configuration settings from a YAML file and applies overrides.

    Returns:
        Config: The final configuration as a Config object.
    """
    logging.info("Loading configuration from file")
    with open('config.yaml', "r") as file:
        config_data = yaml.safe_load(file)
        logging.debug("Loaded initial configuration: %s", config_data)

    args = parse_args(config_data)

    if args.config:
        with open(args.config, "r") as file:
            config_data = yaml.safe_load(file)
            logging.info("Loaded configuration from file: %s", config_data)

    apply_overrides_from_env_and_cli(config_data, args)

    tls_cert_verify: TLSCertificateConfig = TLSCertificateConfig(
        file=config_data["docker"]["tls"]["verify"])
    tls_cert_container_cert: TLSCertificateConfig = TLSCertificateConfig(
        file=config_data["docker"]["tls"]["cert"])
    tls_cert_container_key: TLSCertificateConfig = TLSCertificateConfig(
        file=config_data["docker"]["tls"]["key"])

    docker_tls: DockerTLSConfig = DockerTLSConfig(
        enabled=config_data["docker"]["tls"]["enabled"],
        verify=tls_cert_verify,
        cert=tls_cert_container_cert,
        key=tls_cert_container_key)

    # Traefik has it's own parameter for network, so we have to use it !
    if 'networkLabel' not in config_data['traefik']:
        config_data['traefik']['networkLabel'] = 'traefik.docker.network'

    docker: DockerConfig = DockerConfig(host=config_data["docker"]["host"], tls=docker_tls)

    log_level: LogLevelConfig = LogLevelConfig(
        general=config_data["logLevel"]["general"],
        application=config_data["logLevel"]["application"])

    traefik: TraefikConfig = TraefikConfig(
        containerName=config_data["traefik"]["containerName"],
        monitoredLabel=config_data["traefik"]["monitoredLabel"],
        networkLabel=config_data["traefik"]["networkLabel"])

    config: Config = Config(docker=docker, logLevel=log_level, traefik=traefik)

    logging.debug("Final configuration as Config: %s", config)
    return config

def apply_overrides_from_env_and_cli(config, args):
    """
    Applies environment variables and command line arguments as overrides to the configuration.

    Args:
        config (dict): The configuration dictionary to be modified.
        args (argparse.Namespace): The parsed command line arguments.
    """
    def apply_overrides(config, prefix=''):
        env_vars = {k.upper(): v for k, v in os.environ.items()}
        cli_args = vars(args)  # Convert Namespace to dict for easier access
        for key, value in config.items():
            full_key = f"{prefix}{key}".upper()
            env_key = full_key.replace('.', '_')
            arg_key = full_key.lower()
            if isinstance(value, dict):
                apply_overrides(value, prefix=f"{full_key}.")
            else:
                if env_key in env_vars:
                    config[key] = type(value)(env_vars[env_key])  # Convert env var to correct type
                if arg_key in cli_args and cli_args[arg_key] is not None:
                    config[key] = cli_args[arg_key]  # Directly use the value from CLI args

    apply_overrides(config)

def init_loggers(config: Config) -> logging.Logger:
    """
    Initializes logging based on the configuration.

    Args:
        config (Config): The configuration dictionary.

    Returns:
        logging.Logger: The application logger instance.
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

# Load configuration and initialize logger
config: Config = load_config()

app_logger = init_loggers(config)
