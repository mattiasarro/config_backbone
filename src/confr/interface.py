import inspect

from confr import settings
from confr.utils import write_yaml, strip_keys
from confr.models import Conf, ModifiedConf, _plx_inputs, _get_cli_arg
from collections import namedtuple


global_conf = None # global config object which will hold an instance of Conf
Value = namedtuple("Value", ["key", "default"])


def get(k, default=None):
    return global_conf.get(k, default)


def set(k, v):
    return global_conf.set(k, v)


def get_input(k, default=None):
    cli_arg1 = _get_cli_arg(f"-{k}")
    cli_arg2 = _get_cli_arg(f"--{k}")
    plx_arg = _plx_inputs().get(k.replace(".", settings.PLX_DOT_REPLACEMENT))

    if cli_arg1 is not None:
        return cli_arg1
    elif cli_arg2 is not None:
        return cli_arg2
    elif plx_arg is not None:
        return plx_arg
    else:
        return default


def bind(*args, subkeys=None):
    def decorator(orig):
        if inspect.isfunction(orig):
            def confr_wrapped_function(*args, **kwargs):
                overrides = _get_call_overrides(orig, args, kwargs, subkeys)
                return orig(*args, **kwargs, **overrides)

            return confr_wrapped_function
        else:
            class ConfrWrappedClass(orig):
                def __init__(self, *args, **kwargs):
                    overrides = _get_call_overrides(orig, args, kwargs, subkeys)
                    super().__init__(*args, **kwargs, **overrides)

            return ConfrWrappedClass

    if len(args): # used as confr.bind; args = (orig), subkeys = None
        return decorator(args[0])
    else: # used as confr.bind(subkeys="asd"); args = (), subkeys = "asd"
        return decorator


def value(key=None, default=None):
    return Value(key, default)


def init(
    *args,
    validate=None,
    verbose=True,
    ctx=False, # if True, conf will be active only during the `with`` block
    **kwargs,
):

    global global_conf
    if global_conf is None and verbose:
        print("Declaring config.")
    else:
        if verbose:
            print("Redeclaring config.")

    conf = Conf(*args, **kwargs, verbose=verbose)

    if ctx:
        return ConfContext(global_conf, conf, validate)
    else:
        global_conf = conf
        validate_conf(validate)


def validate_conf(validable, verbose=True):
    if validable is None:
        return

    if inspect.ismodule(validable):
        for k, v in validable.__dict__.items():
            if callable(v):
                if verbose:
                    print(f"Validating {validable.__name__}.{k}.")
                v()
    elif type(validable) in [list, tuple]:
        for v in validable:
            validate_conf(v)
    elif callable(validable):
        if verbose:
            print(f"Validating {validable.__name__}.")
        validable()
    else:
        raise Exception(f"Unknown type {type(validable)} passed to validate_conf ({validable}).")


def modified_conf(**kwargs):
    return ModifiedConf(global_conf, **kwargs)


def write_conf(fp, except_keys=[]):
    ret = strip_keys(global_conf.to_dict(), except_keys=except_keys)
    write_yaml(fp, ret)
    print(f"Wrote configurations for: {list(ret.keys())}")


def to_dict(*limit_keys):
    ret = global_conf.to_dict()
    if limit_keys:
        return {k: ret[k] for k in limit_keys}
    else:
        return ret


def types():
    return global_conf.types


def conf_patches():
    return global_conf.conf_patches


def _get_call_overrides(cls_or_fn, args, kwargs, subkeys):
    try:
        bound_args = inspect.signature(cls_or_fn).bind(*args, **kwargs)
    except Exception as e:
        raise Exception(f"Unable to substitute values for {cls_or_fn.__name__}. {e}")
    bound_args.apply_defaults()
    default_args = dict(bound_args.arguments)

    assert global_conf is not None, "Need to initialize config before executing configurable functions."
    try:
        ret = {}
        for k, v in default_args.items():
            if callable(v) and v == value: # kwarg=confr.value
                get_key = f"{subkeys}.{k}" if subkeys else k
                get_default = None
            elif isinstance(v, Value): # kwarg=confr.value(...)
                if v.key is None: # kwarg=confr.value(default="default")
                    get_key = f"{subkeys}.{k}" if subkeys else k
                    get_default = v.default
                else: # kwarg=confr.value("key", default="default")
                    if v.key[0] == ".":
                        get_key = subkeys + v.key if subkeys else v.key # path is potentially relative to subkey
                    else:
                        get_key = v.key # path is absolute
                    get_default = v.default
            else: # non-configurable value, e.g. kwarg=123
                continue
            ret[k] = global_conf.get(get_key, get_default)
        return ret
    except:
        print(f"Trying to assign configurations to {cls_or_fn.__name__}")
        raise


class ConfContext:
    def __init__(self, old_conf, swapped_conf, validate):
        self.old_conf = old_conf
        self.swapped_conf = swapped_conf
        self.validate = validate

    def __enter__(self):
        global global_conf
        global_conf = self.swapped_conf
        validate_conf(self.validate)

    def __exit__(self, *args):
        global global_conf
        global_conf = self.old_conf
