import yaml
from types import SimpleNamespace

def dict_to_simplenamespace(dict_obj):
    """
    Converts a dictionary or a list of dictionaries to a SimpleNamespace object recursively.
    
    This function takes a dictionary or a list of dictionaries and converts them into a SimpleNamespace object,
    allowing attribute-style access to the dictionary keys. It does this recursively for nested dictionaries or lists.
    
    Args:
        dict_obj (dict or list): The dictionary or list of dictionaries to convert.
        
    Returns:
        SimpleNamespace or list: A SimpleNamespace object created from the dictionary, or a list of SimpleNamespace objects.
    """
    if isinstance(dict_obj, dict):
        for key, value in dict_obj.items():
            dict_obj[key] = dict_to_simplenamespace(value)
    elif isinstance(dict_obj, list):
        return [dict_to_simplenamespace(item) for item in dict_obj]
    return SimpleNamespace(**dict_obj) if isinstance(dict_obj, dict) else dict_obj

def load_config(config_path):
    """
    Loads a YAML configuration file and converts it to a SimpleNamespace object.
    
    This function reads a YAML file from the given path, parses it into a dictionary,
    and then converts that dictionary into a SimpleNamespace object for easier attribute-style access.
    
    Args:
        config_path (str): The file path of the YAML configuration file to load.
        
    Returns:
        SimpleNamespace: A SimpleNamespace object representing the loaded and converted configuration.
    """
    with open(config_path, "r") as file:
        config = yaml.safe_load(file)
    return dict_to_simplenamespace(config)

config = load_config("config.yaml")
