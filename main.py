import tree_sitter
import tree_sitter_python as tspython

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_config import Language
import multilspy.multilspy_types as multispy_types

from pathlib import Path

PY_LANGUAGE = tree_sitter.Language(tspython.language())


class LanguageServerAnalyzer:
    def __init__(self, language: Language, repository_root_path: str, file: str):
        config = MultilspyConfig.from_dict({"code_language": language})
        logger = MultilspyLogger()
        self.lsp = SyncLanguageServer.create(
            config, logger, repository_root_path)
        self.file = file
        with open(Path(repository_root_path)/file, "rb") as f:
            content = f.read()
            parser = tree_sitter.Parser(PY_LANGUAGE)
            self.tree = parser.parse(content)
        # for path in Path(repository_root_path).rglob(f'*{language.extension()}'):
        #     print(path.name)

    def request_definition(self, file: str, node: tree_sitter.Node) -> tree_sitter.Node | None:
        start_point = node.range.start_point
        line, column = start_point.row, start_point.column
        with self.lsp.start_server():
            lsp_results = self.lsp.request_definition(
                file,
                line,
                column
            )
            print(lsp_results)
        if lsp_results is None:
            return None
        query = PY_LANGUAGE.query(
            """(identifier)@element"""
        )
        captures = query.captures(root_node)
        all_identifiers = captures["element"]
        for lsp_result in lsp_results:
            lsp_range = lsp_result['range']
            first = next(filter(lambda ident: pos_eq(
                lsp_range, ident.range), all_identifiers))
            return first
        else:
            raise NotImplementedError()


def pos_eq(lsp_range: multispy_types.Range, tree_range: tree_sitter.Range) -> bool:
    return lsp_range["start"]["line"] == tree_range.start_point.row and lsp_range["end"]["line"] == tree_range.end_point.row and lsp_range["start"]["character"] == tree_range.start_point.column and lsp_range["end"]["character"] == tree_range.end_point.column


analyzer = LanguageServerAnalyzer(
    Language.PYTHON, "/Users/zhanqi/project/lsp_analyzer/test", "a.py")
root_node = analyzer.tree.root_node
query = PY_LANGUAGE.query(
    """(identifier)@element"""
)
captures = query.captures(root_node)
elements = captures["element"]
for element in elements:
    definition = analyzer.request_definition("a.py", element)
    print(f"{element.range} -> {definition.range}")
