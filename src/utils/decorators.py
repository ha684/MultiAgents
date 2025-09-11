def singleton(cls):
    """A decorator that makes a class a singleton."""
    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance


def singleton_per_key(key_func):
    instances = {}

    def decorator(cls):
        def get_instance(*args, **kwargs):
            key = key_func(*args, **kwargs)
            if key not in instances:
                instances[key] = cls(*args, **kwargs)
            return instances[key]

        return get_instance

    return decorator
