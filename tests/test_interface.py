# %%
import os
from copy import deepcopy
from tempfile import NamedTemporaryFile, TemporaryDirectory

import confr
from confr.utils import read_yaml, write_yaml
from confr.test import validations


# mock functions #


@confr.bind
def fn1(key1=confr.value):
    return key1


@confr.bind(subkeys="nested")
def fn1_subkeys(key1=confr.value):
    return key1


@confr.bind
def fn_custom_key(key1=confr.value("key2")):
    return key1


@confr.bind
def fn_custom_key_deep(key1=confr.value("k1.k2.k3")):
    return key1


@confr.bind
def fn_default(key1=confr.value(default="default")):
    return key1


@confr.bind
def fn_custom_key_and_default(key1=confr.value("key2", default="default")):
    return key1


@confr.bind
def fn_python_reference(preprocessing_fn=confr.value):
    return preprocessing_fn()


@confr.bind
def get_model1(encoder=confr.value):
    return encoder


@confr.bind
def get_model2(model=confr.value("encoder")):
    return model


@confr.bind
def get_sth(sth=confr.value):
    return sth


@confr.bind
class MyClass:
    def __init__(self, key1=confr.value):
        self.key1 = key1

    @confr.bind
    def my_method1(self, key1=None, key2=confr.value):
        return self.key1, key1, key2

    # notice this method is not annotated with @confr.bind
    def my_method2(self, key1=None, key2=confr.value):
        return self.key1, key1, key2


# tests #


def test_conf_get_set():
    confr.init(conf={"key1": "val1"}, cli_overrides=False)
    assert confr.get("key1") == fn1() == "val1", (fn1(), type(fn1()))

    confr.set("key1", "val2")
    assert confr.get("key1") == fn1() == "val2"


def test_bind_fn():
    confr.init(conf={"key1": "val1"}, cli_overrides=False)
    assert fn1() == "val1"
    assert fn1(key1="val2") == "val2"


def test_bind_class():
    confr.init(conf={"key1": "val1", "key2": "val2"}, cli_overrides=False)

    o = MyClass(key1="val1")
    assert o.key1 == "val1"
    assert o.my_method1() == ("val1", None, "val2")
    assert o.my_method2() == ("val1", None, confr.value)

    assert o.my_method1(key1="a") == ("val1", "a", "val2")
    assert o.my_method2(key1="a") == ("val1", "a", confr.value)
    assert o.my_method1(key1="a", key2="b") == ("val1", "a", "b")
    assert o.my_method2(key1="a", key2="b") == ("val1", "a", "b")


def test_bind_fn_subkeys():
    confr.init(conf={"key1": "val1", "nested": {"key1": "nested1"}}, cli_overrides=False)

    assert fn1() == "val1"
    assert fn1(key1="val2") == "val2"

    assert fn1_subkeys() == "nested1"
    assert fn1_subkeys(key1="val2") == "val2"


def test_value_custom_key():
    confr.init(conf={"key1": "val1", "key2": "val2"}, cli_overrides=False)
    assert fn_custom_key() == "val2"
    assert fn_custom_key(key1="val3") == "val3"


def test_value_custom_key_deep():
    confr.init(conf={"key1": "val1", "key2": "val2", "k1": {"k2": {"k3": "v3"}}}, cli_overrides=False)
    assert fn_custom_key_deep() == "v3"
    assert fn_custom_key_deep(key1="val3") == "val3"


def test_value_default():
    confr.init(conf={"other_key": "other_val"}, cli_overrides=False) # ensure we init from dict, rather than dir
    assert fn_default() == "default"

    confr.init(conf={"key1": "val1"}, cli_overrides=False)
    assert fn_default() == "val1"


def test_value_custom_key_and_default():
    confr.init(conf={"key1": "val1", "key2": "val2"}, cli_overrides=False)
    assert fn_custom_key_and_default() == "val2"
    assert fn_custom_key_and_default(key1="val3") == "val3"

    confr.init(conf={"other_key": "other_val"}, cli_overrides=False) # ensure we init from dict, rather than dir
    assert fn_custom_key_and_default() == "default"

    confr.init(conf={"key2": "val2"}, cli_overrides=False)
    assert fn_custom_key_and_default() == "val2"


