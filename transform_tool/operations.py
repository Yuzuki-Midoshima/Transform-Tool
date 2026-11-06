"""Maya operations used by Transform Tool."""

from contextlib import contextmanager

from maya import cmds
from maya.api import OpenMaya

from .naming import transform_group_name


CHANNELS = ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz")
RESET_VALUES = {
    "tx": 0.0, "ty": 0.0, "tz": 0.0,
    "rx": 0.0, "ry": 0.0, "rz": 0.0,
    "sx": 1.0, "sy": 1.0, "sz": 1.0,
}
TOLERANCE = 1.0e-5


@contextmanager
def undo_chunk(name):
    cmds.undoInfo(openChunk=True, chunkName=name)
    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)


def _warn(message):
    cmds.warning("Transform Tool: " + message)


def _selected_transforms():
    selection = cmds.ls(selection=True, long=True) or []
    result = []
    seen = set()
    for node in selection:
        if not cmds.objExists(node):
            continue
        if cmds.nodeType(node) in ("transform", "joint"):
            transform = node
        else:
            parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
            transform = parents[0] if parents else None
        if transform and transform not in seen:
            seen.add(transform)
            result.append(transform)
    if not result:
        _warn("Select one or more transform objects.")
    return result


def _is_joint_controller(node):
    if cmds.nodeType(node) != "joint":
        return False
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    return any(cmds.nodeType(shape) == "nurbsCurve" for shape in shapes)


def _non_joint_transforms():
    transforms = _selected_transforms()
    joints = [node for node in transforms if cmds.nodeType(node) == "joint"]
    if joints:
        _warn("Joints were skipped: {}".format(", ".join(joints)))
    return [node for node in transforms if cmds.nodeType(node) != "joint"]


def _group_targets(allow_joint_controllers=False):
    transforms = _selected_transforms()
    accepted = []
    skipped = []
    for node in transforms:
        if cmds.nodeType(node) != "joint":
            accepted.append(node)
        elif allow_joint_controllers and _is_joint_controller(node):
            accepted.append(node)
        else:
            skipped.append(node)
    if skipped:
        _warn("Joints were skipped: {}".format(", ".join(skipped)))
    return accepted


def _inspect_attributes(nodes):
    connections_found = []
    locked = []
    for node in nodes:
        for channel in CHANNELS:
            plug = "{}.{}".format(node, channel)
            if cmds.getAttr(plug, lock=True):
                locked.append((node, channel))
            connections = cmds.listConnections(
                plug, source=True, destination=False, plugs=True
            ) or []
            if connections:
                connections_found.append("{} (connected from {})".format(
                    plug, ", ".join(connections)
                ))
    return connections_found, locked


def _locked_messages(locked):
    return ["{}.{} (locked)".format(node, channel) for node, channel in locked]


def _lock_records(locked):
    records = []
    for node, channel in locked:
        node_uuid = (cmds.ls(node, uuid=True) or [None])[0]
        records.append((node_uuid, node, channel))
    return records


def _set_record_locks(records, locked):
    for node_uuid, original_node, channel in records:
        matches = cmds.ls(node_uuid, long=True) if node_uuid else None
        node = matches[0] if matches else original_node
        if cmds.objExists("{}.{}".format(node, channel)):
            cmds.setAttr("{}.{}".format(node, channel), lock=locked)


def center_pivot():
    nodes = _selected_transforms()
    if not nodes:
        return []
    with undo_chunk("Transform Tool - Center Pivot"):
        for node in nodes:
            cmds.xform(node, centerPivots=True)
    return nodes


def freeze_transformations():
    nodes = _non_joint_transforms()
    if not nodes:
        return []
    with undo_chunk("Transform Tool - Freeze Transformations"):
        cmds.makeIdentity(nodes, apply=True, translate=True, rotate=True, scale=True,
                          normal=False, preserveNormals=True)
    return nodes


def _curve_controllers(visible_only=False):
    """Return unique transforms that directly own a NURBS curve shape."""
    shapes = cmds.ls(type="nurbsCurve", long=True) or []
    if visible_only and shapes:
        shapes = cmds.ls(shapes, visible=True, long=True) or []

    controllers = []
    seen = set()
    for shape in shapes:
        if cmds.getAttr(shape + ".intermediateObject"):
            continue
        parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        if not parents:
            continue
        controller = parents[0]
        if controller not in seen:
            seen.add(controller)
            controllers.append(controller)
    return controllers


def controller_animation_summary():
    """Return ``(controller, key_count)`` rows for animated controllers."""
    rows = []
    for controller in _curve_controllers():
        count = cmds.keyframe(controller, query=True, keyframeCount=True) or 0
        if count:
            rows.append((controller, int(count)))
    return rows


