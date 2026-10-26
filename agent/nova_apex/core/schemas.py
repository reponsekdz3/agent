from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class ActionDomain(str, Enum):
    BROWSER = "browser"
    DESKTOP = "desktop"
    MOBILE = "mobile"
    SHELL = "shell"
    FILESYSTEM = "filesystem"
    MEMORY = "memory"
    SYSTEM = "system"

class ActionType(str, Enum):
    # Browser
    NAVIGATE = "navigate"
    CLICK_ELEMENT = "click_element"
    TYPE_ELEMENT = "type_element"
    EXTRACT_CONTENT = "extract_content"
    BROWSER_SCREENSHOT = "browser_screenshot"
    SUBMIT_FORM = "submit_form"
    CREATE_ACCOUNT = "create_account"
    SOLVE_CAPTCHA_PROMPT = "solve_captcha_prompt"
    EVALUATE_JS = "evaluate_js"
    SWITCH_TAB = "switch_tab"
    CLOSE_BROWSER = "close_browser"

    # Desktop
    DESKTOP_CLICK = "desktop_click"
    DESKTOP_DOUBLE_CLICK = "desktop_double_click"
    DESKTOP_DRAG = "desktop_drag"
    DESKTOP_SCROLL = "desktop_scroll"
    DESKTOP_TYPE = "desktop_type"
    DESKTOP_HOTKEY = "desktop_hotkey"
    DESKTOP_SCREENSHOT = "desktop_screenshot"
    FOCUS_WINDOW = "focus_window"
    CLIPBOARD_READ = "clipboard_read"
    CLIPBOARD_WRITE = "clipboard_write"
    RAW_KEYSTROKE = "raw_keystroke"
    DIRECT_WINDOW_MESSAGE = "direct_window_message"
    ENUMERATE_HARDWARE = "enumerate_hardware"
    LAUNCH_APP = "launch_app"
    KILL_PROCESS = "kill_process"

    # Filesystem
    CREATE_FILE = "create_file"
    WRITE_FILE = "write_file"
    READ_FILE = "read_file"
    DELETE_FILE = "delete_file"
    CREATE_FOLDER = "create_folder"
    LIST_DIRECTORY = "list_directory"
    SEARCH_FILES = "search_files"

    # Mobile (ADB)
    ADB_TAP = "adb_tap"
    ADB_SWIPE = "adb_swipe"
    ADB_INPUT_TEXT = "adb_input_text"
    ADB_KEYEVENT = "adb_keyevent"
    ADB_EXTRACT_OTP = "adb_extract_otp"
    ADB_SCREENSHOT = "adb_screenshot"
    ADB_DUMP_HIERARCHY = "adb_dump_hierarchy"
    ADB_LAUNCH_PACKAGE = "adb_launch_package"
    ADB_INSTALL_APK = "adb_install_apk"

    # Shell
    EXECUTE_SHELL = "execute_shell"

    # Flow Control
    WAIT = "wait"
    ASK_HUMAN = "ask_human"
    COMPLETE = "complete"
    FAIL = "fail"

class ActionRequest(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    domain: ActionDomain
    action_type: ActionType
    description: str
    target: Optional[str] = None  # Selector, file path, URL, or coordinate "x,y"
    value: Optional[str] = None   # Text to type, code to run, URL to navigate
    params: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = 30.0

class StepResult(BaseModel):
    action_id: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

class PlanStep(BaseModel):
    step_id: int
    title: str
    description: str
    domain: ActionDomain
    action_type: ActionType
    suggested_action: ActionRequest
    status: StepStatus = StepStatus.PENDING
    result: Optional[StepResult] = None
    retries_left: int = 3

class GoalStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    PAUSED = "paused"
    WAITING_HUMAN = "waiting_human"
    SUCCESS = "success"
    FAILED = "failed"

class AgentGoal(BaseModel):
    goal_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    prompt: str
    status: GoalStatus = GoalStatus.IDLE
    steps: List[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    summary: Optional[str] = None

class Observation(BaseModel):
    domain: ActionDomain
    screenshot_path: Optional[str] = None
    visual_description: Optional[str] = None
    active_window_title: Optional[str] = None
    current_url: Optional[str] = None
    dom_summary: Optional[str] = None
    terminal_output: Optional[str] = None
    device_connected: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)
