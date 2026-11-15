"""Local stdio MCP server for RGB MoCap preview sessions."""

from __future__ import annotations

import base64
import binascii
import json
import math
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
MAX_REQUEST = 64 * 1024
MAX_REPLY = 16 * 1024 * 1024
MAX_IMAGE = 6 * 1024 * 1024
GUI_TIMEOUT = 75
BONE_TIMEOUT = 210
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
VIEWS = ("viewport", "workspace", "video")


def tool(name, description, properties=None, required=()):
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties or {},
            "required": list(required),
            "additionalProperties": False,
        },
    }


FRAME = {
    "type": "integer",
    "minimum": 1,
    "maximum": 2147483647,
    "description": "One-based frame number on the RGB MoCap timeline.",
}
EXPORT_PATH = {
    "type": "string",
    "maxLength": 4096,
    "description": "Absolute local .fbx destination in an existing folder. The file must not exist.",
}
TOOLS = (
    tool("get_status", "Read the dedicated RGB MoCap preview session's project and frame status. "
         "The first valid tool call starts the session; close any other RGB MoCap window first."),
    tool("open_project", "Open a saved RGB MoCap project in the preview session.",
         {"project_path": {"type": "string", "maxLength": 4096,
                           "description": "Absolute local project folder or project.json path."}},
         ("project_path",)),
    tool("seek_frame", "Pause and seek to a frame of the open project.",
         {"frame": FRAME}, ("frame",)),
    tool("select_frame_range", "Highlight an inclusive frame range on the Timeline for FBX export. "
         "Omit both boundaries to clear the selection. Pass the same boundaries to export_fbx to export it.",
         {"frame_start": FRAME, "frame_end": FRAME}),
    tool("capture_view", "Return a PNG of the current 3D viewport, workspace, or source video.",
         {"view": {"type": "string", "enum": list(VIEWS), "default": "viewport"}}),
    tool("compare_motion", "Return before and after correction PNGs at the same frame. "
         "Requires both saved results for the current person and motion result.",
         {"frame": FRAME}, ("frame",)),
    tool("export_fbx", "Export the active saved source motion or a retargeted character as an FBX. "
         "Pass both frame boundaries to export an inclusive range, or omit both to export all frames.",
         {"output_path": EXPORT_PATH, "frame_start": FRAME, "frame_end": FRAME,
          "character_name": {"type": "string", "minLength": 1, "maxLength": 255,
                             "description": "Exact People panel name of a saved retargeted character. "
                                            "Omit both character selectors to export the active source person."},
          "character_id": {"type": "string", "minLength": 1, "maxLength": 255,
                           "description": "Character ID from get_status. Use this when names repeat."}},
         ("output_path",)),
)
ACTIONS = {
    "get_status": "status",
    "open_project": "open_project",
    "seek_frame": "seek_frame",
    "select_frame_range": "select_frame_range",
    "capture_view": "capture_view",
    "compare_motion": "compare_motion",
    "export_fbx": "export_fbx",
}

# Bone frames are local to the selected character take, independently of the
# source video's frame rate, trim offset and the main Timeline.
TAKE_FRAME = dict(FRAME, description="One-based frame number within the selected take.")
BONE_NAME = {"type": "string", "minLength": 1, "maxLength": 255,
             "description": "Exact bone name returned by list_bones."}