def test_python_reference():
    confr.init(conf={"preprocessing_fn": "@confr.test.imports.my_fn"}, cli_overrides=False)
    assert fn_python_reference() == 123


def test_singleton():
    conf = {
        "encoder": "@confr.test.imports.get_encoder()",
        "encoder/num": 4,
        "num": 3,
    }
    confr.init(conf=conf, cli_overrides=False)

    my_model1 = get_model1()
    my_model2 = get_model1()
    assert my_model1 == my_model2
    assert my_model1.num == my_model2.num == 4


def test_interpolation():
    conf = {
        "k1": "v1",
        "k2": {"k21": "v21", "k22": "${k1}"},
    }
    confr.init(conf=conf, cli_overrides=False)

    assert confr.get("k1") == "v1"
    assert confr.get("k2") == {"k21": "v21", "k22": "v1"}
    assert confr.get("k2.k21") == "v21"
    assert confr.get("k2.k22") == "v1"


def test_interpolation_singleton():
    conf = {
        "encoder": "@confr.test.imports.get_encoder()",
        "encoder/num": 4,
        "num": 3,
        "k1": {"k2": "${encoder}"},
        "my": {
            "encoder": "@confr.test.imports.get_encoder()",
            "encoder/num": 5,
        },
    }
    confr.init(conf=conf, cli_overrides=False)

    my_model1 = get_model1()
    my_model2 = get_model2()
    encoder = confr.get("encoder")
    k1_k2 = confr.get("k1.k2")
    my_encoder = confr.get("my.encoder")

    assert my_encoder.num == 5
    assert my_model1.num == my_model2.num == encoder.num == k1_k2.num == 4
    assert my_model1 == my_model2 == encoder == k1_k2
    assert my_encoder != my_model1 and my_encoder != my_model2 and my_encoder != k1_k2


def test_modified_conf():
    conf = {
        "key1": "val1",
        "encoder": "@confr.test.imports.get_encoder()",
        "encoder/num": 3,
    }
    confr.init(conf=conf, cli_overrides=False)
    assert fn1() == "val1"
    with confr.modified_conf(key1="val2", sth="${encoder}"):
        assert fn1() == "val2"
        assert confr.get("sth").num == 3
    assert fn1() == "val1"


def test_conf_from_files():
    with NamedTemporaryFile() as f:
        f.write("key1: val1".encode("utf-8"))
        f.flush()

        confr.init(conf_files=[f.name], cli_overrides=False)
        assert fn1() == "val1"


def test_conf_from_dir():
    with TemporaryDirectory() as conf_dir:
        conf1_fp = os.path.join(conf_dir, "conf1.yaml")
        conf2_fp = os.path.join(conf_dir, "conf2.yaml")
        write_yaml(conf1_fp, {"key1": "val1"})
        write_yaml(conf2_fp, {"key1": "val2"})

        confr.init(
            conf_dir=conf_dir,
            base_conf="conf1",
            cli_overrides=False,
        )
        assert fn1() == "val1"

        confr.init(
            conf_dir=conf_dir,
            base_conf="conf1",
            overrides={"key1": "overwritten"},
            cli_overrides=False,
        )
        assert fn1() == "overwritten"

        confr.init(
            conf_dir=conf_dir,
            base_conf="conf1",
            conf_patches=["conf2"],
            cli_overrides=False,
        )
        assert fn1() == "val2"

        confr.init(
            conf_dir=conf_dir,
            base_conf="conf1",
            conf_patches=["conf2"],
            overrides={"key1": "overwritten"},
            cli_overrides=False,
        )
        assert fn1() == "overwritten"


