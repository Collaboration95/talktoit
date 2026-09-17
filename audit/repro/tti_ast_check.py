"""AST check."""

import ast
import pathlib

path = pathlib.Path("backend/app/state/app_state.py")
text = path.read_text()
tree = ast.parse(text)
names = {
    "add_completed_turn",
    "finish_turn",
    "terminate_turn",
    "create_pending_turn",
    "get_turns",
    "list_conversations",
    "put_cached_response",
    "get_cached_entry",
    "update_conversation_title",
    "delete_conversation",
}
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
        src = ast.get_source_segment(text, node) or ""
        print(
            node.name, node.lineno, "ensure_ready_calls=", src.count("_ensure_ready()")
        )