BONE_TARGET = {
    "character_id": {"type": "string", "minLength": 1, "maxLength": 128,
                     "description": "ID from bone_editor_status, including source:1 for Person 1 when present. Mutating bones requires a retargeted character."},
    "take_index": {"type": "integer", "minimum": 0, "maximum": 2147483647,
                   "description": "Zero-based character take index; defaults to the editor's current take."},
}
VECTOR3 = {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "number"}}
BONE_OFFSET = {
    "translation": dict(VECTOR3, description="Translation offset [X,Y,Z] in metres. Defaults to zero."),
    "rotation": dict(VECTOR3, description="Rotation offset [X,Y,Z] in XYZ Euler degrees. Defaults to zero."),
    "space": {"type": "string", "enum": ["local", "world"], "default": "local",
              "description": "Offset axes. World uses the character scene axes; rotation pivots at the bone."},
}
BONE_TOOLS = (
    tool("bone_editor_status", "Read the Bone Editor's selected character, take, bone, layer and history state."),
    tool("list_bones", "List bones and parents for a source person or a retargeted character. Prepares the full-bone character cache "
         "when needed; does not run motion inference.",
         {**BONE_TARGET, "prepare": {"type": "boolean", "default": True}}),
    tool("select_bone", "Select and highlight a character bone in the Bone Editor and viewport.",
         {**BONE_TARGET, "bone": BONE_NAME}, ("bone",)),
    tool("get_bone_pose", "Read a source bone's pose, or a character bone's base and edited poses and offset, at a take-local frame.",
         {**BONE_TARGET, "bone": BONE_NAME, "frame": TAKE_FRAME}),
    tool("set_bone_keyframe", "Add or replace an offset keyframe on a character bone. "
         "The original captured and retargeted motion remains unchanged.",
         {**BONE_TARGET, **BONE_OFFSET, "bone": BONE_NAME, "frame": TAKE_FRAME}, ("bone", "frame")),
    tool("delete_bone_keyframe", "Delete one offset keyframe from a character bone.",
         {**BONE_TARGET, "bone": BONE_NAME, "frame": TAKE_FRAME}, ("bone", "frame")),
    tool("move_bone_keyframe", "Move one offset keyframe to another character-take frame.",
         {**BONE_TARGET, "bone": BONE_NAME, "frame": TAKE_FRAME, "new_frame": TAKE_FRAME},
         ("bone", "frame", "new_frame")),
    tool("set_bone_range", "Apply a bone offset over an inclusive character-take frame range, "
         "with identity guards outside the selected range.",
         {**BONE_TARGET, **BONE_OFFSET, "bone": BONE_NAME,
          "frame_start": TAKE_FRAME, "frame_end": TAKE_FRAME}, ("bone", "frame_start", "frame_end")),
    tool("set_bone_layer_enabled", "Enable or bypass the saved bone-edit layer for preview and character FBX export.",
         {**BONE_TARGET, "enabled": {"type": "boolean"}}, ("enabled",)),
    tool("bone_editor_history", "Undo or redo one bone-edit operation in this session.",
         {**BONE_TARGET, "action": {"type": "string", "enum": ["undo", "redo"]}}, ("action",)),
    tool("clear_bone_track", "Remove all offset keys for one bone while preserving the captured motion.",
         {**BONE_TARGET, "bone": BONE_NAME}, ("bone",)),
    tool("save_bone_edits", "Persist the selected character take's bone-edit layer inside the saved project.",
         BONE_TARGET),
    tool("select_motion_target", "Focus a source person or retargeted character in the Bone Editor and viewport.",
         BONE_TARGET, ("character_id",)),
    tool("analyze_motion_range", "Summarize joint movement, speed and bend over a selected saved take range. "
         "Reports baseline as well when character edits are enabled. Does not save or train anything.",
         {**BONE_TARGET, "frame_start": TAKE_FRAME, "frame_end": TAKE_FRAME}, ("frame_start", "frame_end")),
    tool("remember_motion_example", "Save a user-approved take range as a local motion example. "
         "Use only for a range the user asked to remember. Saves joint statistics and a note in the current project.",
         {**BONE_TARGET, "frame_start": TAKE_FRAME, "frame_end": TAKE_FRAME,
          "label": {"type": "string", "minLength": 1, "maxLength": 120},
          "note": {"type": "string", "maxLength": 1200}}, ("frame_start", "frame_end", "label")),
    tool("search_motion_examples", "Find reviewed local motion examples by their label, notes, subject or joints. "
         "Use these references before proposing a similar edit.",
         {"query": {"type": "string", "maxLength": 250},
          "limit": {"type": "integer", "minimum": 1, "maximum": 25},
          "include_other_projects": {"type": "boolean", "default": False}}),
    tool("forget_motion_example", "Remove a selected reviewed example from the current project's motion memory.",
         {"example_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"}}, ("example_id",)),
)
TOOLS += BONE_TOOLS
BONE_TOOL_NAMES = {item["name"] for item in BONE_TOOLS}
ACTIONS.update({name: name for name in BONE_TOOL_NAMES})


def finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_bone_arguments(name, arguments):
    definition = next(item for item in BONE_TOOLS if item['name'] == name)['inputSchema']
    if set(arguments) - set(definition['properties']) or set(definition['required']) - set(arguments):
        raise ToolError('Provide only the documented arguments, including all required fields.')
    result = dict(arguments)
    for key, value in result.items():
        if key in {'bone', 'character_id'}:
            limit = 255 if key == 'bone' else 128
            if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
                raise ToolError(key + ' must be a non-empty name or identifier.')
        elif key == 'take_index':
            if type(value) is not int or not 0 <= value <= 2147483647:
                raise ToolError('take_index must be a zero-based whole-number take index.')
        elif key in {'frame', 'new_frame', 'frame_start', 'frame_end'}:
            if type(value) is not int or not 1 <= value <= 2147483647:
                raise ToolError(key + ' must be a positive whole-number character-take frame.')
        elif key in {'translation', 'rotation'}:
            if (not isinstance(value, list) or len(value) != 3
                    or not all(finite_number(number) for number in value)):
                raise ToolError(key + ' must contain exactly three finite numbers.')
        elif key in {'enabled', 'prepare', 'include_other_projects'}:
            if type(value) is not bool:
                raise ToolError(key + ' must be true or false.')
        elif key == 'space' and value not in ('local', 'world'):
            raise ToolError('space must be local or world.')
        elif key == 'action' and value not in ('undo', 'redo'):
            raise ToolError('action must be undo or redo.')
        elif key in {'label', 'note', 'query'}:
            limit = definition['properties'][key]['maxLength']
            if not isinstance(value, str) or len(value) > limit or '\x00' in value or (key == 'label' and not value.strip()):
                raise ToolError(key + ' must meet the documented text length.')
        elif key == 'limit' and (type(value) is not int or not 1 <= value <= 25):
            raise ToolError('limit must be a whole number between 1 and 25.')
        elif key == 'example_id' and (not isinstance(value, str) or len(value) != 32 or any(c not in '0123456789abcdef' for c in value)):
            raise ToolError('example_id must be the exact ID from search_motion_examples.')
    if 'frame_start' in result and result['frame_start'] > result['frame_end']:
        raise ToolError('frame_start must be at or before frame_end.')
    if name in {'set_bone_keyframe', 'set_bone_range'}:
        result.setdefault('translation', [0.0, 0.0, 0.0])
        result.setdefault('rotation', [0.0, 0.0, 0.0])
        result.setdefault('space', 'local')
    if name == 'list_bones':
        result.setdefault('prepare', True)
    return result


class ToolError(Exception):
    """A valid tool request could not complete."""


def read_line(stream, limit):
    line = stream.readline(limit + 1)
    if len(line) > limit:
        raise ValueError("Protocol message exceeds the size limit.")
    return line


