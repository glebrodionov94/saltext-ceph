"""Keep public interfaces aligned and safe as controller coverage grows."""

import ast
import importlib
import inspect

import salt.loader

from saltext.ceph import PACKAGE_ROOT

FORBIDDEN_INLINE_SECRET_ARGUMENTS = {
    "access_key",
    "keyring",
    "mutual_password",
    "password",
    "private_key",
    "secret",
    "secret_key",
    "token",
}

# These DELETE requests reset configuration to an inherited/default value. The
# transport's generic request method is also an intentional low-level primitive.
UNCONFIRMED_DELETE_EXCEPTIONS = {
    ("client.py", "request"),
    ("cluster_configuration.py", "remove"),
    ("settings.py", "delete"),
}

UNCONFIRMED_ABSENT_STATE_EXCEPTIONS = {
    # Removing a monitor config override reveals Ceph's inherited/default value.
    ("ceph_cluster_config.py", "absent"),
}


def _module_names(directory):
    return {
        path.stem for path in (PACKAGE_ROOT / directory).glob("*.py") if path.name != "__init__.py"
    }


def _public_functions(module):
    return {
        name: value
        for name, value in vars(module).items()
        if inspect.isfunction(value)
        and value.__module__ == module.__name__
        and not name.startswith("_")
        and name != "__virtual__"
    }


def test_every_execution_module_has_a_matching_salt_ssh_wrapper():
    execution_names = _module_names("modules")
    wrapper_names = _module_names("wrapper")
    assert wrapper_names == execution_names | {"ceph"}

    for name in sorted(execution_names):
        execution = importlib.import_module(f"saltext.ceph.modules.{name}")
        wrapper = importlib.import_module(f"saltext.ceph.wrapper.{name}")
        execution_functions = _public_functions(execution)
        wrapper_functions = _public_functions(wrapper)

        assert set(wrapper_functions) == set(execution_functions), name
        for function_name, function in execution_functions.items():
            assert inspect.signature(wrapper_functions[function_name]) == inspect.signature(
                function
            ), f"{name}.{function_name}"


def test_public_loaders_do_not_accept_inline_secret_arguments():
    for directory in ("modules", "wrapper", "states", "runners", "beacons"):
        names = _module_names(directory)
        if directory == "wrapper":
            names -= {"ceph"}
        for name in sorted(names):
            module = importlib.import_module(f"saltext.ceph.{directory}.{name}")
            for function_name, function in _public_functions(module).items():
                parameters = set(inspect.signature(function).parameters)
                assert not parameters & FORBIDDEN_INLINE_SECRET_ARGUMENTS, (
                    f"{module.__name__}.{function_name} accepts a credential directly; "
                    "use an absolute local *_source file instead"
                )


def test_raw_destructive_requests_expose_an_explicit_confirmation():
    utility_root = PACKAGE_ROOT / "utils" / "ceph"
    exceptions_seen = set()
    for path in sorted(utility_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
            if not any(
                isinstance(node, ast.Constant) and node.value == "DELETE"
                for node in ast.walk(function)
            ):
                continue
            identity = (path.name, function.name)
            parameters = {
                argument.arg
                for argument in (
                    function.args.posonlyargs + function.args.args + function.args.kwonlyargs
                )
            }
            if identity in UNCONFIRMED_DELETE_EXCEPTIONS:
                exceptions_seen.add(identity)
            else:
                assert "confirm" in parameters, f"{path.name}:{function.lineno}"

    assert exceptions_seen == UNCONFIRMED_DELETE_EXCEPTIONS


def test_absent_states_expose_an_explicit_confirmation():
    exceptions_seen = set()
    for path in sorted((PACKAGE_ROOT / "states").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and (node.name == "absent" or node.name.endswith("_absent"))
        ):
            identity = (path.name, function.name)
            parameters = {
                argument.arg
                for argument in (
                    function.args.posonlyargs + function.args.args + function.args.kwonlyargs
                )
            }
            if identity in UNCONFIRMED_ABSENT_STATE_EXCEPTIONS:
                exceptions_seen.add(identity)
            else:
                assert "confirm" in parameters, f"{path.name}:{function.lineno}"

    assert exceptions_seen == UNCONFIRMED_ABSENT_STATE_EXCEPTIONS


def test_salt_loader_discovers_all_runners(master_opts):
    runners = salt.loader.runner(
        master_opts,
        context={},
        whitelist=["ceph", "ceph_gitops"],
    )
    assert {
        "ceph.clear_cache",
        "ceph.ping",
        "ceph.tasks",
        "ceph.wait_task",
        "ceph_gitops.apply",
        "ceph_gitops.plan",
        "ceph_gitops.running",
    }.issubset(runners)