def test_conf_from_dir_composed():
    with TemporaryDirectory() as conf_dir:
        base_fp = os.path.join(conf_dir, f"{confr.settings.BASE_CONF}.yaml")
        shallow_fp = os.path.join(conf_dir, "shallow.yaml")
        deep_fp = os.path.join(conf_dir, "deep.yaml")
        write_yaml(base_fp, {"conf_key": 123, "neural_net": {"_file": "shallow.yaml", "this key": "is overridden"}})
        write_yaml(shallow_fp, {"num_outputs": 10, "layer_sizes": [20]})
        write_yaml(deep_fp, {"num_outputs": 10, "layer_sizes": [20, 15, 10, 15, 20]})

        confr.init(conf_dir=conf_dir, cli_overrides=False)
        conf = confr.to_dict()
        print(conf)
        assert conf == {
            "conf_key": 123,
            "neural_net": {"num_outputs": 10, "layer_sizes": [20]},
        }

        # TODO
        # confr.init(
        #     conf_dir=conf_dir,
        #     overrides={"neural_net": {"_file": "deep", "this key": "is overridden"}} # nested dict
        # )
        # assert confr.to_dict() == {
        #     "conf_key": 123,
        #     "neural_net": {"num_outputs": 10, "layer_sizes": [20, 15, 10, 15, 20]},
        # }

        # confr.init(
        #     conf_dir=conf_dir,
        #     overrides={"neural_net._file": "deep.yaml"}, # dot notation
        # )
        # assert confr.to_dict() == {
        #     "conf_key": 123,
        #     "neural_net": {"num_outputs": 10, "layer_sizes": [20, 15, 10, 15, 20]},
        # }


def test_validation():
    conf = {
        "batch_size": 32,
        "samples_per_batch": {
            "labelled": 16,
            "gen": {
                "generator1": 8,
                "generator2": 8,
            }
        }
    }
    confr.init(conf=conf, validate=validations, cli_overrides=False)
    confr.init(conf=conf, validate=[validations.validate_batch_size], cli_overrides=False)
    confr.init(conf=conf, validate=validations.validate_batch_size, cli_overrides=False)


def test_write_conf_file():
    with TemporaryDirectory() as tmp_dir:
        confr.init(conf={"key1": "val1"}, cli_overrides=False)
        confr.set("key2", "val2")

        conf_fn = os.path.join(tmp_dir, "conf.yaml")

        confr.write_conf_file(conf_fn)
        assert read_yaml(conf_fn) == {"key1": "val1", "key2": "val2"}

        confr.write_conf_file(conf_fn, except_keys=["key1"])
        assert read_yaml(conf_fn) == {"key2": "val2"}

        confr.set("key3", {"key4": "val4", "key5": "val5"})

        confr.write_conf_file(conf_fn, except_keys=["key3.key4"])
        assert read_yaml(conf_fn) == {"key1": "val1", "key2": "val2", "key3": {"key5": "val5"}}

        confr.write_conf_file(conf_fn, except_keys=["key3.key4", "key3.key5"])
        assert read_yaml(conf_fn) == {"key1": "val1", "key2": "val2", "key3": {}}


def test_write_conf_file_with_interpolations():
    with TemporaryDirectory() as tmp_dir:
        conf = {
            "encoder_fn": "@confr.test.imports.get_encoder",
            "encoder": "@confr.test.imports.get_encoder()",
            "encoder/num": 4,
            "num": 3,
            "k1": {"k2": "${encoder}"},
            "my": {
                "encoder": "@confr.test.imports.get_encoder()",
                "encoder/num": 5,
            },
        }
        conf_orig = deepcopy(conf)
        confr.init(conf=conf, cli_overrides=False)

        # ensure singletons are initialised
        get_model1()
        get_model2()
        confr.get("encoder_fn")
        confr.get("encoder")
        confr.get("k1.k2")
        confr.get("my.encoder")

        conf_fn = os.path.join(tmp_dir, "conf.yaml")
        confr.write_conf_file(conf_fn)
        assert read_yaml(conf_fn) == conf_orig


# %%
