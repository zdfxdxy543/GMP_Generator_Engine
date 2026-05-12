from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QMenu,
    QAction,
    QDialog,
    QLineEdit,
    QFormLayout,
    QDialogButtonBox,
    QFileDialog,
    QPushButton,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QFrame,
    QGraphicsDropShadowEffect,
    QScrollArea,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QPointF, QRectF
from PyQt5.QtGui import QColor, QPainter, QPen, QPolygonF, QFont
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
import csv

V2_ROOT = Path(__file__).resolve().parent.parent
if str(V2_ROOT) not in sys.path:
    sys.path.insert(0, str(V2_ROOT))

import controller_loop_id_exporter as loop_exporter
import merge_loop_ids_into_ctl_main as merger


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('设置')
        self.resize(560, 220)
        self.setObjectName('SettingsDialog')

        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        gmp_root_row = QWidget()
        gmp_root_layout = QHBoxLayout(gmp_root_row)
        gmp_root_layout.setContentsMargins(0, 0, 0, 0)
        gmp_root_layout.setSpacing(6)
        self.gmp_root_edit = QLineEdit()
        self.gmp_root_edit.setPlaceholderText('请选择或输入 GMP 根目录')
        self.browse_btn = QPushButton('浏览...')
        self.browse_btn.clicked.connect(self.choose_gmp_root)
        gmp_root_layout.addWidget(self.gmp_root_edit)
        gmp_root_layout.addWidget(self.browse_btn)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText('请输入 API Key')
        self.api_key_edit.setEchoMode(QLineEdit.Password)

        self.model_name_edit = QLineEdit()
        self.model_name_edit.setPlaceholderText('请输入大模型名称')

        self.model_url_edit = QLineEdit()
        self.model_url_edit.setPlaceholderText('请输入大模型网址')

        form_layout.addRow('GMP根目录', gmp_root_row)
        form_layout.addRow('api-key', self.api_key_edit)
        form_layout.addRow('大模型名称', self.model_name_edit)
        form_layout.addRow('大模型网址', self.model_url_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.on_accept)
        buttons.rejected.connect(self.reject)

        main_layout.addLayout(form_layout)
        main_layout.addWidget(buttons)

        # config file path
        self._config_path = Path(__file__).parent / 'config.json'
        self.load_settings()

    def choose_gmp_root(self):
        folder = QFileDialog.getExistingDirectory(self, '选择 GMP 根目录')
        if folder:
            self.gmp_root_edit.setText(folder)

    def on_accept(self):
        self.save_settings()
        self.accept()

    def load_settings(self):
        try:
            if self._config_path.exists():
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.gmp_root_edit.setText(data.get('gmp_root', ''))
                self.api_key_edit.setText(data.get('api_key', ''))
                self.model_name_edit.setText(data.get('model_name', ''))
                self.model_url_edit.setText(data.get('model_url', ''))
        except Exception:
            pass

    def save_settings(self):
        data = {
            'gmp_root': self.gmp_root_edit.text().strip(),
            'api_key': self.api_key_edit.text().strip(),
            'model_name': self.model_name_edit.text().strip(),
            'model_url': self.model_url_edit.text().strip(),
        }
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


class NewProjectDialog(QDialog):
    def __init__(self, config_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle('新建项目')
        self.resize(640, 240)
        self.setObjectName('NewProjectDialog')
        self._config_path = Path(config_path)

        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.fixed_path_label = QLabel(self._get_project_parent_display_path())
        self.fixed_path_label.setWordWrap(True)

        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText('请输入项目名')

        self.max_iter_spin = QSpinBox()
        self.max_iter_spin.setRange(1, 9999)
        self.max_iter_spin.setValue(5)

        form_layout.addRow('固定路径', self.fixed_path_label)
        form_layout.addRow('项目名', self.project_name_edit)
        form_layout.addRow('最大迭代次数', self.max_iter_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.on_accept)
        buttons.rejected.connect(self.reject)

        main_layout.addLayout(form_layout)
        main_layout.addWidget(buttons)

        self.project_root = None
        self.project_json_path = None

    def _read_gmp_root(self):
        if not self._config_path.exists():
            return ''
        with open(self._config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return str(data.get('gmp_root', '')).strip()

    def _get_project_parent_path(self):
        gmp_root = self._read_gmp_root()
        if not gmp_root:
            return None
        return Path(gmp_root) / 'ctl' / 'suite'

    def _get_project_parent_display_path(self):
        project_parent = self._get_project_parent_path()
        return str(project_parent) if project_parent else '未配置 GMP 根目录'

    def _get_template_project_path(self):
        project_parent = self._get_project_parent_path()
        if not project_parent:
            return None
        return project_parent / 'mcs_pmsm_nt'

    def _build_project_data(self, project_root):
        return {
            'gmp_path': self._read_gmp_root(),
            'sln_path': str(project_root / 'main.sln'),
            'simulink_model_path': str(project_root / 'simulink_model.slx'),
            'src_folder_path': str(project_root / 'src'),
            'iteration_parameter_header_path': str(project_root / 'paras.h'),
            'objective_text': '',
            'task_type': '',
            'max_iterations': int(self.max_iter_spin.value()),
            'structured_requirement': {
                'performance_requirements': '',
                'selected_loops': [],
            },
        }

    def on_accept(self):
        project_name = self.project_name_edit.text().strip()

        if not project_name:
            QMessageBox.warning(self, '提示', '请先填写项目名。')
            return

        gmp_root = self._read_gmp_root()
        if not gmp_root:
            QMessageBox.warning(self, '提示', '请先在“设置”中配置 GMP 根目录。')
            return

        project_parent = self._get_project_parent_path()
        if project_parent is None:
            QMessageBox.warning(self, '提示', '无法确定项目固定路径。')
            return

        project_root = project_parent / project_name
        if project_root.exists():
            QMessageBox.warning(self, '提示', f'项目目录已存在：{project_root}')
            return

        template_root = self._get_template_project_path()
        if template_root is None or not template_root.exists():
            QMessageBox.warning(
                self,
                '提示',
                f'模板文件夹不存在：{template_root}',
            )
            return

        try:
            project_parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(template_root, project_root)

            project_data = self._build_project_data(project_root)
            self.project_json_path = project_root / f'{project_name}.json'
            with open(self.project_json_path, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, ensure_ascii=False, indent=2)

            self.project_root = project_root
            QMessageBox.information(
                self,
                '完成',
                f'项目已创建：{self.project_json_path}',
            )
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, '错误', f'创建项目失败：{exc}')


def read_ui_settings() -> dict:
    config_path = Path(__file__).parent / 'config.json'
    if not config_path.exists():
        return {}
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def resolve_ui_api_key(settings: dict) -> str:
    return (
        str(settings.get('api_key', '')).strip()
        or os.getenv('SILICONFLOW_API_KEY', '').strip()
        or os.getenv('OPENAI_API_KEY', '').strip()
    )


class ChatInputEdit(QTextEdit):
    enterPressed = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            event.accept()
            self.enterPressed.emit()
            return
        super().keyPressEvent(event)


class ChatBubbleWidget(QFrame):
    def __init__(self, role: str, text: str, parent=None):
        super().__init__(parent)
        self.role = role
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        self.setMinimumWidth(0)
        self.setObjectName(f'chatBubble_{role}')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 16, 22, 16)
        layout.setSpacing(8)

        self.title = QLabel('')
        self.title.setObjectName('chatBubbleTitle')
        self.body = QLabel(text or '')
        self.body.setObjectName('chatBubbleBody')
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body.setStyleSheet('background: transparent;')
        self.body.setMinimumWidth(0)

        layout.addWidget(self.title)
        layout.addWidget(self.body)

        if role == 'user':
            self.title.setText('用户')
            self.setStyleSheet(
                'QFrame{background:#0f62fe;border:none;border-top-left-radius:18px;border-top-right-radius:18px;'
                'border-bottom-left-radius:18px;border-bottom-right-radius:4px;}'
            )
            self.title.setStyleSheet('color:#ffffff;font-size:9pt;font-weight:700;')
            self.body.setStyleSheet('color:#ffffff;background:transparent;')
        elif role == 'model':
            self.title.setText('大模型')
            self.setStyleSheet(
                'QFrame{background:#ffffff;border:1px solid #d9e2ec;'
                'border-top-left-radius:18px;border-top-right-radius:18px;'
                'border-bottom-left-radius:4px;border-bottom-right-radius:18px;}'
            )
            self.title.setStyleSheet('color:#0f62fe;font-size:9pt;font-weight:700;')
            self.body.setStyleSheet('color:#1f2937;background:transparent;')
        else:
            self.title.hide()
            self.setStyleSheet(
                'QFrame{background:#eef2f7;border:1px solid #d9e2ec;border-radius:999px;}'
            )
            self.body.setStyleSheet('color:#64748b;background:transparent;')


class ChatStreamWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = []
        self.message_rows = []
        self.setObjectName('chatStreamWidget')

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet('QScrollArea{background:transparent;border:none;}')

        self.container = QWidget()
        self.container.setAttribute(Qt.WA_StyledBackground, True)
        self.container.setStyleSheet('background: transparent;')
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(12, 12, 12, 12)
        self.container_layout.setSpacing(14)
        self.container_layout.addStretch(1)

        self.scroll.setWidget(self.container)
        outer_layout.addWidget(self.scroll)

    def clear_messages(self):
        self.messages.clear()
        self.message_rows.clear()
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.container_layout.addStretch(1)

    def append_message(self, role: str, text: str):
        self.messages.append((role, text))

        last_item = self.container_layout.itemAt(self.container_layout.count() - 1)
        if last_item and last_item.spacerItem():
            self.container_layout.takeAt(self.container_layout.count() - 1)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        bubble = ChatBubbleWidget(role, text)
        bubble.adjustSize()

        if role == 'user':
            row_layout.addStretch(1)
            row_layout.addWidget(bubble, 0, Qt.AlignRight)
            row_layout.addSpacing(18)
        elif role == 'model':
            row_layout.addSpacing(18)
            row_layout.addWidget(bubble, 0, Qt.AlignLeft)
            row_layout.addStretch(1)
        else:
            bubble.title.hide()
            row_layout.addStretch(1)
            row_layout.addWidget(bubble, 0, Qt.AlignCenter)
            row_layout.addStretch(1)

        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.container_layout.addWidget(row)
        self.container_layout.addStretch(1)
        self.message_rows.append((role, row, bubble))
        self._update_bubble_widths()
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_bubble_widths()

    def _update_bubble_widths(self):
        viewport_width = max(0, self.scroll.viewport().width())
        content_width = max(0, viewport_width - 24)
        user_model_width = max(420, min(860, int(content_width * 0.68)))
        system_width = max(300, min(760, int(content_width * 0.55)))

        for role, _row, bubble in self.message_rows:
            if role in {'user', 'model'}:
                bubble.setFixedWidth(user_model_width)
            else:
                bubble.setFixedWidth(system_width)


def call_ui_chat_model(user_prompt: str, system_prompt: str, temperature: float | None = None) -> str:
    settings = read_ui_settings()
    api_key = resolve_ui_api_key(settings)
    if not api_key:
        raise RuntimeError('未配置 API Key，请先在设置中填写，或配置环境变量。')

    base_url = str(settings.get('model_url', '')).strip() or 'https://api.siliconflow.cn/v1'
    model = str(settings.get('model_name', '')).strip() or 'deepseek-ai/DeepSeek-V3.2'
    url = base_url.rstrip('/') + '/chat/completions'
    payload = {
        'model': model,
        'temperature': float(temperature if temperature is not None else 0.2),
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
    }
    body = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            response_body = response.read().decode('utf-8')
            data = json.loads(response_body)
    except urllib.error.HTTPError as error:
        detail = error.read().decode('utf-8', errors='ignore')
        raise RuntimeError(f'HTTPError {error.code}: {detail}') from error
    except urllib.error.URLError as error:
        raise RuntimeError(f'网络错误: {error}') from error

    choices = data.get('choices') or []
    if not choices:
        raise RuntimeError('模型返回为空。')
    message = choices[0].get('message') or {}
    content = str(message.get('content') or '').strip()
    if not content:
        raise RuntimeError('模型未返回有效文本。')
    return content


class ChatWorker(QThread):
    success = pyqtSignal(str)
    failure = pyqtSignal(str)

    def __init__(self, user_prompt: str, system_prompt: str, parent=None):
        super().__init__(parent)
        self.user_prompt = user_prompt
        self.system_prompt = system_prompt

    def run(self):
        try:
            result = call_ui_chat_model(self.user_prompt, self.system_prompt)
            self.success.emit(result)
        except Exception as exc:
            self.failure.emit(str(exc))


