"""
Utility functions for loading and accessing configuration information.
"""

import json
import os
from pathlib import Path

import jsonschema

DEFAULT_SCHEMA = os.path.join(os.path.dirname(__file__), "config_schema.json")


def get_configured_path(env_var: str, default_subdir: str) -> str:
    # Retrieve the value of the environment variable
    env_var_value = os.getenv(env_var)

    # If the environment variable does not exist,
    # construct a default path using the home directory, '.armory', and the provided default subdirectory
    if env_var_value is None:
        default_path = str(Path.home() / ".armory" / default_subdir)
        return default_path

    # If the environment variable exists, return its value
    return env_var_value


def get_verify_ssl():
    return os.getenv("VERIFY_SSL") == "true" or os.getenv("VERIFY_SSL") is None


def validate_config(config: dict, schema_path: str = DEFAULT_SCHEMA) -> dict:
    """
    Validates that a config matches the default JSON Schema
    """
    with open(schema_path, "r") as schema_file:
        schema = json.load(schema_file)

    jsonschema.validate(instance=config, schema=schema)

    return config


def load_config(filepath: str) -> dict:
    """
    Loads and validates a config file
    """
    with open(filepath) as f:
        config = json.load(f)

    return validate_config(config)
