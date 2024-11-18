import tree_sitter
from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_config import Language
import multilspy.multilspy_types as multispy_types

from pathlib import Path


class WorkSpace:
    def __init__(self, language: Language, repository_root_path: str):
        self.tree_map = {}
        self.root = Path(repository_root_path)
        self.parser = tree_sitter.Parser(language.tree_sitter())
        for path in self.root.rglob(f'*{language.extension()}'):
            content = path.read_bytes()
            self.tree_map[path] = self.parser.parse(content)

    def __getitem__(self, key: str) -> tree_sitter.Tree:
        key = Path(key).name
        absolute_path = self.root/key
        return self.tree_map[absolute_path]

    def __setitem__(self, key: str, value: tree_sitter.Node):
        key = Path(key).name
        absolute_path = self.root/key
        self.tree_map[absolute_path] = value


class LanguageServerAnalyzer:
    def __init__(self, language: Language, repository_root_path: str):
        config = MultilspyConfig.from_dict({"code_language": language})
        logger = MultilspyLogger()
        self.tree_sitter_language = language.tree_sitter()
        self.lsp = SyncLanguageServer.create(
            config, logger, repository_root_path)
        self.workspace = WorkSpace(language, repository_root_path)

    def get_file_tree(self, file: str) -> tree_sitter.Tree:
        return self.workspace[file]

    def request_definition_by_line(self, file: str, line: int, column: int) -> tuple[str, tree_sitter.Node] | None:
        with self.lsp.start_server():
            lsp_results = self.lsp.request_definition(file, line, column)
        if lsp_results is None:
            return None
        query = self.tree_sitter_language.query(
            """(identifier)@element"""
        )
        for lsp_result in lsp_results:
            lsp_range = lsp_result['range']
            relative_path = lsp_result["relativePath"]
            file_node = self.workspace[relative_path].root_node
            captures = query.captures(file_node)
            all_identifiers = captures["element"]
            first = filter(lambda ident: pos_eq(
                lsp_range, ident.range), all_identifiers)
            if len(all_identifiers) > 0:
                if first := next(first, None):
                    return relative_path, first
                # if [0, 0] -> [0, 1], it means the file itself is the definition
                if pos_eq(lsp_range, tree_sitter.Range((0, 0), (0, 1), 0, 1)):
                    return relative_path, file_node
        else:
            return None

    def request_definition(self, file: str, node: tree_sitter.Node) -> tuple[str, tree_sitter.Node] | None:
        start_point = node.range.start_point
        line, column = start_point.row, start_point.column
        return self.request_definition_by_line(file, line, column)

    def request_rename_by_line(self, file: str, line: int, column: int, new_name: str) -> bool:
        with self.lsp.start_server():
            lsp_results = self.lsp.request_rename(file, line, column, new_name)
        if lsp_results is None:
            return False
        document_changes = lsp_results["documentChanges"]

        for change in document_changes:
            assert "textDocument" in change
            url = change["textDocument"]["uri"]
            new_lines = self.get_file_tree(
                url).root_node.text.decode().splitlines()
            edits = change["edits"]
            for edit in edits:
                range_ = edit["range"]
                start, end = range_["start"], range_["end"]
                assert start["line"] == end["line"]
                line = start["line"]
                new_text = edit["newText"]
                new_lines[line] = new_lines[line][0:start["character"]] + \
                    new_text + new_lines[line][end["character"]:]
            self.workspace[url] = self.workspace.parser.parse(
                '\n'.join(new_lines).encode())
        return True

    def request_rename(self, file: str, node: tree_sitter.Node, new_name: str) -> bool:
        start_point = node.range.start_point
        line, column = start_point.row, start_point.column
        return self.request_rename_by_line(file, line, column, new_name)

    def text(self, file: str) -> str:
        return self.workspace[file].root_node.text.decode()


def pos_eq(lsp_range: multispy_types.Range, tree_range: tree_sitter.Range) -> bool:
    return lsp_range["start"]["line"] == tree_range.start_point.row and lsp_range["end"]["line"] == tree_range.end_point.row and lsp_range["start"]["character"] == tree_range.start_point.column and lsp_range["end"]["character"] == tree_range.end_point.column


repo_path = Path(__file__).parent/"test"
file_name = "b.py"
analyzer = LanguageServerAnalyzer(Language.PYTHON, str(repo_path))

root_node = analyzer.get_file_tree(file_name).root_node
print(root_node.text.decode())
# REQUEST DEFINITION EXAMPLE
query = Language.PYTHON.tree_sitter().query(
    """(identifier)@element"""
)
captures = query.captures(root_node)
elements = captures["element"]
for element in elements:
    def_file, def_node = analyzer.request_definition(file_name, element)
    # print file, line, column -> definition file, line, column
    print(f"{file_name}, [{element.range.start_point.row}, {element.range.start_point.column}] -> {def_file}, [{def_node.range.start_point.row}, {def_node.range.start_point.column}]")
# RENAME EXAMPLE
a = elements[-1]
assert analyzer.request_rename(file_name, a, "bb")
print('After rename:')
print(analyzer.text(file_name))
print('#'*10)
print(analyzer.text("a.py"))