class ControllerStructureCanvas(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(320)
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName('CurveCanvas')
        self.setObjectName('ControllerStructureCanvas')
        self._model = {
            'items': [],
            'mech_props': [],
            'source': '',
        }

    def set_model(self, model: dict):
        self._model = model or {'items': [], 'mech_props': [], 'source': ''}
        self.update()

    @staticmethod
    def _arrow_head(end_x, end_y, direction='down'):
        size = 8
        if direction == 'down':
            return [QPointF(end_x, end_y), QPointF(end_x - size, end_y - size * 1.4), QPointF(end_x + size, end_y - size * 1.4)]
        return [QPointF(end_x, end_y), QPointF(end_x - size * 1.4, end_y - size), QPointF(end_x - size * 1.4, end_y + size)]

    def _draw_arrow(self, painter: QPainter, start: QPointF, end: QPointF):
        painter.setPen(QPen(QColor('#4d4d4d'), 1.6))
        painter.drawLine(start, end)
        if end.y() >= start.y():
            head = self._arrow_head(end.x(), end.y(), 'down')
        else:
            head = self._arrow_head(end.x(), end.y(), 'right')
        painter.setBrush(QColor('#4d4d4d'))
        painter.drawPolygon(QPolygonF(head))

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(10, 10, -10, -10)
        painter.fillRect(rect, QColor('#fcfcfd'))

        painter.setPen(QColor('#303030'))
        painter.drawText(QRectF(rect.left(), rect.top(), rect.width(), 22), Qt.AlignLeft | Qt.AlignVCenter, '控制器结构框图')

        items = self._model.get('items') or []
        if not items:
            painter.setPen(QColor('#7a7a7a'))
            painter.drawText(rect, Qt.AlignCenter, '暂无控制器结构\n请先在“主程序生成”中生成并保存 loop-ids 结果')
            return

        box_w = 176
        box_h = 52
        text_x = rect.left() + box_w + 28
        x = rect.left() + 20
        y = rect.top() + 42
        gap = 26

        box_pen_colors = {
            'current_loop': QColor('#0f62fe'),
            'speed_loop': QColor('#0f7b3a'),
            'position_loop': QColor('#a05a00'),
        }
        fill_colors = {
            'current_loop': QColor('#eef4ff'),
            'speed_loop': QColor('#effaf3'),
            'position_loop': QColor('#fff4e6'),
        }

        # Build layout positions.
        positions = []
        current_item = next((item for item in items if item['kind'] == 'current_loop'), None)
        inner_items = [item for item in items if item['kind'] in {'speed_loop', 'position_loop'}]

        if current_item:
            positions.append((current_item, QRectF(x, y, box_w, box_h)))
            y += box_h + gap + 8

        for inner in inner_items:
            positions.append((inner, QRectF(x, y, box_w, box_h)))
            y += box_h + gap

        # draw arrows between consecutive visible nodes
        for idx in range(len(positions) - 1):
            _, prev_rect = positions[idx]
            _, next_rect = positions[idx + 1]
            start = QPointF(prev_rect.center().x(), prev_rect.bottom())
            end = QPointF(next_rect.center().x(), next_rect.top())
            self._draw_arrow(painter, start, end)

        # mechanical wrapper around speed/position nodes
        if inner_items:
            first_rect = positions[1 if current_item else 0][1]
            last_rect = positions[-1][1]
            wrapper = QRectF(
                first_rect.left() - 10,
                first_rect.top() - 14,
                first_rect.width() + 20,
                (last_rect.bottom() - first_rect.top()) + 28,
            )
            painter.setPen(QPen(QColor('#8c8c8c'), 1.6, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(wrapper, 10, 10)
            painter.setPen(QColor('#666666'))
            mech_props = self._model.get('mech_props') or []
            mech_text = '机械环'
            if mech_props:
                mech_text += f"  ({', '.join(mech_props)})"
            painter.drawText(QRectF(wrapper.left() + 8, wrapper.top() - 12, wrapper.width() - 16, 16), Qt.AlignLeft | Qt.AlignVCenter, mech_text)

        # draw node boxes and property labels
        for item, box in positions:
            kind = item['kind']
            label = item['label']
            props = item.get('properties') or []
            display_props = '，'.join(props) if props else '-'

            painter.setPen(QPen(box_pen_colors.get(kind, QColor('#4d4d4d')), 1.8))
            painter.setBrush(fill_colors.get(kind, QColor('#f2f2f2')))
            painter.drawRoundedRect(box, 8, 8)
            painter.setPen(QColor('#222222'))
            painter.drawText(box.adjusted(10, 0, -10, 0), Qt.AlignCenter, label)

            painter.setPen(QColor('#4d4d4d'))
            prop_rect = QRectF(text_x, box.top() + 10, rect.right() - text_x, box.height() - 20)
            painter.drawText(prop_rect, Qt.AlignLeft | Qt.AlignVCenter, f'属性参数：{display_props}')


class ControllerStructurePanel(QWidget):
    def __init__(self, project_json_getter=None, parent=None):
        super().__init__(parent)
        self.project_json_getter = project_json_getter
        self.canvas = ControllerStructureCanvas()
        self.source_label = QLabel('来源：未加载项目')
        self.source_label.setStyleSheet('color: #666666;')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title_row = QWidget()
        title_layout = QHBoxLayout(title_row)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.addWidget(QLabel('控制器结构'))
        title_layout.addStretch()
        refresh_btn = QPushButton('刷新框图')
        refresh_btn.clicked.connect(self.refresh_from_project)
        title_layout.addWidget(refresh_btn)

        layout.addWidget(title_row)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.source_label)
        self.refresh_from_project()

    def _project_json_path(self):
        if callable(self.project_json_getter):
            return self.project_json_getter()
        return None

    def _load_payload(self):
        project_json = self._project_json_path()
        if not project_json:
            return None, None

        candidates = [project_json]
        candidates.append(project_json.parent / 'controller_loop_ids_generated.json')

        for path in candidates:
            try:
                if not path.exists():
                    continue
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    selected = data.get('selected_loops') or data.get('structured_requirement', {}).get('selected_loops')
                    if isinstance(selected, list) and selected:
                        return data, path
            except Exception:
                continue
        return None, None

    @staticmethod
    def _loop_label(kind: str) -> str:
        return {
            'current_loop': '电流环',
            'speed_loop': '速度环',
            'position_loop': '位置环',
        }.get(kind, kind)

    def _build_model(self, payload: dict | None):
        if not payload:
            return {'items': [], 'mech_props': [], 'source': ''}

        loops = payload.get('selected_loops') or payload.get('structured_requirement', {}).get('selected_loops') or []
        by_name = {str(loop.get('name') or '').strip().lower(): loop for loop in loops if isinstance(loop, dict)}

        mech_loop = by_name.get('mech_loop')
        mech_props = list(mech_loop.get('properties') or []) if mech_loop else []
        mech_target = mech_props[0] if mech_props else ''

        items = []
        current = by_name.get('current_loop')
        if current:
            items.append({
                'kind': 'current_loop',
                'label': self._loop_label('current_loop'),
                'properties': current.get('properties') or [],
            })

        speed = by_name.get('speed_loop')
        position = by_name.get('position_loop')

        if not speed and mech_target == 'speed':
            speed = {'properties': mech_props}
        if not position and mech_target == 'position':
            position = {'properties': mech_props}

        if speed:
            items.append({
                'kind': 'speed_loop',
                'label': self._loop_label('speed_loop'),
                'properties': speed.get('properties') or [],
            })
        if position:
            items.append({
                'kind': 'position_loop',
                'label': self._loop_label('position_loop'),
                'properties': position.get('properties') or [],
            })

        return {
            'items': items,
            'mech_props': mech_props,
            'source': payload.get('_source_path', ''),
        }

    def refresh_from_project(self):
        payload, source_path = self._load_payload()
        if payload and source_path:
            payload = dict(payload)
            payload['_source_path'] = str(source_path)
        model = self._build_model(payload)
        self.canvas.set_model(model)
        if source_path:
            self.source_label.setText(f'来源：{source_path}')
        else:
            self.source_label.setText('来源：未找到 controller_loop_ids_generated.json 或当前项目 JSON 中的 selected_loops')


class CurveCanvas(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.setFrameShape(QFrame.StyledPanel)
        self._points: list[tuple[float, float]] = []
        self._title = '负载曲线'
        self._x_label = '时间'
        self._y_label = '负载值'

    def set_curve(self, points: list[tuple[float, float]], title='负载曲线', x_label='时间', y_label='负载值'):
        self._points = list(points)
        self._title = title
        self._x_label = x_label
        self._y_label = y_label
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(12, 12, -12, -12)
        painter.fillRect(rect, QColor('#fbfbfb'))

        title_rect = QRectF(rect.left(), rect.top(), rect.width(), 24)
        painter.setPen(QColor('#333333'))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, self._title)

        plot_rect = QRectF(rect.left() + 44, rect.top() + 32, rect.width() - 58, rect.height() - 64)
        if plot_rect.width() <= 0 or plot_rect.height() <= 0:
            return

        # grid and axes
        painter.setPen(QPen(QColor('#d8d8d8'), 1))
        for i in range(6):
            y = plot_rect.top() + i * plot_rect.height() / 5.0
            painter.drawLine(int(plot_rect.left()), int(y), int(plot_rect.right()), int(y))
        for i in range(6):
            x = plot_rect.left() + i * plot_rect.width() / 5.0
            painter.drawLine(int(x), int(plot_rect.top()), int(x), int(plot_rect.bottom()))

        painter.setPen(QPen(QColor('#666666'), 1.5))
        painter.drawLine(int(plot_rect.left()), int(plot_rect.bottom()), int(plot_rect.right()), int(plot_rect.bottom()))
        painter.drawLine(int(plot_rect.left()), int(plot_rect.top()), int(plot_rect.left()), int(plot_rect.bottom()))

        painter.setPen(QColor('#666666'))
        painter.drawText(QRectF(rect.left(), plot_rect.top() - 18, 38, 18), Qt.AlignRight | Qt.AlignVCenter, self._y_label)
        painter.drawText(QRectF(plot_rect.left(), rect.bottom() - 18, plot_rect.width(), 18), Qt.AlignCenter, self._x_label)

        if len(self._points) < 2:
            painter.setPen(QColor('#888888'))
            painter.drawText(plot_rect, Qt.AlignCenter, '暂无可绘制数据\n请在下方列表输入两列数值')
            return

        xs = [p[0] for p in self._points]
        ys = [p[1] for p in self._points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        if abs(max_x - min_x) < 1e-9:
            max_x = min_x + 1.0
        if abs(max_y - min_y) < 1e-9:
            max_y = min_y + 1.0

        num_ticks = 6
        painter.setPen(QColor('#666666'))
        f = painter.font()
        f.setPointSize(8)
        painter.setFont(f)

        for i in range(num_ticks):
            tval = min_x + i * (max_x - min_x) / (num_ticks - 1)
            tx = plot_rect.left() + (tval - min_x) / (max_x - min_x) * plot_rect.width()
            painter.drawLine(int(tx), int(plot_rect.bottom()), int(tx), int(plot_rect.bottom() + 6))
            txt = ('%g' % (round(tval, 6)))
            painter.drawText(QRectF(tx - 36, plot_rect.bottom() + 6, 72, 16), Qt.AlignCenter, txt)

        for i in range(num_ticks):
            yval = min_y + i * (max_y - min_y) / (num_ticks - 1)
            y_ratio = (yval - min_y) / (max_y - min_y)
            py = plot_rect.bottom() - y_ratio * plot_rect.height()
            painter.drawLine(int(plot_rect.left() - 6), int(py), int(plot_rect.left()), int(py))
            ytxt = ('%g' % (round(yval, 6)))
            painter.drawText(QRectF(rect.left(), py - 8, 40, 16), Qt.AlignRight | Qt.AlignVCenter, ytxt)

        def map_point(x_val, y_val):
            x_ratio = (x_val - min_x) / (max_x - min_x)
            y_ratio = (y_val - min_y) / (max_y - min_y)
            px = plot_rect.left() + x_ratio * plot_rect.width()
            py = plot_rect.bottom() - y_ratio * plot_rect.height()
            return QPointF(px, py)

        poly = QPolygonF([map_point(x, y) for x, y in self._points])
        painter.setPen(QPen(QColor('#0f62fe'), 2.2))
        painter.drawPolyline(poly)

        painter.setPen(QPen(QColor('#0f62fe'), 1.2))
        painter.setBrush(QColor('#ffffff'))
        for point in poly:
            painter.drawEllipse(point, 3.8, 3.8)

        painter.setPen(QColor('#444444'))
        painter.drawText(QRectF(plot_rect.right() - 140, plot_rect.top() + 6, 140, 18), Qt.AlignRight, f'点数: {len(self._points)}')


class MainProgramPanel(QWidget):
    def __init__(self, project_json_getter=None, structure_refresh_callback=None, parent=None):
        super().__init__(parent)
        self.current_requirement = ''
        self.chat_worker = None
        self.project_json_getter = project_json_getter
        self.structure_refresh_callback = structure_refresh_callback
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.chat_view = ChatStreamWidget()
        self._append_chat('system', '请输入需求，后续可结合设置中的大模型 API 进行完善。')

        input_row = QWidget()
        input_layout = QHBoxLayout(input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(10)

        self.input_edit = ChatInputEdit()
        self.input_edit.setPlaceholderText('请输入需求描述...')
        self.input_edit.setFixedHeight(96)
        self.input_edit.enterPressed.connect(self.send_requirement)

        input_actions = QWidget()
        input_actions_layout = QVBoxLayout(input_actions)
        input_actions_layout.setContentsMargins(0, 0, 0, 0)
        input_actions_layout.setSpacing(8)
        self.send_btn = QPushButton('发送需求')
        self.send_btn.setObjectName('primaryButton')
        self.send_btn.setStyleSheet(
            'QPushButton{background:#0f62fe;color:#ffffff;border:none;font-weight:600;}'
            'QPushButton:hover{background:#0a55df;}'
            'QPushButton:pressed{background:#0848c7;}'
            'QPushButton:disabled{background:#9abafc;color:#f8fbff;}'
        )
        self.send_btn.clicked.connect(self.send_requirement)
        self.clear_btn = QPushButton('清空')
        self.clear_btn.setObjectName('ghostButton')
        self.clear_btn.clicked.connect(self.clear_input)
        input_actions_layout.addWidget(self.send_btn)
        input_actions_layout.addWidget(self.clear_btn)
        input_actions_layout.addStretch()

        input_layout.addWidget(self.input_edit, 1)
        input_layout.addWidget(input_actions)

        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        action_layout.addStretch()
        self.run_btn = QPushButton('生成程序')
        self.run_btn.setObjectName('secondaryActionButton')
        self.run_btn.clicked.connect(self.generate_program)
        action_layout.addWidget(self.run_btn)

        self.status_label = QLabel('状态：等待输入需求')

        layout.addWidget(QLabel('主程序生成'))
        layout.addWidget(self.chat_view, 1)
        layout.addWidget(input_row)
        layout.addWidget(action_row)
        layout.addWidget(self.status_label)

    def clear_input(self):
        self.input_edit.clear()

    def _append_chat(self, role: str, text: str):
        self.chat_view.append_message(role, text)

    def send_requirement(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        if self.chat_worker is not None and self.chat_worker.isRunning():
            self._append_chat('system', '正在等待上一条对话返回，请稍后。')
            return

        self.current_requirement = text
        self._append_chat('user', text)
        self._append_chat('system', '正在调用大模型完善需求...')
        self.status_label.setText('状态：对话处理中...')
        self.send_btn.setEnabled(False)

        self.chat_worker = ChatWorker(
            text,
            (
                '你是面向 loop-ids 生成系统的控制器需求完善助手。'
                '你的任务是把用户原始需求改写为可直接用于控制环路选择与程序生成的中文需求。'
                '重点聚焦以下内容：'
                '1) 明确电流环（current_loop）目标、约束、动态响应与可测量量；'
                '2) 明确机械环（mech_loop）控制目标与结构层级（速度或位置）；'
                '3) 明确机械环控制方法（pid/mit/smc）及其选择依据；'
                '4) 明确内外环关系、必要信号链路与关键性能指标。'
                '输出要求：仅输出“完善后的需求文本”，不输出代码块、不输出额外解释。'
            ),
            self,
        )
        self.chat_worker.success.connect(self.on_chat_success)
        self.chat_worker.failure.connect(self.on_chat_failure)
        self.chat_worker.finished.connect(self.on_chat_finished)
        self.chat_worker.start()
        self.input_edit.clear()

    def _project_json_path(self):
        if callable(self.project_json_getter):
            return self.project_json_getter()
        return None

    def _update_project_json_requirement(self, requirement_text: str):
        project_json = self._project_json_path()
        if not project_json:
            return
        try:
            with open(project_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
            data['objective_text'] = requirement_text
            with open(project_json, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._append_chat('system', f'已写入需求到项目文件 {project_json.name}')
        except Exception as exc:
            self._append_chat('system', f'写入项目 JSON 失败：{exc}')

    def _update_project_json_selected_loops(self, loop_ids_path: Path):
        project_json = self._project_json_path()
        if not project_json:
            return
        try:
            with open(loop_ids_path, 'r', encoding='utf-8') as f:
                loops_payload = json.load(f)
            if not isinstance(loops_payload, dict):
                return

            with open(project_json, 'r', encoding='utf-8') as f:
                project_data = json.load(f)
            if not isinstance(project_data, dict):
                project_data = {}

            if 'structured_requirement' not in project_data:
                project_data['structured_requirement'] = {}
            project_data['structured_requirement']['selected_loops'] = loops_payload.get('selected_loops') or []
            project_data['generated_loop_ids_path'] = str(loop_ids_path)

            with open(project_json, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, ensure_ascii=False, indent=2)
            self._append_chat('system', f'已写入主程序结构到项目文件 {project_json.name}')
        except Exception as exc:
            self._append_chat('system', f'写入主程序结构失败：{exc}')

    def on_chat_success(self, reply: str):
        self._append_chat('model', reply)
        self.current_requirement = reply
        self._update_project_json_requirement(reply)
        self.status_label.setText('状态：需求已完善，可点击“生成程序”')

    def on_chat_failure(self, error_text: str):
        self._append_chat('system', f'对话失败：{error_text}')
        self.status_label.setText('状态：对话失败，请检查设置与网络')

    def on_chat_finished(self):
        self.send_btn.setEnabled(True)

    def generate_program(self):
        if not self.current_requirement:
            self._append_chat('system', '请先输入并发送需求，再执行生成。')
            self.status_label.setText('状态：缺少需求')
            return

        script_path = Path(__file__).resolve().parent.parent / 'run_llm_to_program.py'
        project_json = self._project_json_path()
        output_root = project_json.parent if project_json else script_path.parent
        loop_ids_output = output_root / 'controller_loop_ids_generated.json'
        c_output = output_root / 'ctl_main.c'
        h_output = output_root / 'ctl_main.h'
        paras_output = output_root / 'paras.generated.h'
        llm_config = script_path.parent / 'llm_settings.json'
        project_src_dir = (project_json.parent / 'src') if project_json else None

        self.status_label.setText('状态：正在生成程序...')
        self._append_chat('system', '开始生成控制器程序（复用交互界面同一大模型调用）。')
        self._append_chat('system', f'输出目录 {output_root}')

        try:
            self._append_chat('system', '[1/2] 生成 loop-ids...')
            loop_exporter.export_json(
                output_path=loop_ids_output,
                requirement=self.current_requirement,
                settings_path=llm_config,
                chat_text_caller=lambda system_prompt, user_prompt, temp: call_ui_chat_model(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    temperature=temp,
                ),
            )
            self._append_chat('system', f'loop-ids 已生成：{loop_ids_output.name}')

            self._append_chat('system', '[2/2] 生成 ctl_main 与 paras 代码文件...')
            merger.main(
                loop_ids_path=loop_ids_output,
                template_path=script_path.parent.joinpath('Example', 'ctl_main.c'),
                output_path=c_output,
                header_template_path=script_path.parent.joinpath('Example', 'ctl_main.h'),
                header_output_path=h_output,
                paras_template_path=script_path.parent.joinpath('Example', 'paras.h'),
                paras_output_path=paras_output,
            )

            if project_src_dir is not None:
                project_src_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(c_output, project_src_dir / c_output.name)
                shutil.copy2(h_output, project_src_dir / h_output.name)
                shutil.copy2(paras_output, project_src_dir / paras_output.name)
                self._append_chat('system', f'已覆盖拷贝到项目源码目录：{project_src_dir}')

            self.status_label.setText('状态：生成完成')
            self._append_chat('system', '控制器程序生成完成。')
            self._update_project_json_selected_loops(loop_ids_output)
            if callable(self.structure_refresh_callback):
                self.structure_refresh_callback()
        except Exception as exc:
            self.status_label.setText('状态：调用失败')
            self._append_chat('system', f'生成过程中发生异常：{exc}')


class LoadCurvePanel(QWidget):
    def __init__(self, project_json_getter=None, parent=None):
        super().__init__(parent)
        self.project_json_getter = project_json_getter
        self._updating_table = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.chart_canvas = CurveCanvas()
        self.chart_hint = QLabel('说明：在下方输入两列数值后，曲线会自动更新。')
        self.chart_hint.setStyleSheet('color: #666;')

        self.table = QTableWidget(1, 2)
        self.table.setHorizontalHeaderLabels(['时间', '负载值'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.table.itemChanged.connect(self.ensure_trailing_row)

        layout.addWidget(QLabel('负载曲线设置'))
        layout.addWidget(self.chart_canvas, 2)
        layout.addWidget(self.chart_hint)
        layout.addWidget(self.table, 1)

        # bottom row with save button aligned to bottom-right of the table
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()
        self.save_btn = QPushButton('保存')
        self.save_btn.setObjectName('secondaryActionButton')
        self.save_btn.clicked.connect(self.save_to_csv)
        btn_layout.addWidget(self.save_btn)
        layout.addWidget(btn_row)

    def ensure_trailing_row(self, item):
        if self._updating_table:
            return
        if self.table.rowCount() == 0:
            self.table.insertRow(0)
        last_row = self.table.rowCount() - 1
        points = self.collect_points()
        self.chart_canvas.set_curve(points, title='负载曲线', x_label='时间', y_label='负载值')

        if item.row() != last_row:
            return

        row_has_data = False
        for col in range(self.table.columnCount()):
            cell = self.table.item(last_row, col)
            if cell and cell.text().strip():
                row_has_data = True
                break

        if row_has_data:
            self._updating_table = True
            try:
                self.table.blockSignals(True)
                self.table.insertRow(self.table.rowCount())
            finally:
                self.table.blockSignals(False)
                self._updating_table = False

    def collect_points(self):
        points = []
        for row in range(self.table.rowCount()):
            x_item = self.table.item(row, 0)
            y_item = self.table.item(row, 1)
            if not x_item or not y_item:
                continue
            x_text = x_item.text().strip()
            y_text = y_item.text().strip()
            if not x_text or not y_text:
                continue
            try:
                x_val = float(x_text)
                y_val = float(y_text)
            except ValueError:
                continue
            points.append((x_val, y_val))
        return points

    def _project_folder(self):
        if callable(self.project_json_getter):
            pj = self.project_json_getter()
            if pj:
                try:
                    return Path(pj).parent
                except Exception:
                    pass
        # fallback to app root
        return Path(__file__).resolve().parent.parent

    def save_to_csv(self):
        points = self.collect_points()
        if not points:
            QMessageBox.warning(self, '提示', '没有可保存的数据。')
            return
        out_dir = self._project_folder()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / 'load.csv'
        try:
            with open(out_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                for x, y in points:
                    writer.writerow([x, y])
            QMessageBox.information(self, '完成', f'已保存：{out_path}')
        except Exception as exc:
            QMessageBox.critical(self, '错误', f'保存失败：{exc}')


class RequirementPanel(QWidget):
    def __init__(self, project_json_getter=None, parent=None):
        super().__init__(parent)
        self.chat_worker = None
        self.project_json_getter = project_json_getter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.chat_view = ChatStreamWidget()
        self._append_chat('system', '请输入需求指标。')

        self.input_edit = ChatInputEdit()
        self.input_edit.setPlaceholderText('请输入需求指标描述...')
        self.input_edit.setFixedHeight(110)
        self.input_edit.enterPressed.connect(self.send_requirement)

        self.send_btn = QPushButton('发送需求')
        self.send_btn.setObjectName('primaryButton')
        self.send_btn.setStyleSheet(
            'QPushButton{background:#0f62fe;color:#ffffff;border:none;font-weight:600;}'
            'QPushButton:hover{background:#0a55df;}'
            'QPushButton:pressed{background:#0848c7;}'
            'QPushButton:disabled{background:#9abafc;color:#f8fbff;}'
        )
        self.send_btn.clicked.connect(self.send_requirement)

        self.clear_btn = QPushButton('清空')
        self.clear_btn.setObjectName('ghostButton')
        self.clear_btn.clicked.connect(self.input_edit.clear)

        self.status_label = QLabel('状态：等待输入需求指标')

        input_bar = QWidget()
        input_bar_layout = QHBoxLayout(input_bar)
        input_bar_layout.setContentsMargins(0, 0, 0, 0)
        input_bar_layout.setSpacing(10)
        input_bar_layout.addWidget(self.input_edit, 1)

        side_actions = QWidget()
        side_actions_layout = QVBoxLayout(side_actions)
        side_actions_layout.setContentsMargins(0, 0, 0, 0)
        side_actions_layout.setSpacing(8)
        side_actions_layout.addWidget(self.send_btn)
        side_actions_layout.addWidget(self.clear_btn)
        side_actions_layout.addStretch()
        input_bar_layout.addWidget(side_actions)

        layout.addWidget(QLabel('需求指标设置'))
        layout.addWidget(self.chat_view, 1)
        layout.addWidget(input_bar)
        layout.addWidget(self.status_label)

    def _append_chat(self, role: str, text: str):
        self.chat_view.append_message(role, text)

    def send_requirement(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        if self.chat_worker is not None and self.chat_worker.isRunning():
            self._append_chat('system', '正在等待上一条对话返回，请稍后。')
            return

        self._append_chat('user', text)
        self._append_chat('system', '正在调用大模型完善需求指标...')
        self.status_label.setText('状态：对话处理中...')
        self.send_btn.setEnabled(False)

        self.chat_worker = ChatWorker(
            text,
            (
                '你是面向 loop-ids 生成系统的需求指标完善助手。'
                '你的任务是把用户输入改写为可执行、可测量、适合控制器设计验证的中文需求指标。'
                '重点聚焦：'
                '1) 性能指标必须明确、可量化、可验证；'
                '2) 与电流环、机械环、速度/位置控制目标相关的约束需要具体；'
                '3) 输出应适合后续进入控制器程序生成流程；'
                '4) 保持中文简洁表达，不输出分析过程。'
                '输出要求：仅输出完善后的需求指标文本。'
            ),
            self,
        )
        self.chat_worker.success.connect(self.on_chat_success)
        self.chat_worker.failure.connect(self.on_chat_failure)
        self.chat_worker.finished.connect(self.on_chat_finished)
        self.chat_worker.start()
        self.input_edit.clear()

    def _project_json_path(self):
        if callable(self.project_json_getter):
            return self.project_json_getter()
        return None

    def _write_requirement_to_project_json(self, requirement_text: str):
        project_json = self._project_json_path()
        if not project_json:
            return
        try:
            with open(project_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
            if 'structured_requirement' not in data:
                data['structured_requirement'] = {}
            data['structured_requirement']['performance_requirements'] = requirement_text
            with open(project_json, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._append_chat('system', f'已写入需求指标到项目文件 {project_json.name}')
        except Exception as exc:
            self._append_chat('system', f'写入项目 JSON 失败：{exc}')

    def on_chat_success(self, reply: str):
        self._append_chat('model', reply)
        self._write_requirement_to_project_json(reply)
        self.status_label.setText('状态：需求指标已完善')

    def on_chat_failure(self, error_text: str):
        self._append_chat('system', f'对话失败：{error_text}')
        self.status_label.setText('状态：对话失败，请检查设置与网络')

    def on_chat_finished(self):
        self.send_btn.setEnabled(True)


class Design3RightPanel(QWidget):
    def __init__(self, project_json_getter=None, parent=None):
        super().__init__(parent)
        self.controller_panel = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.tabs = QTabWidget()
        self.main_program_panel = MainProgramPanel(
            project_json_getter=project_json_getter,
            structure_refresh_callback=self.refresh_structure,
        )
        self.tabs.addTab(self.main_program_panel, '主程序生成')
        self.tabs.addTab(LoadCurvePanel(project_json_getter=project_json_getter), '负载曲线设置')
        self.tabs.addTab(RequirementPanel(project_json_getter=project_json_getter), '需求指标设置')

        layout.addWidget(self.tabs)

    def set_controller_panel(self, controller_panel):
        self.controller_panel = controller_panel

    def refresh_structure(self):
        if self.controller_panel is not None:
            self.controller_panel.refresh_from_project()


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_project_json_path = None
        self.setWindowTitle('GMP Generator Engine - UI')
        self.resize(1000, 600)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # Top toolbar (horizontal)
        toolbar = QWidget()
        toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(4, 4, 4, 4)
        toolbar_layout.setSpacing(6)

        file_menu = QMenu('文件', self)
        self.action_new = QAction('新建', self)
        self.action_save = QAction('保存', self)
        self.action_load = QAction('读取', self)
        self.action_settings = QAction('设置', self)
        file_menu.addAction(self.action_new)
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_load)
        file_menu.addAction(self.action_settings)
        self.action_new.triggered.connect(self.open_new_project_dialog)
        self.action_load.triggered.connect(self.open_project_json)
        self.action_save.triggered.connect(self.save_project_json)
        self.action_settings.triggered.connect(self.open_settings_dialog)

        file_button = QToolButton()
        file_button.setText('文件')
        file_button.setPopupMode(QToolButton.InstantPopup)
        file_button.setMenu(file_menu)
        toolbar_layout.addWidget(file_button)

        toolbar_layout.addStretch()
        toolbar.setFixedHeight(48)

        # Central area: left (1/3) and right (2/3)
        central = QSplitter(Qt.Horizontal)
        central.setChildrenCollapsible(False)

        self.left_controller_panel = ControllerStructurePanel(project_json_getter=self.get_current_project_json_path)
        self.left_controller_panel.setStyleSheet('background: #f0f0f0; border: 1px solid #ddd;')

        self.right_panel_widget = Design3RightPanel(project_json_getter=self.get_current_project_json_path)
        self.right_panel_widget.setStyleSheet('background: #ffffff; border: 1px solid #ddd;')
        self.right_panel_widget.set_controller_panel(self.left_controller_panel)

        central.addWidget(self.left_controller_panel)
        central.addWidget(self.right_panel_widget)
        central.setStretchFactor(0, 1)
        central.setStretchFactor(1, 2)

        # Bottom information bar (horizontal)
        self.info_widget = QWidget()
        self.info_widget.setObjectName('panelCard')
        info_layout = QHBoxLayout(self.info_widget)
        info_layout.setContentsMargins(6, 6, 6, 6)
        info_layout.setSpacing(6)
        info_label = QLabel('Status: Ready')
        info_label.setStyleSheet('color: #475467; font-weight: 600;')
        info_layout.addWidget(info_label)
        info_layout.addStretch()
        user_label = QLabel('User: Guest')
        user_label.setStyleSheet('color: #475467;')
        info_layout.addWidget(user_label)
        self.info_widget.setFixedHeight(34)
        self.info_widget.setStyleSheet('background: #f7f9fc;')

        # Assemble main layout
        main_layout.addWidget(toolbar)
        main_layout.addWidget(central)
        main_layout.addWidget(self.info_widget)

        self.setCentralWidget(container)
        self._apply_visual_theme()
        self._install_surface_effects()

    def _apply_visual_theme(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background: #eef2f7;
            }
            QWidget {
                color: #1f2937;
                font-family: Segoe UI, Microsoft YaHei, Arial;
                font-size: 10pt;
            }
            QLabel {
                color: #1f2937;
            }
            QFrame#ControllerStructureCanvas,
            QFrame#CurveCanvas,
            QTextEdit,
            QTableWidget,
            QTabWidget::pane,
            QMenu,
            QDialog,
            QWidget#panelCard {
                background: #ffffff;
                border: 1px solid #d9e2ec;
                border-radius: 14px;
            }
            QFrame#chatBubble_user {
                background: #0f62fe;
                color: #ffffff;
                border: none;
                border-top-left-radius: 18px;
                border-top-right-radius: 18px;
                border-bottom-left-radius: 18px;
                border-bottom-right-radius: 4px;
            }
            QFrame#chatBubble_model {
                background: #ffffff;
                color: #1f2937;
                border: 1px solid #d9e2ec;
                border-top-left-radius: 18px;
                border-top-right-radius: 18px;
                border-bottom-left-radius: 4px;
                border-bottom-right-radius: 18px;
            }
            QFrame#systemBubble {
                background: #eef2f7;
                color: #64748b;
                border: 1px solid #d9e2ec;
                border-radius: 999px;
            }
            QLabel#chatBubbleTitle {
                font-size: 9pt;
                font-weight: 700;
                color: rgba(255,255,255,0.90);
            }
            QFrame#chatBubble_user QLabel#chatBubbleTitle,
            QFrame#chatBubble_user QLabel#chatBubbleBody {
                color: #ffffff;
            }
            QFrame#chatBubble_model QLabel#chatBubbleTitle {
                color: #0f62fe;
            }
            QFrame#chatBubble_model QLabel#chatBubbleBody {
                color: #1f2937;
            }
            QFrame#systemBubble QLabel#chatBubbleTitle {
                color: #64748b;
            }
            QFrame#systemBubble QLabel#chatBubbleBody {
                color: #64748b;
            }
            QLabel#chatBubbleBody {
                font-size: 10pt;
                line-height: 1.55;
            }
            QTabWidget::pane {
                padding: 6px;
            }
            QTabBar::tab {
                background: #e9eef5;
                color: #344054;
                border: 1px solid #cfd8e3;
                border-bottom: none;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                min-width: 120px;
                padding: 8px 14px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #0f62fe;
                font-weight: 600;
            }
            QTabBar::tab:hover {
                background: #f6f8fc;
            }
            QPushButton {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cfd8e3;
                border-radius: 10px;
                padding: 7px 14px;
                min-height: 18px;
            }
            QPushButton:hover {
                background: #f3f7ff;
                border-color: #7da7ff;
            }
            QPushButton:pressed {
                background: #dce8ff;
            }
            QPushButton#primaryButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0f62fe, stop:1 #1d7bff);
                color: white;
                border: none;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0a55df, stop:1 #1769dd);
            }
            QPushButton#ghostButton,
            QPushButton#secondaryActionButton {
                background: #f8fafc;
                color: #344054;
                border: 1px solid #d6deea;
                font-weight: 600;
            }
            QPushButton#secondaryActionButton {
                min-width: 112px;
            }
            QPushButton#ghostButton:hover,
            QPushButton#secondaryActionButton:hover {
                background: #eef4ff;
                border-color: #9fb7ff;
            }
            QToolButton {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cfd8e3;
                border-radius: 10px;
                padding: 7px 14px;
            }
            QToolButton:hover {
                background: #f3f7ff;
                border-color: #7da7ff;
            }
            QTextEdit {
                padding: 10px;
                selection-background-color: #dbeafe;
                line-height: 1.4;
            }
            QTableWidget {
                gridline-color: #e1e8f0;
                selection-background-color: #dbeafe;
                selection-color: #111827;
            }
            QHeaderView::section {
                background: #f2f6fb;
                color: #344054;
                border: none;
                border-bottom: 1px solid #d9e2ec;
                padding: 8px 10px;
                font-weight: 600;
            }
            QMenu {
                border: 1px solid #d9e2ec;
                padding: 6px;
            }
            QMenu::item {
                padding: 8px 24px 8px 18px;
                border-radius: 8px;
                margin: 2px 0;
            }
            QMenu::item:selected {
                background: #eaf1ff;
                color: #0f62fe;
            }
            QDialog {
                background: #f7f9fc;
            }
            """
        )

    def _install_surface_effects(self):
        for widget in [self.left_controller_panel, self.right_panel(), self.info_bar()]:
            effect = QGraphicsDropShadowEffect(widget)
            effect.setBlurRadius(26)
            effect.setXOffset(0)
            effect.setYOffset(6)
            effect.setColor(QColor(31, 41, 55, 38))
            widget.setGraphicsEffect(effect)

    def right_panel(self):
        return getattr(self, 'right_panel_widget', None)

    def info_bar(self):
        return getattr(self, 'info_widget', None)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        dialog.exec_()

    def open_new_project_dialog(self):
        config_path = Path(__file__).parent / 'config.json'
        dialog = NewProjectDialog(config_path, self)
        if dialog.exec_() == QDialog.Accepted and dialog.project_json_path:
            self.current_project_json_path = Path(dialog.project_json_path)
            QMessageBox.information(self, '已加载项目', f'当前项目：{self.current_project_json_path}')
            self.left_controller_panel.refresh_from_project()

    def get_current_project_json_path(self):
        return self.current_project_json_path

    def open_project_json(self):
        file_path, _ = QFileDialog.getOpenFileName(self, '选择项目 JSON 文件', '', 'JSON Files (*.json)')
        if not file_path:
            return
        selected = Path(file_path)
        try:
            with open(selected, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError('JSON 顶层必须是对象')
            self.current_project_json_path = selected
            QMessageBox.information(self, '已加载项目', f'当前项目：{self.current_project_json_path}')
            self.left_controller_panel.refresh_from_project()
        except Exception as exc:
            QMessageBox.critical(self, '错误', f'加载项目 JSON 失败：{exc}')

    def save_project_json(self):
        if not self.current_project_json_path:
            QMessageBox.warning(self, '提示', '请先新建或读取项目 JSON。')
            return
        try:
            with open(self.current_project_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            with open(self.current_project_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, '完成', f'已保存：{self.current_project_json_path}')
        except Exception as exc:
            QMessageBox.critical(self, '错误', f'保存项目 JSON 失败：{exc}')
