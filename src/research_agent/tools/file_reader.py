"""Read bounded UTF-8 text from a caller-authorized directory."""

from pathlib import Path, PureWindowsPath

from research_agent.llm.base import JsonObject
from research_agent.parameters import Parameter
from research_agent.security import PathNotAllowed, open_authorized
from research_agent.tools.base import BaseTool, ToolError


class FileReader(BaseTool):
    name = "read_file"
    description = "Read a UTF-8 .txt or .md file by path relative to the authorized directory."
    parameters = {
        "path": Parameter("string", "Relative file path", min_length=1, max_length=512),
    }

    def __init__(self, root: Path, *, max_bytes: int = 8192):
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("The authorized file root must be a directory")
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError("The file byte limit must be a positive integer")
        self.max_bytes = max_bytes

    def execute(self, *, path: str) -> JsonObject:
        windows_path = PureWindowsPath(path)
        relative = Path(path.replace("\\", "/"))
        if (
            windows_path.anchor
            or relative.is_absolute()
            or ".." in relative.parts
            or ":" in path
            or "\x00" in path
            or any(PureWindowsPath(part).is_reserved() for part in windows_path.parts)
        ):
            raise ToolError("invalid_path", "Provide a relative file path inside the authorized directory")
        if relative.suffix.lower() not in {".txt", ".md"}:
            raise ToolError("unsupported_format", "Only .txt and .md files are supported")
        try:
            target = (self.root / relative).resolve(strict=True)
            if not target.is_relative_to(self.root):
                raise ToolError("path_not_allowed", "File is outside the authorized directory")
            if target.suffix.lower() not in {".txt", ".md"} or not target.is_file():
                raise ToolError("unsupported_format", "The target must be a regular .txt or .md file")
            with open_authorized(self.root, target) as handle:
                data = handle.read(self.max_bytes + 1)
        except PathNotAllowed as error:
            raise ToolError("path_not_allowed", "File is outside the authorized set") from error
        except FileNotFoundError as error:
            raise ToolError("file_not_found", "File does not exist") from error
        except (OSError, RuntimeError, ValueError) as error:
            raise ToolError("file_read_error", "Could not read the requested file") from error
        if len(data) > self.max_bytes:
            raise ToolError("file_too_large", f"File exceeds the {self.max_bytes}-byte read limit")
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ToolError("invalid_encoding", "File must contain UTF-8 text") from error
        return {"path": target.relative_to(self.root).as_posix(), "content": content}
