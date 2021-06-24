import json
from pydantic import BaseSettings, ValidationError


def as_instance(cls):
    """Decorator making use-ready pydantic model from class upon declaring

    :param cls: Pydantic model class
    :return: Pydantic model instance filled with data from .env file
    """
    try:
        return cls()
    except ValidationError as e:

        def _format_env_exc(exc):
            errors = {}
            model: BaseSettings = exc.model
            fields = model.__fields__
            prefix = model.__config__.env_prefix
            for e in exc.errors():
                location = errors
                *path, cause = e.pop("loc")
                if cause in fields and fields[cause].has_alias:
                    field = fields[cause]
                    cause = field.alias
                else:
                    cause = prefix + cause.upper()
                for field in path:
                    location = location.setdefault(field, {})
                location[cause] = e["msg"]
            return json.dumps(errors, ensure_ascii=False, indent=4)

        raise RuntimeError(f"Invalid .env file: {_format_env_exc(e)}") from e