def write_message(stream, message):
    data = json.dumps(message, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    stream.write(data.encode("utf-8") + b"\n")
    stream.flush()


def validate_arguments(name, arguments):
    if name in BONE_TOOL_NAMES:
        return validate_bone_arguments(name, arguments)
    if name == "get_status":
        if arguments:
            raise ToolError("get_status takes no arguments.")
    elif name == "open_project":
        path = arguments.get("project_path")
        if (set(arguments) != {"project_path"} or not isinstance(path, str)
                or len(path) > 4096 or "\x00" in path or not Path(path).is_absolute()):
            raise ToolError("Provide an absolute project folder or project.json path.")
    elif name == "capture_view":
        view = arguments.get("view", "viewport")
        if set(arguments) - {"view"} or view not in VIEWS:
            raise ToolError("view must be viewport, workspace, or video.")
        arguments = {"view": view}
    elif name == "select_frame_range":
        if not arguments:
            return arguments
        if (set(arguments) != {"frame_start", "frame_end"}
                or type(arguments["frame_start"]) is not int or type(arguments["frame_end"]) is not int
                or not 1 <= arguments["frame_start"] <= arguments["frame_end"] <= 2147483647):
            raise ToolError("Provide both inclusive frame boundaries, or omit both to clear the selection.")
    elif name == "export_fbx":
        path = arguments.get("output_path")
        if (set(arguments) - {"output_path", "frame_start", "frame_end", "character_name", "character_id"}
                or not isinstance(path, str)
                or len(path) > 4096 or "\x00" in path or path.startswith(("\\\\", "//"))
                or not Path(path).is_absolute() or Path(path).suffix.lower() != ".fbx"):
            raise ToolError("Provide an absolute local .fbx destination path.")
        has_start, has_end = "frame_start" in arguments, "frame_end" in arguments
        if has_start != has_end:
            raise ToolError("Provide both frame_start and frame_end, or omit both for all frames.")
        if has_start:
            start, end = arguments["frame_start"], arguments["frame_end"]
            if type(start) is not int or type(end) is not int or not 1 <= start <= end <= 2147483647:
                raise ToolError("Frames must be positive whole numbers, with frame_start at or before frame_end.")
        if "character_name" in arguments:
            character = arguments["character_name"]
            if not isinstance(character, str) or not character.strip() or len(character) > 255 or "\x00" in character:
                raise ToolError("character_name must be the exact saved character name.")
        if "character_id" in arguments:
            ident = arguments["character_id"]
            if not isinstance(ident, str) or not ident.strip() or len(ident) > 255 or "\x00" in ident:
                raise ToolError("character_id must come from get_status.")
            if "character_name" in arguments:
                raise ToolError("Provide either character_id or character_name.")
    else:
        frame = arguments.get("frame")
        if set(arguments) != {"frame"} or type(frame) is not int or not 1 <= frame <= 2147483647:
            raise ToolError("frame must be a positive whole number on the timeline.")
    return arguments


class PreviewSession:
    def __init__(self):
        self.process = None
        self.failure = None
        self.next_id = 0
        self.requests = queue.Queue(maxsize=1)
        self.replies = queue.Queue(maxsize=1)
        self.input_lock = threading.Lock()
        self.exchange_thread = None
        self.diagnostics_thread = None
        self.diagnostics = []
        self.diagnostics_lock = threading.Lock()

    def start(self):
        python = ROOT / "runtime" / "python.exe"
        if not python.is_file():
            raise ToolError("Install RGB MoCap with install.cmd before opening a preview session.")
        try:
            self.process = subprocess.Popen(
                [str(python), "-I", "-X", "utf8", "-B", str(ROOT / "launch_source.py"), "--mcp-session"],
                cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except OSError as error:
            raise ToolError(f"Could not start RGB MoCap: {error}") from error
        self.exchange_thread = threading.Thread(target=self.exchange, daemon=True)
        self.diagnostics_thread = threading.Thread(target=self.read_diagnostics, daemon=True)
        self.exchange_thread.start()
        self.diagnostics_thread.start()

    def read_diagnostics(self):
        with self.process.stderr as stream:
            for raw in iter(lambda: stream.readline(2048), b""):
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    with self.diagnostics_lock:
                        self.diagnostics.append(line)
                        del self.diagnostics[:-6]

    def exchange(self):
        proc = self.process
        with proc.stdout:
            while (request := self.requests.get()) is not None:
                try:
                    with self.input_lock:
                        write_message(proc.stdin, request)
                    line = read_line(proc.stdout, MAX_REPLY)
                    if not line:
                        raise EOFError("RGB MoCap closed its preview connection.")
                    response = json.loads(line.decode("utf-8"))
                    if not isinstance(response, dict) or response.get("id") != request["id"]:
                        raise ValueError("Unexpected reply from RGB MoCap.")
                    self.replies.put(response)
                except (OSError, ValueError, EOFError, RecursionError) as error:
                    self.replies.put(error)
                    return

    def call(self, action, arguments, disconnected):
        if self.failure:
            raise ToolError(self.failure)
        if self.process is None:
            self.start()
        self.next_id += 1
        request = {"id": self.next_id, "action": action, "arguments": arguments}
        self.requests.put_nowait(request)
        deadline = time.monotonic() + (BONE_TIMEOUT if action in BONE_TOOL_NAMES else GUI_TIMEOUT)
        while True:
            if disconnected.is_set():
                raise EOFError("MCP client disconnected.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.break_session("RGB MoCap did not reply within the preview timeout.")
            try:
                response = self.replies.get(timeout=min(remaining, 0.2))
                break
            except queue.Empty:
                continue
        if isinstance(response, Exception):
            self.break_session(str(response))
        if isinstance(response.get("error"), str):
            raise ToolError(response["error"][:2000])
        result = response.get("result")
        if not isinstance(result, dict):
            self.break_session("RGB MoCap returned an invalid preview result.")
        return result

    def break_session(self, reason):
        self.close()
        with self.diagnostics_lock:
            detail = self.diagnostics[-1][:700] if self.diagnostics else ""
        self.failure = reason + (f" {detail}" if detail else "")
        self.failure += " Reconnect the MCP session to start RGB MoCap again."
        raise ToolError(self.failure)

    def close(self):
        proc = self.process
        if proc is None:
            return
        try:
            self.requests.put_nowait(None)
        except queue.Full:
            # A request still waiting to be sent can be discarded on disconnect.
            try:
                self.requests.get_nowait()
            except queue.Empty:
                pass
            self.requests.put_nowait(None)
        # Close stdin without waiting on a writer blocked in a full pipe.
        if self.input_lock.acquire(blocking=False):
            try:
                proc.stdin.close()
            except OSError:
                pass
            finally:
                self.input_lock.release()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        self.exchange_thread.join(timeout=0.5)
        self.diagnostics_thread.join(timeout=0.5)
        if not proc.stdin.closed:
            try:
                proc.stdin.close()
            except OSError:
                pass
        self.process = None


def tool_result(result):
    images = result.get("images", [])
    if not isinstance(images, list) or len(images) > 2:
        raise ToolError("RGB MoCap returned an invalid image list.")
    metadata = {key: value for key, value in result.items() if key != "images"}
    content = [{"type": "text", "text": json.dumps(metadata, ensure_ascii=False)}]
    for image in images:
        if not isinstance(image, dict) or image.get("mimeType") != "image/png":
            raise ToolError("RGB MoCap returned an invalid image type.")
        data = image.get("data")
        if not isinstance(data, str) or len(data) > ((MAX_IMAGE + 2) // 3) * 4:
            raise ToolError("RGB MoCap returned an oversized preview image.")
        try:
            png = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ToolError("RGB MoCap returned invalid image data.") from error
        if not png.startswith(PNG_SIGNATURE) or len(png) > MAX_IMAGE:
            raise ToolError("RGB MoCap returned an invalid PNG image.")
        label = image.get("label")
        if isinstance(label, str) and label:
            content.append({"type": "text", "text": label[:250]})
        content.append({"type": "image", "mimeType": "image/png", "data": data})
    return {"content": content, "isError": False}


def rpc_error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def rpc_result(request_id, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


class McpServer:
    def __init__(self):
        self.version = None
        self.ready = False
        self.session = PreviewSession()

    def dispatch(self, request, disconnected):
        if not isinstance(request, dict):
            return rpc_error(None, -32600, "Invalid request.")
        method = request.get("method")
        request_id = request.get("id")
        has_id = "id" in request
        if (request.get("jsonrpc") != "2.0" or not isinstance(method, str)
                or (has_id and type(request_id) not in (int, str))):
            return rpc_error(None, -32600, "Invalid request.")
        params = request.get("params", {})
        if not has_id:
            if method == "notifications/initialized" and self.version is not None:
                self.ready = True
            return None
        if not isinstance(params, dict):
            return rpc_error(request_id, -32602, "params must be an object.")
        if method == "ping":
            return rpc_result(request_id, {})
        if method == "initialize":
            if self.version is not None:
                return rpc_error(request_id, -32600, "MCP session already initialized.")
            version = params.get("protocolVersion")
            if not isinstance(version, str):
                return rpc_error(request_id, -32602, "protocolVersion must be a string.")
            self.version = version if version in PROTOCOLS else PROTOCOLS[0]
            return rpc_result(request_id, {
                "protocolVersion": self.version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "rgbmocap", "version": "1.2.0"},
                "instructions": "Use this local session to inspect, edit character bones and export saved RGB MoCap projects. "
                                "Frames are one-based; bone tools use character-take frames. Images are PNG tool results.",
            })
        if not self.ready:
            return rpc_error(request_id, -32000, "Initialize the MCP session first.")
        if method == "tools/list":
            return rpc_result(request_id, {"tools": TOOLS})
        if method != "tools/call":
            return rpc_error(request_id, -32601, "Method not found.")
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or name not in ACTIONS:
            return rpc_error(request_id, -32602, "Unknown RGB MoCap tool.")
        if not isinstance(arguments, dict):
            return rpc_error(request_id, -32602, "arguments must be an object.")
        try:
            arguments = validate_arguments(name, arguments)
            result = tool_result(self.session.call(ACTIONS[name], arguments, disconnected))
        except ToolError as error:
            result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
        return rpc_result(request_id, result)


def read_client(stream, messages, disconnected):
    try:
        while (line := read_line(stream, MAX_REQUEST)):
            messages.put(line)
    except (OSError, ValueError) as error:
        messages.put(error)
    finally:
        disconnected.set()
        messages.put(None)


def main():
    server = McpServer()
    messages = queue.Queue(maxsize=8)
    disconnected = threading.Event()
    threading.Thread(target=read_client, args=(sys.stdin.buffer, messages, disconnected),
                     daemon=True).start()
    try:
        while (message := messages.get()) is not None:
            if isinstance(message, Exception):
                write_message(sys.stdout.buffer, rpc_error(None, -32600, str(message)))
                break
            try:
                request = json.loads(message.decode("utf-8"))
            except (ValueError, RecursionError):
                response = rpc_error(None, -32700, "Invalid JSON.")
            else:
                response = server.dispatch(request, disconnected)
            if response is not None:
                write_message(sys.stdout.buffer, response)
    except (BrokenPipeError, EOFError, KeyboardInterrupt):
        pass
    finally:
        server.session.close()


if __name__ == "__main__":
    main()
