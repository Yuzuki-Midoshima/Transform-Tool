"""Naming rules for transform utility groups."""

import re


_REPLACEABLE_SUFFIXES = {
    "anim", "ctrl", "control", "ctl", "zero", "offset", "grp", "group"
}


def transform_group_name(node, suffix):
    """Return a namespace-aware transform group name for *node*.

    Common controller/type suffixes are replaced (``L_hand_anim`` becomes
    ``L_hand_ZERO``); otherwise the requested suffix is appended.
    """
    suffix = str(suffix).strip().strip("_")
    if not suffix:
        raise ValueError("Group suffix cannot be empty.")
    if any(character in suffix for character in "|:"):
        raise ValueError("Group suffix cannot contain '|' or ':'.")

    short_name = node.rsplit("|", 1)[-1]
    namespace, separator, leaf = short_name.rpartition(":")
    match = re.match(r"^(.*)_([^_]+)$", leaf)
    if match and match.group(2).lower() in _REPLACEABLE_SUFFIXES:
        leaf = "{}_{}".format(match.group(1), suffix)
    elif not leaf.lower().endswith("_" + suffix.lower()):
        leaf = "{}_{}".format(leaf, suffix)
    return "{}{}{}".format(namespace, separator, leaf) if separator else leaf