def controller_reset_plan():
    """Describe resettable plugs and controller-level skip reasons."""
    changes = []
    skipped = []
    for controller in _curve_controllers(visible_only=True):
        if (cmds.lockNode(controller, query=True, lock=True) or [False])[0]:
            skipped.append((controller, "node locked"))
            continue
        controller_changes = []
        for channel, value in RESET_VALUES.items():
            plug = "{}.{}".format(controller, channel)
            if not cmds.getAttr(plug, settable=True):
                continue
            if not (cmds.getAttr(plug, keyable=True) or
                    cmds.getAttr(plug, channelBox=True)):
                continue
            current = cmds.getAttr(plug)
            if abs(current - value) > TOLERANCE:
                controller_changes.append((channel, current, value))
        if controller_changes:
            changes.append((controller, controller_changes))
    return changes, skipped


def delete_all_controller_animation(controllers=None):
    """Delete every animation key from all curve controllers in the scene."""
    controllers = list(controllers) if controllers is not None else _curve_controllers()
    if not controllers:
        _warn("No curve controllers were found.")
        return 0

    key_count = cmds.keyframe(controllers, query=True, keyframeCount=True) or 0
    if key_count:
        with undo_chunk("Transform Tool - Delete Controller Animation"):
            cmds.cutKey(controllers, clear=True)
    return int(key_count)


def reset_all_visible_controllers(plan=None):
    """Reset safe, animator-facing transform channels on visible controllers."""
    if plan is None:
        plan, skipped_rows = controller_reset_plan()
    else:
        plan = list(plan)
        skipped_rows = []
    changed = []
    with undo_chunk("Transform Tool - Reset Visible Controllers"):
        for controller, channel_changes in plan:
            if not channel_changes:
                continue
            for channel, unused_current, value in channel_changes:
                plug = "{}.{}".format(controller, channel)
                cmds.setAttr(plug, value)
            changed.append(controller)
    return changed, [controller for controller, unused_reason in skipped_rows]


def _unique_name(parent, requested):
    siblings = cmds.listRelatives(parent, children=True, fullPath=False) if parent else None
    siblings = set(siblings or [])
    if requested not in siblings and not (not parent and cmds.objExists(requested)):
        return requested
    index = 1
    while True:
        candidate = "{}{}".format(requested, index)
        if candidate not in siblings and (parent or not cmds.objExists(candidate)):
            return candidate
        index += 1


def _assert_identity(node):
    values = cmds.getAttr(node + ".translate")[0] + cmds.getAttr(node + ".rotate")[0]
    scales = cmds.getAttr(node + ".scale")[0]
    return (all(abs(value) <= TOLERANCE for value in values) and
            all(abs(value - 1.0) <= TOLERANCE for value in scales))


def create_transform_group(node, suffix="ZERO"):
    """Insert one matching transform above *node* and return its long name."""
    world_matrix = cmds.xform(node, query=True, matrix=True, worldSpace=True)
    original_parent = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
    requested = transform_group_name(node, suffix)
    group = cmds.group(empty=True, name=_unique_name(original_parent, requested))
    if original_parent:
        group = cmds.parent(group, original_parent)[0]
    cmds.xform(group, matrix=world_matrix, worldSpace=True)
    node = cmds.parent(node, group, absolute=True)[0]

    if not _assert_identity(node):
        raise RuntimeError("Could not clean local transforms for {}".format(node))
    resulting_matrix = cmds.xform(node, query=True, matrix=True, worldSpace=True)
    if any(abs(before - after) > TOLERANCE
           for before, after in zip(world_matrix, resulting_matrix)):
        raise RuntimeError("World transform changed for {}".format(node))
    return (cmds.ls(group, long=True) or [group])[0]


def create_connected_transform_group(node, suffix="ZERO"):
    """Move incoming transform drivers to a new parent and zero the child."""
    world_matrix = cmds.xform(node, query=True, matrix=True, worldSpace=True)
    incoming = []
    driver_nodes = set()
    for channel in CHANNELS:
        destination = "{}.{}".format(node, channel)
        sources = cmds.listConnections(
            destination, source=True, destination=False, plugs=True
        ) or []
        for source in sources:
            incoming.append((source, channel))
            driver_nodes.add(source.split(".", 1)[0])

    # Constraints read these properties from the constrained transform. Once
    # their outputs drive the new group, their support inputs must follow too.
    support_connections = []
    for attribute in (
            "parentInverseMatrix[0]", "rotatePivot", "rotatePivotTranslate",
            "rotateOrder"):
        source = "{}.{}".format(node, attribute)
        destinations = cmds.listConnections(
            source, source=False, destination=True, plugs=True
        ) or []
        for destination in destinations:
            if destination.split(".", 1)[0] in driver_nodes:
                support_connections.append((attribute, destination))

    for source, channel in incoming:
        cmds.disconnectAttr(source, "{}.{}".format(node, channel))
    for attribute, destination in support_connections:
        cmds.disconnectAttr("{}.{}".format(node, attribute), destination)

    group = create_transform_group(node, suffix)

    for attribute, destination in support_connections:
        cmds.connectAttr("{}.{}".format(group, attribute), destination, force=True)
    for source, channel in incoming:
        cmds.connectAttr(source, "{}.{}".format(group, channel), force=True)

    child = (cmds.listRelatives(group, children=True, type="transform",
                                fullPath=True) or [None])[0]
    resulting_matrix = cmds.xform(child, query=True, matrix=True, worldSpace=True)
    if any(abs(before - after) > TOLERANCE
           for before, after in zip(world_matrix, resulting_matrix)):
        raise RuntimeError("World transform changed for {}".format(child))
    return group


