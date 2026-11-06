"""Compact PySide6 interface for Transform Tool."""

import os

from maya import OpenMayaUI, cmds
from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import wrapInstance

from . import operations


WINDOW_OBJECT_NAME = "transformToolWindow"
RIG_CTRL_SHAPE_WINDOW_OBJECT_NAME = "RigCtrlShapeTool"


def _maya_main_window():
    pointer = OpenMayaUI.MQtUtil.mainWindow()
    return wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None


def _display_node_name(node):
    """Return a compact DAG leaf name while operations retain the full path."""
    return node.rsplit("|", 1)[-1]


def _commit_active_shape_preview():
    """Let Rig Ctrl Shape Tool finalize its visible non-destructive edit."""
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() != RIG_CTRL_SHAPE_WINDOW_OBJECT_NAME:
            continue
        commit = getattr(widget, "commit_active_preview", None)
        if callable(commit):
            return bool(commit())
    return False


class ConfirmationDialog(QtWidgets.QDialog):
    """Compact confirmation dialog with collapsible, scrollable details."""

    def __init__(self, title, summary, details, action_text, destructive=False,
                 can_execute=True, item_action_text=None, item_action=None,
                 item_actions=None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(430)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        summary_label = QtWidgets.QLabel(summary)
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)

        self.details_button = QtWidgets.QToolButton()
        self._initial_can_execute = can_execute
        self._item_actions = list(item_actions or [])
        if item_action_text and item_action:
            self._item_actions.append((item_action_text, item_action, True))
        self.details_button.setText("対象の詳細（{}件）".format(len(details)))
        self.details_button.setCheckable(True)
        self.details_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.details_button.toggled.connect(self._toggle_details)
        layout.addWidget(self.details_button)

        self.details_list = QtWidgets.QListWidget()
        self.details_list.setAlternatingRowColors(True)
        self.details_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.details_list.setMaximumHeight(210)
        self.details_list.setMinimumHeight(90)
        layout.addWidget(self.details_list)

        for detail in details:
            text, payload = detail if isinstance(detail, tuple) else (detail, detail)
            self._add_detail(text, payload)

        buttons = QtWidgets.QDialogButtonBox()
        self.execute_button = buttons.addButton(
            action_text, QtWidgets.QDialogButtonBox.AcceptRole
        )
        buttons.addButton("キャンセル", QtWidgets.QDialogButtonBox.RejectRole)
        self.execute_button.setEnabled(bool(details) and can_execute)
        if destructive:
            self.execute_button.setStyleSheet("QPushButton { color: #ffb0a8; }")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.details_button.setChecked(0 < len(details) <= 8)
        self._toggle_details(self.details_button.isChecked())

    def _toggle_details(self, expanded):
        self.details_button.setArrowType(
            QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow
        )
        self.details_list.setVisible(expanded)
        QtCore.QTimer.singleShot(0, self.adjustSize)

    def _add_detail(self, text, payload):
        item = QtWidgets.QListWidgetItem(self.details_list)
        item.setData(QtCore.Qt.UserRole, payload)

        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QVBoxLayout(row)
        row_layout.setContentsMargins(6, 3, 3, 3)
        row_layout.setSpacing(2)

        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(4)
        label = QtWidgets.QLabel(text)
        label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        label.setStyleSheet("font-family: monospace;")
        label.setWordWrap(True)
        remove = QtWidgets.QToolButton()
        remove.setText("×")
        remove.setToolTip("このコントローラーを一覧から除外")
        remove.setFixedSize(22, 22)
        remove.clicked.connect(lambda unused=False, target=item: self._remove_detail(target))
        header_layout.addWidget(label, 1)
        header_layout.addWidget(remove, 0, QtCore.Qt.AlignTop)
        row_layout.addLayout(header_layout)

        action_layout = QtWidgets.QHBoxLayout()
        action_layout.setSpacing(4)
        action_layout.addStretch(1)
        for action in self._item_actions:
            action_text, action_callback, remove_after = action[:3]
            enabled_for_payload = action[3] if len(action) > 3 else None
            execute_one = QtWidgets.QPushButton(action_text)
            execute_one.setToolTip("このコントローラーの{}を実行".format(action_text))
            execute_one.setFixedHeight(22)
            execute_one.setMinimumWidth(42)
            if enabled_for_payload:
                execute_one.setEnabled(enabled_for_payload(payload))
            execute_one.clicked.connect(
                lambda unused=False, target=item, data=payload,
                callback=action_callback, should_remove=remove_after, button=execute_one:
                self._execute_one(target, data, callback, should_remove, button)
            )
            action_layout.addWidget(execute_one)
        row_layout.addLayout(action_layout)
        item.setSizeHint(row.sizeHint())
        self.details_list.setItemWidget(item, row)

    def _remove_detail(self, item):
        row = self.details_list.row(item)
        if row >= 0:
            self.details_list.takeItem(row)
        count = self.details_list.count()
        self.details_button.setText("対象の詳細（{}件）".format(count))
        self.execute_button.setEnabled(count > 0 and self._initial_can_execute)

    def _execute_one(self, item, payload, callback, remove_after, button):
        callback(payload)
        if remove_after:
            self._remove_detail(item)
        else:
            button.setEnabled(False)
            button.setText("済")

    def payloads(self):
        return [
            self.details_list.item(index).data(QtCore.Qt.UserRole)
            for index in range(self.details_list.count())
        ]


class TransformToolWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or _maya_main_window())
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("Transform Tool")
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowMaximizeButtonHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.setMinimumWidth(320)
        self._settings = QtCore.QSettings("TransformTool", "TransformTool")
        self._open_dialogs = []
        self._build_ui()
        self._selection_timer = QtCore.QTimer(self)
        self._selection_timer.setInterval(300)
        self._selection_timer.timeout.connect(self._update_selection_label)
        self._selection_timer.start()
        self._update_selection_label()
        self.adjustSize()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.selection_label = QtWidgets.QLabel("選択中のオブジェクト")
        self.selection_label.setStyleSheet("font-weight: bold; color: #b8b8b8;")
        self.selection_label.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )
        root.addWidget(self.selection_label)

        icon_row = QtWidgets.QHBoxLayout()
        image_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "images"))
        specs = (
            ("CenterPivot.png", "Center Pivot",
             "Move the pivot to the center of the selected object.",
             operations.center_pivot),
            ("FreezeTransformations.png", "Freeze Transforms",
             "Freeze Translate, Rotate and Scale. Joints are skipped.",
             self._freeze_transformations),
        )
        for filename, label, tooltip, callback in specs:
            button = QtWidgets.QToolButton()
            button.setIcon(QtGui.QIcon(os.path.join(image_dir, filename)))
            button.setIconSize(QtCore.QSize(36, 36))
            button.setText(label)
            button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            button.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                 QtWidgets.QSizePolicy.Fixed)
            button.setFixedHeight(70)
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            icon_row.addWidget(button)
        root.addLayout(icon_row)

        group_label = QtWidgets.QLabel("選択コントローラーのグループ")
        group_label.setStyleSheet("font-weight: bold; color: #b8b8b8;")
        group_label.setToolTip("Insert groups while preserving the world transform.")
        root.addWidget(group_label)

        row = QtWidgets.QHBoxLayout()
        for label, tooltip, callback in (
            ("Create ZERO", "Create a ZERO group for the controller's rest pose.",
             self._create_zero),
            ("Create OFFSET", "Create an OFFSET group for constraints or space switching.",
             self._create_offset),
        ):
            button = QtWidgets.QPushButton(label)
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            row.addWidget(button)
        root.addLayout(row)

        combined = QtWidgets.QPushButton("Create OFFSET > ZERO")
        combined.setToolTip(
            "Create OFFSET > ZERO > selected controller in one operation."
        )
        combined.clicked.connect(self._create_zero_offset)
        root.addWidget(combined)

        animation_label = QtWidgets.QLabel("シーン内の全コントローラー")
        animation_label.setStyleSheet("font-weight: bold; color: #b8b8b8;")
        root.addWidget(animation_label)

        animation_hint = QtWidgets.QLabel(
            "NURBSカーブのコントローラーをシーン全体から検索します"
        )
        animation_hint.setStyleSheet("color: #929292; font-size: 11px;")
        animation_hint.setWordWrap(True)
        root.addWidget(animation_hint)

        scene_row = QtWidgets.QHBoxLayout()
        delete_animation = QtWidgets.QPushButton("キーを全削除…")
        delete_animation.setToolTip(
            "全カーブコントローラーから全フレームのキーを削除します。"
        )
        delete_animation.clicked.connect(self._confirm_delete_animation)
        scene_row.addWidget(delete_animation)

        reset_controllers = QtWidgets.QPushButton("全て初期値へ…")
        reset_controllers.setToolTip(
            "可視カーブコントローラーの安全なチャンネルを0（Scaleは1）に戻します。"
        )
        reset_controllers.clicked.connect(self._confirm_reset_controllers)
        scene_row.addWidget(reset_controllers)
        root.addLayout(scene_row)

        self.options_button = QtWidgets.QToolButton()
        self.options_button.setText("Options")
        self.options_button.setCheckable(True)
        self.options_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.options_button.setArrowType(QtCore.Qt.RightArrow)
        self.options_button.toggled.connect(self._toggle_options)
        root.addWidget(self.options_button)

        self.options_widget = QtWidgets.QWidget()
        options_layout = QtWidgets.QFormLayout(self.options_widget)
        options_layout.setContentsMargins(8, 2, 8, 4)

        self.zero_suffix = QtWidgets.QLineEdit(
            self._settings.value("zeroSuffix", "ZERO", type=str)
        )
        self.zero_suffix.setPlaceholderText("ZERO")
        self.zero_suffix.setToolTip("Suffix used for the ZERO group name.")
        options_layout.addRow("ZERO name:", self.zero_suffix)

        self.offset_suffix = QtWidgets.QLineEdit(
            self._settings.value("offsetSuffix", "OFFSET", type=str)
        )
        self.offset_suffix.setPlaceholderText("OFFSET")
        self.offset_suffix.setToolTip("Suffix used for the OFFSET group name.")
        options_layout.addRow("OFFSET name:", self.offset_suffix)

        self.allow_joint_controllers = QtWidgets.QCheckBox(
            "カーブ形状を持つジョイントも許可"
        )
        self.allow_joint_controllers.setChecked(
            self._settings.value("allowJointControllers", False, type=bool)
        )
        self.allow_joint_controllers.setToolTip(
            "NURBSカーブ形状を直接持つジョイントを処理対象にします。"
            "jointOrientとrotateAxisは維持され、通常のスケルトンジョイントは除外されます。"
        )
        options_layout.addRow("", self.allow_joint_controllers)
        self.options_widget.setVisible(False)
        root.addWidget(self.options_widget)

        close_button = QtWidgets.QPushButton("Close")
        close_button.setToolTip("Close Transform Tool.")
        close_button.clicked.connect(self.close)
        root.addWidget(close_button)

        self.zero_suffix.editingFinished.connect(self._save_options)
        self.offset_suffix.editingFinished.connect(self._save_options)
        self.allow_joint_controllers.toggled.connect(self._save_options)

    def _freeze_transformations(self):
        # Preview stores a pre-edit CV baseline. Commit it before makeIdentity
        # so a later preview refresh cannot overwrite the frozen result.
        _commit_active_shape_preview()
        return operations.freeze_transformations()

    def _update_selection_label(self):
        selected = cmds.ls(selection=True, objectsOnly=True, long=True) or []
        names = []
        seen = set()
        for node in selected:
            name = _display_node_name(node).split(".", 1)[0]
            if name not in seen:
                seen.add(name)
                names.append(name)

        if not names:
            self.selection_label.setText("選択中のオブジェクト")
            self.selection_label.setToolTip("オブジェクトが選択されていません")
            return

        if len(names) == 1:
            text = "選択中：{}".format(names[0])
        else:
            preview = ", ".join(names[:2])
            remainder = len(names) - 2
            text = "選択中（{}）：{}".format(len(names), preview)
            if remainder > 0:
                text += "、他{}件".format(remainder)
        self.selection_label.setText(text)
        self.selection_label.setToolTip("\n".join(names))

    def _toggle_options(self, expanded):
        self.options_button.setArrowType(
            QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow
        )
        self.options_widget.setVisible(expanded)
        QtCore.QTimer.singleShot(0, self.adjustSize)

    def _save_options(self, *unused):
        self._settings.setValue("zeroSuffix", self.zero_suffix.text().strip())
        self._settings.setValue("offsetSuffix", self.offset_suffix.text().strip())
        self._settings.setValue(
            "allowJointControllers", self.allow_joint_controllers.isChecked()
        )

    def _operation_options(self):
        self._save_options()
        return (
            self.zero_suffix.text().strip(),
            self.offset_suffix.text().strip(),
            True,
            self.allow_joint_controllers.isChecked(),
        )

    def _create_zero(self):
        zero, unused_offset, unlock, allow_joints = self._operation_options()
        operations.create_zero(zero, unlock_locked=unlock,
                               allow_joint_controllers=allow_joints)

    def _create_offset(self):
        unused_zero, offset, unlock, allow_joints = self._operation_options()
        operations.create_offset(offset, unlock_locked=unlock,
                                 allow_joint_controllers=allow_joints)

    def _create_zero_offset(self):
        zero, offset, unlock, allow_joints = self._operation_options()
        operations.create_zero_offset(
            offset, zero, unlock_locked=unlock,
            allow_joint_controllers=allow_joints
        )

    def _show_modeless(self, dialog):
        """Keep a non-modal dialog alive without blocking Maya interaction."""
        dialog.setWindowModality(QtCore.Qt.NonModal)
        dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self._open_dialogs.append(dialog)

        def forget_dialog(unused_result):
            if dialog in self._open_dialogs:
                self._open_dialogs.remove(dialog)

        dialog.finished.connect(forget_dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _show_information(self, title, message):
        box = QtWidgets.QMessageBox(
            QtWidgets.QMessageBox.Information,
            title,
            message,
            QtWidgets.QMessageBox.Ok,
            self,
        )
        self._show_modeless(box)

    def _confirm_delete_animation(self):
        rows = operations.controller_animation_summary()
        details = [(
            "{}  —  {}キー".format(_display_node_name(node), count), node
        )
            for node, count in rows
        ]
        dialog = ConfirmationDialog(
            "全アニメーションキーを削除",
            "一覧に残っているコントローラーのキーを削除します。\n"
            "各行の「削除」で1件ずつ実行、×で対象から除外できます。",
            details,
            "キーを削除",
            destructive=True,
            can_execute=bool(rows),
            item_action_text="削除",
            item_action=self._delete_one_controller_animation,
            parent=self,
        )
        dialog.accepted.connect(
            lambda: self._delete_controller_animation(dialog.payloads())
        )
        self._show_modeless(dialog)

    def _delete_controller_animation(self, controllers):
        count = operations.delete_all_controller_animation(controllers)
        self._show_information(
            "完了", "{}個のアニメーションキーを削除しました。".format(count)
        )

    def _delete_one_controller_animation(self, controller):
        operations.delete_all_controller_animation([controller])

    def _confirm_reset_controllers(self):
        plan, skipped = operations.controller_reset_plan()
        details = []
        for controller, changes in plan:
            values = ", ".join(
                "{}: {:g} → {:g}".format(channel, current, target)
                for channel, current, target in changes
            )
            details.append((
                "{}\n    {}".format(_display_node_name(controller), values),
                (controller, changes),
            ))

        dialog = ConfirmationDialog(
            "全コントローラーを初期値に戻す",
            "一覧に残っているコントローラーを初期値へ戻します。\n"
            "各行で移動・回転・スケールを個別または一括で初期化できます。",
            details,
            "初期値に戻す",
            can_execute=bool(plan),
            item_actions=(
                ("移動", lambda row: self._reset_one_controller_group(row, "t"), True,
                 lambda row: any(change[0].startswith("t") for change in row[1])),
                ("回転", lambda row: self._reset_one_controller_group(row, "r"), True,
                 lambda row: any(change[0].startswith("r") for change in row[1])),
                ("スケール", lambda row: self._reset_one_controller_group(row, "s"), True,
                 lambda row: any(change[0].startswith("s") for change in row[1])),
                ("すべて", self._reset_one_controller, True),
            ),
            parent=self,
        )
        dialog.accepted.connect(
            lambda: self._reset_visible_controllers(dialog.payloads())
        )
        self._show_modeless(dialog)

    def _reset_visible_controllers(self, plan):
        changed, skipped = operations.reset_all_visible_controllers(plan)
        message = "{}個のコントローラーを初期値に戻しました。".format(len(changed))
        if skipped:
            message += "\nロックされた{}個はスキップしました。".format(len(skipped))
        self._show_information("完了", message)

    def _reset_one_controller(self, plan_row):
        operations.reset_all_visible_controllers([plan_row])

    def _reset_one_controller_group(self, plan_row, channel_prefix):
        controller, changes = plan_row
        filtered = [
            change for change in changes if change[0].startswith(channel_prefix)
        ]
        operations.reset_all_visible_controllers([(controller, filtered)])


_window = None


def show():
    global _window
    # Also find windows created by an older, already-reloaded ui module.
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == WINDOW_OBJECT_NAME:
            widget.close()
            widget.deleteLater()
    _window = TransformToolWindow()
    _window.show()
    _window.raise_()
    _window.activateWindow()
    return _window