def create_joint_controller_group(node, suffix="ZERO"):
    """Insert a group above a curve-shaped joint without changing jointOrient."""
    world_matrix = cmds.xform(node, query=True, matrix=True, worldSpace=True)
    joint_orient = cmds.getAttr(node + ".jointOrient")[0]
    rotate_axis = cmds.getAttr(node + ".rotateAxis")[0]
    original_parent = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
    requested = transform_group_name(node, suffix)
    group = cmds.group(empty=True, name=_unique_name(original_parent, requested))
    if original_parent:
        group = cmds.parent(group, original_parent, relative=True)[0]

    # The empty group starts as an identity child of the original parent. Relative
    # parenting therefore preserves the joint's authored local attributes.
    node = cmds.parent(node, group, relative=True)[0]
    cmds.setAttr(node + ".translate", 0.0, 0.0, 0.0, type="double3")
    cmds.setAttr(node + ".rotate", 0.0, 0.0, 0.0, type="double3")
    cmds.setAttr(node + ".scale", 1.0, 1.0, 1.0, type="double3")

    # An identity rotate channel on a joint can still contain jointOrient and
    # rotateAxis. Solve the group matrix around that retained local matrix.
    local_matrix = OpenMaya.MMatrix(cmds.getAttr(node + ".matrix"))
    target_world = OpenMaya.MMatrix(world_matrix)
    group_world = local_matrix.inverse() * target_world
    cmds.xform(group, matrix=list(group_world), worldSpace=True)

    if not _assert_identity(node):
        raise RuntimeError("Could not clean joint controller channels for {}".format(node))
    if any(abs(a - b) > TOLERANCE
           for a, b in zip(joint_orient, cmds.getAttr(node + ".jointOrient")[0])):
        raise RuntimeError("jointOrient changed for {}".format(node))
    if any(abs(a - b) > TOLERANCE
           for a, b in zip(rotate_axis, cmds.getAttr(node + ".rotateAxis")[0])):
        raise RuntimeError("rotateAxis changed for {}".format(node))
    resulting_matrix = cmds.xform(node, query=True, matrix=True, worldSpace=True)
    if any(abs(before - after) > TOLERANCE
           for before, after in zip(world_matrix, resulting_matrix)):
        raise RuntimeError("World transform changed for {}".format(node))
    return (cmds.ls(group, long=True) or [group])[0]


def create_groups(suffixes, unlock_locked=False, allow_joint_controllers=False):
    nodes = _group_targets(allow_joint_controllers=allow_joint_controllers)
    if not nodes:
        return []
    suffixes = tuple(suffixes)
    try:
        for suffix in suffixes:
            transform_group_name(nodes[0], suffix)
    except ValueError as error:
        _warn(str(error))
        return []

    connections, locked = _inspect_attributes(nodes)
    # Locked channels are temporarily unlocked below and restored afterward.
    # Hidden/keyable state and incoming connections are preserved.
    connected_nodes = {
        message.split(".", 1)[0] for message in connections
    }

    # Descendants first keeps selected parent/child pairs stable.
    nodes.sort(key=lambda item: item.count("|"), reverse=True)
    created = []
    lock_records = _lock_records(locked)
    try:
        if lock_records:
            _set_record_locks(lock_records, False)
        with undo_chunk("Transform Tool - Create Groups"):
            for node in nodes:
                current = node
                for suffix in reversed(suffixes):
                    if cmds.nodeType(current) == "joint":
                        current = create_joint_controller_group(current, suffix)
                    elif current in connected_nodes:
                        current = create_connected_transform_group(current, suffix)
                        connected_nodes.add(current)
                    else:
                        current = create_transform_group(current, suffix)
                    created.append(current)
    except Exception as error:
        # The chunk has closed at this point, so one undo cleanly rolls back all
        # groups made before an unexpected validation failure.
        cmds.undo()
        _warn(str(error))
        return []
    finally:
        if lock_records:
            _set_record_locks(lock_records, True)
    return created


def create_zero(suffix="ZERO", unlock_locked=False, allow_joint_controllers=False):
    return create_groups((suffix,), unlock_locked=unlock_locked,
                         allow_joint_controllers=allow_joint_controllers)


def create_offset(suffix="OFFSET", unlock_locked=False, allow_joint_controllers=False):
    return create_groups((suffix,), unlock_locked=unlock_locked,
                         allow_joint_controllers=allow_joint_controllers)


def create_zero_offset(offset_suffix="OFFSET", zero_suffix="ZERO",
                       unlock_locked=False, allow_joint_controllers=False):
    return create_groups((offset_suffix, zero_suffix), unlock_locked=unlock_locked,
                         allow_joint_controllers=allow_joint_controllers)
